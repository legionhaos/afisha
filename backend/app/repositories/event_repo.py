from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    and_,
    case,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import EventCategory, EventStatus, ModerationReason, SourceType
from app.models.event import Event, EventSource
from app.schemas.event import EventSearchFilterDTO


class EventRepository:
    """Асинхронный репозиторий для работы с мероприятиями и гибридным поиском."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, event_id: UUID, include_cancelled: bool = True) -> Event | None:
        """Получает мероприятие по ID с подгрузкой источников через selectinload."""
        stmt = (
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.id == event_id)
        )
        if not include_cancelled:
            stmt = stmt.where(Event.status == EventStatus.PUBLISHED)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ids_preserve_order(self, event_ids: list[UUID]) -> list[Event]:
        """Возвращает карточки по списку UUID с сохранением исходного порядка."""
        if not event_ids:
            return []
        stmt = (
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.id.in_(event_ids))
        )
        result = await self.session.execute(stmt)
        events_map = {e.id: e for e in result.scalars().all()}
        return [events_map[eid] for eid in event_ids if eid in events_map]

    async def get_by_dedup_key(self, dedup_key: str) -> Event | None:
        """Находит событие по уникальному ключу дедупликации."""
        stmt = (
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.dedup_key == dedup_key)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_source_hash(self, source_hash: str) -> Event | None:
        """Находит событие по первичному хешу источника (для идемпотентности)."""
        stmt = select(Event).where(Event.source_hash == source_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _build_base_filters(self, filters: EventSearchFilterDTO) -> list[Any]:
        """Формирует общие предикаты фильтрации каталога."""
        clauses = [Event.status == EventStatus.PUBLISHED]

        if filters.city:
            clauses.append(func.lower(Event.city) == filters.city.strip().lower())
        if filters.venue:
            clauses.append(func.lower(Event.venue).contains(filters.venue.strip().lower()))
        if filters.category:
            clauses.append(Event.category == filters.category)
        if filters.date_from:
            clauses.append(Event.date_start >= filters.date_from)
        if filters.date_to:
            clauses.append(Event.date_start <= filters.date_to)
        if filters.price_max is not None:
            clauses.append(Event.price_min <= filters.price_max)
        if filters.is_free is True:
            clauses.append(Event.is_free.is_(True))
        if filters.age_limit_max is not None:
            clauses.append(Event.age_limit <= filters.age_limit_max)
        if filters.max_duration_min is not None:
            clauses.append(
                or_(
                    Event.duration_min.is_(None),
                    Event.duration_min <= filters.max_duration_min,
                )
            )
        if filters.language:
            clauses.append(func.lower(Event.language) == filters.language.strip().lower())
        if filters.tags:
            clauses.append(Event.tags.contains(filters.tags))

        return clauses

    async def hybrid_search(
        self,
        filters: EventSearchFilterDTO,
        query_embedding: list[float] | None = None,
    ) -> tuple[list[Event], int]:
        """Гибридный поиск (RRF), объединяющий FTS (0.4) и Vector (0.6).

        При query_embedding is None автоматически переключается на комбинацию FTS и pg_trgm.
        """
        clauses = self._build_base_filters(filters)

        # 1. Total count query
        count_stmt = select(func.count(Event.id)).where(and_(*clauses))
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        if total == 0:
            return [], 0

        # 2. Main query construction
        query_text = filters.query_text.strip() if filters.query_text else None
        offset = (filters.page - 1) * filters.page_size
        limit = filters.page_size

        stmt = select(Event).options(selectinload(Event.sources)).where(and_(*clauses))

        if query_text and query_embedding is not None:
            # Hybrid search with Reciprocal Rank Fusion (RRF)
            # RRF_Score = 0.4 / (60 + rank_text) + 0.6 / (60 + rank_vec)
            # In PostgreSQL:
            text_rank_expr = func.ts_rank(Event.tsv, func.websearch_to_tsquery("russian", query_text))
            vec_dist_expr = Event.embedding.cosine_distance(query_embedding)

            # Combined score expression
            rrf_score = (
                0.4 / (60.0 + func.coalesce(text_rank_expr, 0.0)) +
                0.6 / (60.0 + func.coalesce(vec_dist_expr, 1.0))
            )
            stmt = stmt.order_by(rrf_score.desc(), Event.date_start.asc())
        elif query_text and query_embedding is None:
            # Degraded search without LLM: ts_rank + trigram similarity
            text_rank = func.ts_rank(Event.tsv, func.websearch_to_tsquery("russian", query_text))
            trgm_sim = func.similarity(Event.normalized_title, query_text.lower())
            combined = text_rank * 0.5 + trgm_sim * 0.5
            stmt = stmt.order_by(combined.desc(), Event.date_start.asc())
        else:
            # Default sorting by parameter
            if filters.sort_by == "price_min":
                stmt = stmt.order_by(Event.price_min.asc(), Event.date_start.asc())
            else:
                stmt = stmt.order_by(Event.date_start.asc())

        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def diagnose_blocking_constraints(self, filters: EventSearchFilterDTO) -> list[str]:
        """Находит блокирующие ограничения (цена, дата, возраст, категория) при пустой выдаче."""
        # Baseline where status == PUBLISHED and city matches (if specified)
        base_conditions = [Event.status == EventStatus.PUBLISHED]
        if filters.city:
            base_conditions.append(func.lower(Event.city) == filters.city.strip().lower())

        # Construct conditional counts testing each relaxation
        without_price_cond = list(base_conditions)
        without_date_cond = list(base_conditions)
        without_age_cond = list(base_conditions)
        without_category_cond = list(base_conditions)

        # Apply other filters except one
        if filters.category:
            without_price_cond.append(Event.category == filters.category)
            without_date_cond.append(Event.category == filters.category)
            without_age_cond.append(Event.category == filters.category)

        if filters.date_from:
            without_price_cond.append(Event.date_start >= filters.date_from)
            without_age_cond.append(Event.date_start >= filters.date_from)
            without_category_cond.append(Event.date_start >= filters.date_from)
        if filters.date_to:
            without_price_cond.append(Event.date_start <= filters.date_to)
            without_age_cond.append(Event.date_start <= filters.date_to)
            without_category_cond.append(Event.date_start <= filters.date_to)

        if filters.price_max is not None:
            without_date_cond.append(Event.price_min <= filters.price_max)
            without_age_cond.append(Event.price_min <= filters.price_max)
            without_category_cond.append(Event.price_min <= filters.price_max)

        if filters.age_limit_max is not None:
            without_price_cond.append(Event.age_limit <= filters.age_limit_max)
            without_date_cond.append(Event.age_limit <= filters.age_limit_max)
            without_category_cond.append(Event.age_limit <= filters.age_limit_max)

        stmt = select(
            func.count(Event.id).filter(and_(*without_price_cond)).label("cnt_no_price"),
            func.count(Event.id).filter(and_(*without_date_cond)).label("cnt_no_date"),
            func.count(Event.id).filter(and_(*without_age_cond)).label("cnt_no_age"),
            func.count(Event.id).filter(and_(*without_category_cond)).label("cnt_no_cat"),
        )
        res = await self.session.execute(stmt)
        row = res.first()

        blocking: list[str] = []
        if row:
            cnt_no_price, cnt_no_date, cnt_no_age, cnt_no_cat = row
            if cnt_no_price > 0 and filters.price_max is not None:
                blocking.append(
                    f"Цена: сняв ограничение до {filters.price_max} ₽, доступно еще {cnt_no_price} мероприятий"
                )
            if cnt_no_date > 0 and (filters.date_from or filters.date_to):
                blocking.append(
                    f"Даты: в другие дни в этом городе доступно {cnt_no_date} мероприятий"
                )
            if cnt_no_age > 0 and filters.age_limit_max is not None:
                blocking.append(
                    f"Возрастной ценз: для других возрастов доступно {cnt_no_age} мероприятий"
                )
            if cnt_no_cat > 0 and filters.category:
                blocking.append(
                    f"Категория: в других жанрах доступно {cnt_no_cat} мероприятий"
                )

        if not blocking:
            blocking.append("По заданным параметрам в выбранном городе нет запланированных событий.")

        return blocking

    async def find_similar_events(
        self,
        base_event: Event,
        city: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 4,
    ) -> list[Event]:
        """Ищет похожие мероприятия той же категории или по семантическому вектору."""
        clauses = [
            Event.status == EventStatus.PUBLISHED,
            Event.id != base_event.id,
        ]
        target_city = city or base_event.city
        clauses.append(func.lower(Event.city) == target_city.lower())

        if date_from:
            clauses.append(Event.date_start >= date_from)
        if date_to:
            clauses.append(Event.date_start <= date_to)

        stmt = select(Event).options(selectinload(Event.sources)).where(and_(*clauses))

        if base_event.embedding is not None:
            stmt = stmt.order_by(
                Event.embedding.cosine_distance(base_event.embedding).asc(),
                Event.date_start.asc(),
            )
        else:
            # Fallback to category and date
            stmt = stmt.where(Event.category == base_event.category).order_by(Event.date_start.asc())

        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_venue_schedule(
        self,
        venue_query: str,
        date_from: datetime,
        date_to: datetime,
    ) -> list[Event]:
        """Возвращает расписание мероприятий конкретной площадки."""
        stmt = (
            select(Event)
            .options(selectinload(Event.sources))
            .where(
                and_(
                    Event.status == EventStatus.PUBLISHED,
                    or_(
                        func.lower(Event.venue).contains(venue_query.strip().lower()),
                        func.similarity(Event.venue, venue_query.strip()) >= 0.4,
                    ),
                    Event.date_start >= date_from,
                    Event.date_start <= date_to,
                )
            )
            .order_by(Event.date_start.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_or_update_event(
        self,
        event_data: dict[str, Any],
        raw_record_id: UUID | None = None,
    ) -> tuple[Event, Literal["added", "updated", "merged"]]:
        """Идемпотентная вставка/обновление события с дедупликацией по dedup_key."""
        dedup_key = event_data["dedup_key"]
        existing = await self.get_by_dedup_key(dedup_key)

        if existing:
            # 1. Duplicate found: merge incoming data and record new source
            existing.description = max(existing.description, event_data.get("description", ""), key=len)
            if event_data.get("org_link") and not existing.org_link:
                existing.org_link = event_data["org_link"]
            if event_data.get("lat") and not existing.lat:
                existing.lat = event_data["lat"]
                existing.lon = event_data["lon"]

            # Merge tags
            incoming_tags = event_data.get("tags", [])
            existing.tags = list(set(existing.tags + incoming_tags))
            existing.verified_at = event_data.get("verified_at", datetime.now(existing.verified_at.tzinfo))

            # Add source entry
            src = EventSource(
                id=uuid4(),
                event_id=existing.id,
                raw_record_id=raw_record_id,
                source_url=event_data["source_url"],
                source_type=event_data["source_type"],
                source_hash=event_data["source_hash"],
            )
            self.session.add(src)
            await self.session.flush()
            return existing, "merged"

        # 2. Brand new event
        new_event = Event(**event_data)
        self.session.add(new_event)
        await self.session.flush()

        src = EventSource(
            id=uuid4(),
            event_id=new_event.id,
            raw_record_id=raw_record_id,
            source_url=new_event.source_url,
            source_type=new_event.source_type,
            source_hash=new_event.source_hash,
        )
        self.session.add(src)
        await self.session.flush()
        return new_event, "added"

    async def list_moderation_queue(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Event], int]:
        """Возвращает карточки, требующие модерации (is_disputed=True или status=DRAFT)."""
        clauses = or_(
            Event.is_disputed.is_(True),
            Event.status == EventStatus.DRAFT,
        )
        count_stmt = select(func.count(Event.id)).where(clauses)
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        offset = (page - 1) * page_size
        stmt = (
            select(Event)
            .options(selectinload(Event.sources))
            .where(clauses)
            .order_by(Event.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update_status(
        self,
        event_id: UUID,
        new_status: EventStatus,
        is_disputed: bool = False,
        dispute_reason: ModerationReason | None = None,
    ) -> Event | None:
        """Обновляет статус карточки события (например, перевод в CANCELLED)."""
        event = await self.get_by_id(event_id, include_cancelled=True)
        if not event:
            return None

        event.status = new_status
        event.is_disputed = is_disputed
        event.dispute_reason = dispute_reason
        await self.session.flush()
        return event
