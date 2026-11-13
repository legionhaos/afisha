from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.event import EventCardDTO


class ChatMessageRequestDTO(BaseModel):
    """Входной запрос к интеллектуальному ИИ-агенту."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    thread_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Идентификатор сессии диалога (short-term memory)",
    )
    user_identifier: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Анонимизированный идентификатор пользователя",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Свободный текст запроса пользователя",
    )
    confirm_action_id: str | None = Field(
        default=None,
        description="Токен подтверждения изменения данных (двухфазная мутация)",
    )


class AgentRecommendationItemDTO(BaseModel):
    """Рекомендация мероприятия с обоснованием соответствия ограничениям."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    event: EventCardDTO = Field(..., description="Карточка мероприятия")
    constraint_match_explanation: str = Field(
        ...,
        description="Объяснение, каким именно ограничениям пользователя соответствует карточка",
    )


class ChatMessageResponseDTO(BaseModel):
    """Финальный ответ ИИ-агента с карточками и обоснованием."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    thread_id: str = Field(..., description="ID сессии диалога")
    trace_id: UUID = Field(..., description="Идентификатор сохраненной трассы выполнения агента")
    reply_text: str = Field(..., description="Текстовый ответ агента")
    recommendations: list[AgentRecommendationItemDTO] = Field(
        default_factory=list,
        description="Список рекомендованных мероприятий (до 5 штук)",
    )
    clarifying_question: str | None = Field(
        default=None,
        description="Ровно 1 уточняющий вопрос при неоднозначности параметров",
    )
    requires_confirmation: bool = Field(
        default=False,
        description="Требуется ли явное подтверждение пользователя для изменения данных",
    )
    pending_action_id: str | None = Field(
        default=None,
        description="Идентификатор отложенного действия (подписка / обратная связь)",
    )
    pending_action_summary: str | None = Field(
        default=None,
        description="Описание требующего подтверждения действия на русском языке",
    )
    is_fallback_mode: bool = Field(
        default=False,
        description="Флаг активации резервного детерминированного поиска без LLM",
    )
    fallback_notice: str | None = Field(
        default=None,
        description="Предупреждение о переходе в резервный режим при сбое модели",
    )
    data_grounded_badge: str = Field(
        default="Ответ построен исключительно по проверенным данным сервиса",
        description="Гарантия отсутствия галлюцинаций (Zero Hallucination Policy)",
    )
