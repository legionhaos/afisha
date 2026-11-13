from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Float, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.models.enums import EventStatus
from app.models.event import Event
from app.models.raw_record import RawEventRecord


class EventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, event_id: UUID, include_cancelled: bool = True) -> Event | None:
        stmt = select(Event).options(selectinload(Event.raw_sources)).where(Event.id == event_id)
        if not include_cancelled:
            stmt = stmt.where(Event.status == EventStatus.PUBLISHED)
        return await self.session.scalar(stmt)

    async def get_by_dedup_key(self, dedup_key: str) -> Event | None:
        return await self.session.scalar(select(Event).where(Event.dedup_key == dedup_key))

    async def get_by_source_hash(self, source_hash: str) -> Event | None:
        return await self.session.scalar(
            select(Event).join(RawEventRecord, RawEventRecord.event_id == Event.id)
            .where(RawEventRecord.source_hash == source_hash)
            .options(selectinload(Event.raw_sources))
        )

    async def get_by_ids_preserve_order(self, event_ids: list[UUID]) -> list[Event]:
        if not event_ids:
            return []
        result = await self.session.scalars(
            select(Event).where(Event.id.in_(event_ids))
            .options(selectinload(Event.raw_sources))
        )
        by_id = {event.id: event for event in result.all()}
        return [by_id[event_id] for event_id in event_ids if event_id in by_id]

    @staticmethod
    def _conditions(filters, exclude: str | None = None):
        conditions = [Event.status == EventStatus.PUBLISHED]
        def add(field, expression):
            if field != exclude:
                conditions.append(expression)
        if filters.city: add('city', func.lower(Event.city) == filters.city.lower())
        if filters.venue: add('venue', func.lower(Event.venue) == filters.venue.lower())
        if filters.category: add('category', Event.category == filters.category)
        if filters.date_from: add('date', Event.date_start >= filters.date_from)
        if filters.date_to: add('date', Event.date_start <= filters.date_to)
        if filters.price_max is not None: add('price_max', Event.price_min <= filters.price_max)
        if filters.is_free is not None: add('is_free', Event.is_free == filters.is_free)
        if filters.age_limit_max is not None: add('age_limit_max', Event.age_limit <= filters.age_limit_max)
        if filters.max_duration_min is not None: add('max_duration_min', Event.duration_min <= filters.max_duration_min)
        if filters.language: add('language', func.lower(Event.language) == filters.language.lower())
        if filters.tags: add('tags', Event.tags.contains(filters.tags))
        return conditions

    async def hybrid_search(self, filters, query_embedding: list[float] | None = None) -> tuple[list[Event], int]:
        conditions = self._conditions(filters)
        query = filters.query_text.strip() if filters.query_text else None
        text_cte = vector_cte = None
        if query:
            tsquery = func.websearch_to_tsquery('russian', query)
            similarity = func.similarity(Event.normalized_title, query.lower().replace('ё', 'е'))
            text_score = func.ts_rank(Event.tsv, tsquery) + similarity
            title_match = Event.normalized_title.op('%')(query.lower().replace('ё', 'е'))
            text_cte = select(Event.id.label('id'), func.row_number().over(order_by=(text_score.desc(), Event.id)).label('rank')).where(*conditions, or_(Event.tsv.op('@@')(tsquery), title_match)).cte('text_search')
        if query_embedding is not None:
            distance = Event.embedding.cosine_distance(query_embedding)
            vector_cte = select(Event.id.label('id'), func.row_number().over(order_by=(distance, Event.id)).label('rank')).where(*conditions, Event.embedding.is_not(None)).order_by(distance, Event.id).limit(20).cte('vector_search')
        ranked = None
        if text_cte is not None and vector_cte is not None:
            ranked = select(func.coalesce(text_cte.c.id, vector_cte.c.id).label('id'), (func.coalesce(1.0 / (60 + cast(text_cte.c.rank, Float)), 0.0) + func.coalesce(1.0 / (60 + cast(vector_cte.c.rank, Float)), 0.0)).label('score')).select_from(text_cte.join(vector_cte, text_cte.c.id == vector_cte.c.id, full=True)).cte('ranked')
        elif text_cte is not None or vector_cte is not None:
            source = text_cte if text_cte is not None else vector_cte
            ranked = select(source.c.id, (1.0 / (60 + cast(source.c.rank, Float))).label('score')).cte('ranked')
        base = select(Event).where(*conditions)
        count = select(func.count()).select_from(Event).where(*conditions)
        if ranked is not None:
            base = base.join(ranked, ranked.c.id == Event.id)
            count = count.join(ranked, ranked.c.id == Event.id)
        if filters.sort_by == 'price_min': order = (Event.price_min, Event.date_start, Event.id)
        elif filters.sort_by == 'relevance' and ranked is not None: order = (ranked.c.score.desc(), Event.date_start, Event.id)
        else: order = (Event.date_start, Event.id)
        total = await self.session.scalar(count) or 0
        rows = await self.session.scalars(base.options(selectinload(Event.raw_sources)).order_by(*order).offset((filters.page - 1) * filters.page_size).limit(filters.page_size))
        return list(rows.all()), total

    async def diagnose_blocking_constraints(self, filters) -> list[str]:
        names = ('price_max', 'date', 'age_limit_max', 'max_duration_min', 'category')
        active = {'price_max': filters.price_max is not None, 'date': bool(filters.date_from or filters.date_to), 'age_limit_max': filters.age_limit_max is not None, 'max_duration_min': filters.max_duration_min is not None, 'category': filters.category is not None}
        expressions = []
        for name in names:
            if active[name]:
                cond = self._conditions(filters, name)
                if filters.query_text:
                    q = filters.query_text.strip()
                    cond.append(or_(Event.tsv.op('@@')(func.websearch_to_tsquery('russian', q)), Event.normalized_title.op('%')(q.lower().replace('ё', 'е'))))
                expressions.append(func.count().filter(and_(*cond)).label(name))
        if not expressions: return []
        row = (await self.session.execute(select(*expressions))).one()._mapping
        return [name for name in names if name in row and row[name] > 0]

    async def find_similar_events(self, event: Event, city: str | None, date_from: datetime | None, date_to: datetime | None, limit: int = 4) -> list[Event]:
        stmt = select(Event).where(Event.id != event.id, Event.status == EventStatus.PUBLISHED)
        if city: stmt = stmt.where(Event.city == city)
        if date_from: stmt = stmt.where(Event.date_start >= date_from)
        if date_to: stmt = stmt.where(Event.date_start <= date_to)
        if event.embedding is not None:
            distance = Event.embedding.cosine_distance(event.embedding)
            stmt = stmt.where(or_(Event.category == event.category, distance <= 0.3)).order_by(distance.nulls_last(), Event.date_start)
        else:
            stmt = stmt.where(Event.category == event.category).order_by(Event.date_start)
        return list((await self.session.scalars(stmt.options(selectinload(Event.raw_sources)).limit(limit))).all())

    async def get_venue_schedule(self, venue_query: str, date_from: datetime, date_to: datetime) -> list[Event]:
        stmt = select(Event).where(Event.status == EventStatus.PUBLISHED, Event.venue.op('%')(venue_query), Event.date_start >= date_from, Event.date_start <= date_to).order_by(Event.date_start).options(selectinload(Event.raw_sources))
        return list((await self.session.scalars(stmt)).all())

    async def create_or_update_event(self, event_data: dict[str, Any], raw_record_id: UUID) -> tuple[Event, str]:
        raw = await self.session.get(RawEventRecord, raw_record_id)
        if raw is None: raise ValueError('Raw record not found')
        if raw.event_id is not None:
            linked = await self.session.get(Event, raw.event_id)
            if linked is not None and linked.dedup_key != event_data['dedup_key']:
                raise ValueError('Изменился ключ связанного события; требуется проверка модератора')
        allowed = {column.key for column in Event.__table__.columns} - {'id', 'tsv', 'created_at', 'updated_at'}
        data = {key: value for key, value in event_data.items() if key in allowed}
        locked_query = (select(Event).where(Event.dedup_key == data['dedup_key'])
                        .with_for_update().execution_options(populate_existing=True))
        event = await self.session.scalar(locked_query)
        created = False
        if event is None:
            stmt = (insert(Event).values(**data)
                    .on_conflict_do_nothing(index_elements=[Event.dedup_key])
                    .returning(Event))
            event = await self.session.scalar(stmt)
            created = event is not None
            if event is None:
                event = await self.session.scalar(locked_query)
        if created:
            action = 'added'
        else:
            if event is None:
                raise RuntimeError('Conflicting event not visible; retry the transaction')
            action = 'updated' if raw.event_id == event.id else 'merged'
            # Merge under the row lock, not from a stale pre-insert snapshot.
            from app.services.deduplication_service import DeduplicationService

            for field, value in DeduplicationService().merge_event_fields(event, data).items():
                setattr(event, field, value)
            if data.get('is_disputed'):
                event.is_disputed = True
                event.dispute_reason = data.get('dispute_reason')
                if event.status != EventStatus.CANCELLED:
                    event.status = EventStatus.DRAFT
        raw.event_id = event.id
        await self.session.flush()
        return event, action

    async def list_moderation_queue(self, page: int, page_size: int) -> tuple[list[Event], int]:
        condition = or_(Event.is_disputed.is_(True), Event.status == EventStatus.DRAFT)
        total = await self.session.scalar(select(func.count()).select_from(Event).where(condition)) or 0
        rows = await self.session.scalars(select(Event).options(selectinload(Event.raw_sources)).where(condition).order_by(Event.created_at.desc(), Event.id).offset((page - 1) * page_size).limit(page_size))
        return list(rows.all()), total

    async def update_status(self, event_id: UUID, new_status: EventStatus, is_disputed: bool) -> Event:
        event = await self.get_by_id(event_id)
        if event is None: raise LookupError('Event not found')
        event.status, event.is_disputed = new_status, is_disputed
        await self.session.flush()
        return event
