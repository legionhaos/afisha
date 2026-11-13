from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import EventCategory, EventStatus, ModerationReason, SourceType


class EventSourceDTO(BaseModel):
    """Информация об источнике данных, сведенном в карточку."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    source_url: str = Field(..., description="URL оригинального источника")
    source_type: SourceType = Field(..., description="Тип источника")
    merged_at: AwareDatetime = Field(..., description="Время слияния данных")


class EventCardDTO(BaseModel):
    """Публичная нормализованная карточка мероприятия."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID = Field(..., description="Уникальный идентификатор события")
    title: str = Field(..., description="Название мероприятия")
    normalized_title: str | None = Field(default=None, description="Нормализованное название для поиска")
    category: EventCategory = Field(..., description="Категория мероприятия")
    tags: list[str] = Field(default_factory=list, description="Теги мероприятия")
    date_start: AwareDatetime = Field(..., description="Дата и время начала в UTC+5")
    date_end: AwareDatetime | None = Field(default=None, description="Дата и время окончания")
    duration_min: int | None = Field(default=None, description="Длительность в минутах")
    city: str = Field(..., description="Город проведения")
    venue: str = Field(..., description="Площадка проведения")
    address: str = Field(..., description="Точный адрес площадки")
    lat: Decimal | None = Field(default=None, description="Широта")
    lon: Decimal | None = Field(default=None, description="Долгота")
    description: str = Field(..., description="Полное описание мероприятия")
    price_min: int = Field(default=0, ge=0, description="Минимальная цена билета в рублях")
    price_max: int = Field(default=0, ge=0, description="Максимальная цена билета в рублях")
    is_free: bool = Field(default=False, description="Признак бесплатного входа")
    age_limit: int = Field(default=0, ge=0, le=18, description="Возрастной ценз: 0, 6, 12, 16, 18")
    language: str | None = Field(default=None, description="Язык проведения (русский, башкирский и др.)")
    org_link: str | None = Field(default=None, description="Ссылка организатора на покупку билетов")
    source_url: str = Field(..., description="Основная ссылка на источник")
    status: EventStatus = Field(default=EventStatus.PUBLISHED, description="Статус публикации")
    cancelled_badge: str | None = Field(
        default=None,
        description="Явная пометка, если мероприятие отменено, но открыто по прямой ссылке",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Уверенность парсинга")
    is_disputed: bool = Field(default=False, description="Флаг спорной карточки")
    dispute_reason: ModerationReason | None = Field(default=None, description="Причина отправки на модерацию")
    verified_at: AwareDatetime = Field(..., description="Время последней проверки данных")
    sources: list[EventSourceDTO] = Field(default_factory=list, description="Источники, сведенные при дедупликации")


class EventCreateDTO(BaseModel):
    """Схема создания/импорта события с валидацией бизнес-правил."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    title: str = Field(..., min_length=2, max_length=500)
    category: EventCategory
    tags: list[str] = Field(default_factory=list)
    date_start: AwareDatetime
    date_end: AwareDatetime | None = None
    duration_min: int | None = Field(default=None, ge=1)
    city: str = Field(..., min_length=2, max_length=120)
    venue: str = Field(..., min_length=2, max_length=255)
    address: str = Field(..., min_length=5)
    lat: Decimal | None = None
    lon: Decimal | None = None
    description: str = Field(..., min_length=10)
    price_min: int = Field(default=0, ge=0)
    price_max: int = Field(default=0, ge=0)
    is_free: bool = Field(default=False)
    age_limit: int = Field(default=0)
    language: str | None = None
    org_link: str | None = None
    source_url: str
    source_type: SourceType = SourceType.IMPORT
    status: EventStatus = EventStatus.PUBLISHED

    @field_validator("age_limit")
    @classmethod
    def validate_age_limit(cls, v: int) -> int:
        valid_limits = {0, 6, 12, 16, 18}
        if v not in valid_limits:
            raise ValueError(f"Возрастное ограничение должно быть одним из {valid_limits}, получено: {v}")
        return v

    @model_validator(mode="after")
    def validate_prices_and_free(self) -> "EventCreateDTO":
        if self.is_free:
            self.price_min = 0
            self.price_max = 0
        elif self.price_max < self.price_min:
            raise ValueError(
                f"price_max ({self.price_max}) не может быть меньше price_min ({self.price_min})"
            )
        return self


class EventUpdateAdminDTO(BaseModel):
    """Схема модерации/обновления карточки события администратором."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    title: str | None = None
    category: EventCategory | None = None
    tags: list[str] | None = None
    date_start: AwareDatetime | None = None
    date_end: AwareDatetime | None = None
    duration_min: int | None = None
    city: str | None = None
    venue: str | None = None
    address: str | None = None
    description: str | None = None
    price_min: int | None = Field(default=None, ge=0)
    price_max: int | None = Field(default=None, ge=0)
    is_free: bool | None = None
    age_limit: int | None = None
    language: str | None = None
    org_link: str | None = None
    status: EventStatus | None = None
    is_disputed: bool | None = None
    dispute_reason: ModerationReason | None = None
    moderator_actor: str = Field(..., description="Идентификатор модератора для журнала аудита")


class EventSearchFilterDTO(BaseModel):
    """Параметры фильтрации и поиска по каталогу."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    query_text: str | None = Field(default=None, max_length=200, description="Поисковый текстовый запрос")
    city: str | None = Field(default=None, description="Город проведения")
    venue: str | None = Field(default=None, description="Площадка")
    category: EventCategory | None = Field(default=None, description="Категория")
    date_preset: Literal["today", "tomorrow", "weekend", "week"] | None = Field(
        default=None,
        description="Быстрый выбор периода относительно таймзоны Уфы (UTC+5)",
    )
    date_from: AwareDatetime | None = Field(default=None, description="Нижняя граница даты проведения")
    date_to: AwareDatetime | None = Field(default=None, description="Верхняя граница даты проведения")
    price_max: int | None = Field(default=None, ge=0, description="Максимальная цена билета")
    is_free: bool | None = Field(default=None, description="Только бесплатные мероприятия")
    age_limit_max: int | None = Field(default=None, ge=0, le=18, description="Максимальный возраст (0, 6, 12, 16, 18)")
    max_duration_min: int | None = Field(default=None, gt=0, description="Максимальная длительность в минутах")
    language: str | None = Field(default=None, description="Язык проведения")
    tags: list[str] | None = Field(default=None, description="Фильтр по тегам")
    page: int = Field(default=1, ge=1, description="Номер страницы")
    page_size: int = Field(default=10, ge=1, le=50, description="Количество карточек на странице")
    sort_by: Literal["date_start", "price_min", "relevance"] = Field(
        default="date_start",
        description="Поле сортировки результатов",
    )


class EmptyResultExplanationDTO(BaseModel):
    """Диагностика пустого результата поиска по требованиям ТЗ."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    is_empty: bool = Field(default=True)
    message: str = Field(..., description="Человекочитаемое объяснение, почему ничего не найдено")
    blocking_constraints: list[str] = Field(
        default_factory=list,
        description="Ограничения, которые заблокировали выдачу (цена, дата, возраст)",
    )
    suggested_relaxations: list[str] = Field(
        default_factory=list,
        description="Рекомендации по ослаблению параметров поиска",
    )


class PaginatedEventsResponseDTO(BaseModel):
    """Ответ каталога с пагинацией и объяснением пустой выдачи."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    items: list[EventCardDTO] = Field(..., description="Найденные мероприятия")
    total: int = Field(..., ge=0, description="Общее количество")
    page: int = Field(..., ge=1, description="Текущая страница")
    page_size: int = Field(..., ge=1, description="Размер страницы")
    empty_explanation: EmptyResultExplanationDTO | None = Field(
        default=None,
        description="Диагностика пустой выдачи при total == 0",
    )
