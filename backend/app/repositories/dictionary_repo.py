from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dictionary import City, Venue
from app.models.event import Event
from app.models.enums import EventCategory, EventStatus


class DictionaryRepository:
    """Репозиторий для справочников городов, площадок и категорий."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve_city_name(self, raw_city: str) -> str | None:
        """Нечеткий поиск города через триграммы pg_trgm с порогом 0.45 для исправления опечаток."""
        if not raw_city or not raw_city.strip():
            return None

        clean = raw_city.strip().lower()

        # 1. Exact match on normalized_name
        stmt_exact = select(City.name).where(City.normalized_name == clean).limit(1)
        res_exact = await self.session.execute(stmt_exact)
        city_exact = res_exact.scalar_one_or_none()
        if city_exact:
            return city_exact

        # 2. Trigram similarity match with threshold >= 0.45
        # In PostgreSQL with pg_trgm: func.similarity(City.normalized_name, clean)
        similarity_expr = func.similarity(City.normalized_name, clean)
        stmt_fuzzy = (
            select(City.name, similarity_expr.label("sim"))
            .where(similarity_expr >= 0.45)
            .order_by(similarity_expr.desc())
            .limit(1)
        )
        res_fuzzy = await self.session.execute(stmt_fuzzy)
        row = res_fuzzy.first()
        if row:
            return row[0]

        return None

    async def get_all_cities(self) -> list[City]:
        """Возвращает список всех зарегистрированных городов."""
        stmt = select(City).order_by(City.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_city_by_name(self, name: str) -> City | None:
        """Находит город по точному названию."""
        stmt = select(City).where(City.name == name)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_venues_by_city(self, city_name: str | None = None) -> list[Venue]:
        """Возвращает список площадок, опционально отфильтрованный по городу."""
        stmt = select(Venue).join(City, Venue.city_id == City.id)
        if city_name:
            stmt = stmt.where(City.name == city_name)
        stmt = stmt.order_by(Venue.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_categories_stats(self, city_name: str | None = None) -> list[dict[str, Any]]:
        """Возвращает список категорий с подсчетом активных опубликованных событий."""
        stmt = (
            select(Event.category, func.count(Event.id).label("cnt"))
            .where(Event.status == EventStatus.PUBLISHED)
        )
        if city_name:
            stmt = stmt.where(Event.city == city_name)
        stmt = stmt.group_by(Event.category)

        result = await self.session.execute(stmt)
        counts_map = {cat: cnt for cat, cnt in result.all()}

        category_titles = {
            EventCategory.CONCERT: "Концерты",
            EventCategory.THEATER: "Спектакли",
            EventCategory.EXHIBITION: "Выставки",
            EventCategory.FESTIVAL: "Фестивали",
            EventCategory.CINEMA: "Кино",
            EventCategory.EXCURSION: "Экскурсии",
            EventCategory.OTHER: "Другие события",
        }

        stats: list[dict[str, Any]] = []
        for cat in EventCategory:
            stats.append({
                "category": cat,
                "title_ru": category_titles.get(cat, cat.value.capitalize()),
                "events_count": counts_map.get(cat, 0),
            })
        return stats

    async def upsert_city(
        self,
        name: str,
        normalized_name: str,
        lat: Decimal | None = None,
        lon: Decimal | None = None,
    ) -> City:
        """Вставляет или возвращает существующий город."""
        stmt = select(City).where(City.name == name)
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        city = City(
            id=uuid4(),
            name=name,
            normalized_name=normalized_name,
            lat=lat,
            lon=lon,
        )
        self.session.add(city)
        await self.session.flush()
        return city

    async def upsert_venue(
        self,
        city_id: UUID,
        name: str,
        normalized_name: str,
        address: str,
        lat: Decimal | None = None,
        lon: Decimal | None = None,
    ) -> Venue:
        """Вставляет или возвращает существующую площадку."""
        stmt = select(Venue).where(
            Venue.city_id == city_id,
            Venue.normalized_name == normalized_name,
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        venue = Venue(
            id=uuid4(),
            city_id=city_id,
            name=name,
            normalized_name=normalized_name,
            address=address,
            lat=lat,
            lon=lon,
        )
        self.session.add(venue)
        await self.session.flush()
        return venue
