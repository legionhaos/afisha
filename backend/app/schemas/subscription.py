from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from app.models.enums import EventCategory


class SubscriptionCreateDTO(BaseModel):
    """Схема создания подписки пользователя без лишних ПДн (152-ФЗ)."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    user_identifier: str = Field(..., min_length=2, max_length=128, description="Хеш или анонимный ID пользователя")
    telegram_chat_id: int | None = Field(default=None, description="BIGINT Telegram chat ID (64-bit safe)")
    city: str = Field(..., min_length=2, max_length=120, description="Город подписки")
    category: EventCategory | None = Field(default=None, description="Категория (None - все категории)")
    period_type: str = Field(default="all", description="Периодичность: weekend, all")


class SubscriptionReadDTO(BaseModel):
    """Схема чтения подписки пользователя."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID = Field(..., description="ID подписки")
    user_identifier: str = Field(..., description="Идентификатор пользователя")
    telegram_chat_id: int | None = Field(default=None, description="BIGINT ID чата Telegram")
    city: str = Field(..., description="Город подписки")
    category: EventCategory | None = Field(default=None, description="Категория")
    period_type: str = Field(..., description="Периодичность")
    is_active: bool = Field(default=True, description="Статус активности")
    created_at: AwareDatetime = Field(..., description="Время создания подписки")
    expires_at: AwareDatetime = Field(..., description="Время истечения подписки")
