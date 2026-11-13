from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dictionary import City, Venue
from app.models.enums import EventCategory, EventStatus
from app.models.event import Event


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


class DictionaryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve_city_name(self, raw_city: str) -> str | None:
        normalized = _normalize(raw_city)
        if not normalized:
            return None
        similarity = func.similarity(City.normalized_name, normalized)
        return await self.session.scalar(
            select(City.name).where(City.normalized_name.op('%')(normalized), similarity >= 0.3)
            .order_by(similarity.desc(), City.name).limit(1)
        )

    async def get_all_cities(self) -> list[City]:
        return list((await self.session.scalars(select(City).order_by(City.name))).all())

    async def get_city_by_name(self, name: str) -> City | None:
        return await self.session.scalar(select(City).where(City.name == name))

    async def get_categories_stats(self, city_name: str | None = None) -> list[dict]:
        stmt = select(Event.category, func.count(Event.id)).where(Event.status == EventStatus.PUBLISHED)
        if city_name:
            stmt = stmt.where(Event.city == city_name)
        counts = dict((await self.session.execute(stmt.group_by(Event.category))).all())
        titles = {
            EventCategory.CONCERT: "Концерты",
            EventCategory.THEATER: "Спектакли",
            EventCategory.EXHIBITION: "Выставки",
            EventCategory.FESTIVAL: "Фестивали",
            EventCategory.CINEMA: "Кино",
            EventCategory.EXCURSION: "Экскурсии",
            EventCategory.OTHER: "Другие события",
        }
        return [{"category": category, "title_ru": title, "events_count": counts.get(category, 0)}
                for category, title in titles.items()]

    async def get_venues_by_city(self, city_name: str | None = None) -> list[Venue]:
        stmt = select(Venue).join(City).order_by(Venue.name)
        if city_name:
            stmt = stmt.where(City.name == city_name)
        return list((await self.session.scalars(stmt)).all())

    async def upsert_city_and_venue(self, city_name: str, venue_name: str, address: str, lat: Decimal | None, lon: Decimal | None) -> None:
        city = await self.session.scalar(select(City).where(City.name == city_name))
        if city is None:
            # Venue coordinates are not the city centre; do not fabricate it.
            raise ValueError(f"Город {city_name!r} отсутствует в справочнике; сначала добавьте его центр")
        normalized = _normalize(venue_name)
        venue = await self.session.scalar(select(Venue).where(Venue.city_id == city.id, Venue.normalized_name == normalized, Venue.address == address))
        if venue is None:
            self.session.add(Venue(city_id=city.id, name=venue_name, normalized_name=normalized, address=address, lat=lat, lon=lon))
        else:
            venue.name, venue.lat, venue.lon = venue_name, lat, lon
        await self.session.flush()
