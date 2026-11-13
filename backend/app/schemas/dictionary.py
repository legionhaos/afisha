from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import EventCategory


class CityDTO(BaseModel):
    """Город или населенный пункт Республики Башкортостан."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID = Field(..., description="ID города")
    name: str = Field(..., description="Официальное название (Уфа, Стерлитамак и т.д.)")
    normalized_name: str = Field(..., description="Нормализованное название для нечеткого поиска")
    lat: Decimal | None = Field(default=None, description="Географическая широта центра")
    lon: Decimal | None = Field(default=None, description="Географическая долгота центра")


class VenueDTO(BaseModel):
    """Площадка проведения мероприятий (театр, ДК, музей, парк)."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID = Field(..., description="ID площадки")
    city_id: UUID = Field(..., description="ID города размещения")
    name: str = Field(..., description="Название площадки")
    normalized_name: str = Field(..., description="Нормализованное название")
    address: str = Field(..., description="Адрес площадки")
    lat: Decimal | None = Field(default=None, description="Широта")
    lon: Decimal | None = Field(default=None, description="Долгота")


class CategoryStatsDTO(BaseModel):
    """Справочник категорий с количеством опубликованных событий."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    category: EventCategory = Field(..., description="Код категории")
    title_ru: str = Field(..., description="Отображаемое название на русском")
    events_count: int = Field(default=0, ge=0, description="Количество активных событий")


class DictionariesResponseDTO(BaseModel):
    """Сводный ответ справочников для фильтров каталога."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    cities: list[CityDTO]
    venues: list[VenueDTO]
    categories: list[CategoryStatsDTO]
