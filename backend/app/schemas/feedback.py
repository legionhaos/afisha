from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from app.models.enums import FeedbackStatus


class FeedbackCreateDTO(BaseModel):
    """Схема отправки обращения от организатора или жителя."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    event_id: UUID | None = Field(default=None, description="ID мероприятия, если обращение связано с ним")
    sender_identifier: str = Field(..., min_length=2, max_length=128, description="Идентификатор отправителя")
    message_text: str = Field(..., min_length=10, max_length=2000, description="Текст сообщения или уточнения")
    honeypot: str = Field(default="", description="Ловушка для спам-ботов, должна оставаться пустой")


class FeedbackReadDTO(BaseModel):
    """Схема чтения обратной связи."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID = Field(..., description="ID тикета")
    event_id: UUID | None = Field(default=None, description="Связанное мероприятие")
    sender_identifier: str = Field(..., description="Отправитель")
    message_text: str = Field(..., description="Текст обращения")
    status: FeedbackStatus = Field(default=FeedbackStatus.NEW, description="Статус обработки")
    created_at: AwareDatetime = Field(..., description="Время подачи обращения")
