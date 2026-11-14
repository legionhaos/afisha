import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Float,
    and_,
    cast,
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

    def _build_base_filters(self, filters: EventSearchFilterDTO, exclude: str | None = None) -> list[Any]:
        """Формирует общие предикаты фильтрации каталога."""
        clauses = [Event.status == EventStatus.PUBLISHED]

        if filters.city:
            clauses.append(func.lower(Event.city) == filters.city.strip().lower())
        if filters.venue:
            clauses.append(func.lower(Event.venue).contains(filters.venue.strip().lower()))
        if filters.category and exclude != "category":
            clauses.append(Event.category == filters.category)
        if filters.date_from and exclude != "date":
            clauses.append(Event.date_start >= filters.date_from)
        if filters.date_to and exclude != "date":
            clauses.append(Event.date_start <= filters.date_to)
        if filters.price_max is not None and exclude != "price":
            clauses.append(Event.price_min <= filters.price_max)
        if filters.is_free is not None:
            clauses.append(Event.is_free.is_(filters.is_free))
        if filters.age_limit_max is not None and exclude != "age":
            clauses.append(Event.age_limit <= filters.age_limit_max)
        if filters.max_duration_min is not None and exclude != "duration":
            clauses.append(Event.duration_min <= filters.max_duration_min)
        if filters.language:
            clauses.append(func.lower(Event.language) == filters.language.strip().lower())
        if filters.tags:
            clauses.append(Event.tags.contains(filters.tags))

        return clauses

    @staticmethod
    def _topic_filter(query: str) -> Any:
        terms = [term.strip().lower() for term in query.split("|") if term.strip()]
        topic_clauses = []
        for term in terms:
            ts_query = func.plainto_tsquery("russian", term)
            if term in {"хоккей", "hockey"}:
                topic_clauses.extend([
                    func.lower(Event.title).op("~*")(r"(^|[^[:alnum:]])хоккей[[:alpha:]]*([^[:alnum:]]|$)"),
                    func.lower(Event.description).op("~*")(r"(^|[^[:alnum:]])хоккей[[:alpha:]]*([^[:alnum:]]|$)"),
                ])
            topic_clauses.extend([
                Event.tsv.op("@@")(ts_query),
                func.lower(Event.title).op("~*")(rf"(^|[^[:alnum:]]){re.escape(term)}([^[:alnum:]]|$)"),
                func.lower(Event.description).op("~*")(rf"(^|[^[:alnum:]]){re.escape(term)}([^[:alnum:]]|$)"),
                Event.tags.contains([term]),
            ])
        topic_clauses.append(Event.normalized_title.op("%")(query.casefold().replace("ё", "е")))
        return or_(*topic_clauses)

    async def hybrid_search(
        self,
        filters: EventSearchFilterDTO,
        query_embedding: list[float] | None = None,
    ) -> tuple[list[Event], int]:
        """Объединяет ранги текстового и векторного поиска через RRF."""
        clauses = self._build_base_filters(filters)

        query_text = filters.query_text.strip() if filters.query_text else None
        if query_text:
            clauses.append(self._topic_filter(query_text))

        query = filters.query_text.strip() if filters.query_text else ""
        text_ranked = vector_ranked = None
        if query:
            normalized = query.casefold().replace("ё", "е")
            tsquery = func.websearch_to_tsquery("russian", query)
            similarity = func.similarity(Event.normalized_title, normalized)
            score = func.ts_rank(Event.tsv, tsquery) + similarity
            text_ranked = (
                select(Event.id.label("id"), func.row_number().over(order_by=(score.desc(), Event.id)).label("rank"))
                .where(*clauses, or_(Event.tsv.op("@@")(tsquery), Event.normalized_title.op("%")(normalized)))
                .cte("text_search")
            )
        if query_embedding is not None:
            distance = Event.embedding.cosine_distance(query_embedding)
            vector_ranked = (
                select(Event.id.label("id"), func.row_number().over(order_by=(distance, Event.id)).label("rank"))
                .where(*clauses, Event.embedding.is_not(None))
                .order_by(distance, Event.id).limit(20).cte("vector_search")
            )
        ranked = None
        if text_ranked is not None and vector_ranked is not None:
            score = (func.coalesce(0.4 / (60 + cast(text_ranked.c.rank, Float)), 0.0)
                     + func.coalesce(0.6 / (60 + cast(vector_ranked.c.rank, Float)), 0.0))
            ranked = (select(func.coalesce(text_ranked.c.id, vector_ranked.c.id).label("id"), score.label("score"))
                      .select_from(text_ranked.join(vector_ranked, text_ranked.c.id == vector_ranked.c.id, full=True))
                      .cte("ranked"))
        elif text_ranked is not None or vector_ranked is not None:
            source = text_ranked if text_ranked is not None else vector_ranked
            ranked = select(source.c.id, (1.0 / (60 + cast(source.c.rank, Float))).label("score")).cte("ranked")
        stmt = select(Event).options(selectinload(Event.sources)).where(*clauses)
        count_stmt = select(func.count(Event.id)).where(*clauses)
        if ranked is not None:
            stmt = stmt.join(ranked, ranked.c.id == Event.id)
            count_stmt = count_stmt.join(ranked, ranked.c.id == Event.id)
        if filters.sort_by == "price_min":
            ordering = (Event.price_min, Event.date_start, Event.id)
        elif filters.sort_by == "relevance" and ranked is not None:
            ordering = (ranked.c.score.desc(), Event.date_start, Event.id)
        else:
            ordering = (Event.date_start, Event.id)
        total = (await self.session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(*ordering).offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def diagnose_blocking_constraints(self, filters: EventSearchFilterDTO) -> list[str]:
        """Проверяет каждое ослабление с сохранением остальных ограничений."""
        active = {
            "price": filters.price_max is not None,
            "date": filters.date_from is not None or filters.date_to is not None,
            "age": filters.age_limit_max is not None,
            "duration": filters.max_duration_min is not None,
            "category": filters.category is not None,
        }
        expressions = []
        for name, enabled in active.items():
            if not enabled:
                continue
            clauses = self._build_base_filters(filters, exclude=name)
            if filters.query_text and filters.query_text.strip():
                query = filters.query_text.strip()
                normalized = query.casefold().replace("ё", "е")
                clauses.append(self._topic_filter(query))
                # Without an embedding, hybrid_search additionally requires a
                # full-text or trigram match in its text ranking CTE.
                clauses.append(or_(
                    Event.tsv.op("@@")(func.websearch_to_tsquery("russian", query)),
                    Event.normalized_title.op("%")(normalized),
                ))
            expressions.append(func.count(Event.id).filter(and_(*clauses)).label(name))
        if not expressions:
            return ["По заданным параметрам нет запланированных событий."]
        counts = (await self.session.execute(select(*expressions))).one()._mapping
        labels = {"price": "Цена", "date": "Даты", "age": "Возрастной ценз",
                  "duration": "Продолжительность", "category": "Категория"}
        result = [f"{labels[name]}: при снятии ограничения доступно {counts[name]} мероприятий"
                  for name in active if name in counts and counts[name] > 0]
        return result or ["По заданным параметрам нет запланированных событий."]

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
            distance = Event.embedding.cosine_distance(base_event.embedding)
            stmt = stmt.where(or_(Event.category == base_event.category, distance <= 0.3)).order_by(
                distance.nulls_last(), Event.date_start.asc(), Event.id,
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
        # Serialize imports for one canonical event, including the initial insert.
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(dedup_key, 0)))
        )
        existing = await self.get_by_dedup_key(dedup_key)

        if existing:
            # 1. Duplicate found: merge incoming data and record new source
            existing.description = max(existing.description or "", event_data.get("description") or "", key=len)
            if event_data.get("org_link") and not existing.org_link:
                existing.org_link = event_data["org_link"]
            if event_data.get("lat") is not None and existing.lat is None:
                existing.lat = event_data["lat"]
                existing.lon = event_data["lon"]

            # Merge tags
            incoming_tags = event_data.get("tags", [])
            existing.tags = list(dict.fromkeys([*(existing.tags or []), *incoming_tags]))
            if event_data.get("verified_at") is not None:
                existing.verified_at = event_data["verified_at"]

            if event_data.get("status") == EventStatus.CANCELLED:
                existing.status = EventStatus.CANCELLED
            if event_data.get("is_disputed"):
                existing.is_disputed = True
                existing.dispute_reason = event_data.get("dispute_reason")
                if existing.status != EventStatus.CANCELLED:
                    existing.status = EventStatus.DRAFT

            if existing.price_min == 0 and existing.price_max == 0 and not existing.is_free:
                existing.price_min = event_data.get("price_min", 0)
                existing.price_max = event_data.get("price_max", 0)
                existing.is_free = event_data.get("is_free", False)

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
