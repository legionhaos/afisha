import enum


class EventCategory(str, enum.Enum):
    """Категории культурных мероприятий Республики Башкортостан."""
    CONCERT = "concert"        # Концерт
    THEATER = "theater"        # Спектакль
    EXHIBITION = "exhibition"  # Выставка
    FESTIVAL = "festival"      # Фестиваль
    CINEMA = "cinema"          # Кино
    EXCURSION = "excursion"    # Экскурсия
    OTHER = "other"            # Другое


class SourceType(str, enum.Enum):
    """Типы источников данных о мероприятиях."""
    MANUAL = "manual"          # Ручной ввод
    IMPORT = "import"          # Импорт CSV/JSON
    RSS = "rss"                # RSS-лента
    API = "api"                # Внешний API
    PAGE = "page"              # Веб-страница


class EventStatus(str, enum.Enum):
    """Статусы публикации мероприятия."""
    PUBLISHED = "published"    # Опубликовано (в выдаче)
    DRAFT = "draft"            # Черновик (в очереди модерации)
    CANCELLED = "cancelled"    # Отменено (не в поиске, доступно по прямой ссылке с пометкой)


class ModerationReason(str, enum.Enum):
    """Причины отправки карточки в очередь модерации."""
    LOW_CONFIDENCE = "low_confidence"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    POTENTIAL_DUPLICATE = "potential_duplicate"
    PROMPT_INJECTION_SUSPECTED = "prompt_injection_suspected"
    MANUAL_FLAG = "manual_flag"


class FeedbackStatus(str, enum.Enum):
    """Статусы обработки обращений организаторов и жителей."""
    NEW = "new"
    PROCESSED = "processed"
    REJECTED = "rejected"


class SubscriptionChannel(str, enum.Enum):
    """Каналы доставки уведомлений по подпискам."""
    TELEGRAM = "telegram"
    WEB = "web"
