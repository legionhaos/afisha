from enum import Enum


class EventCategory(str, Enum):
    CONCERT = "concert"
    THEATER = "theater"
    EXHIBITION = "exhibition"
    FESTIVAL = "festival"
    CINEMA = "cinema"
    EXCURSION = "excursion"
    OTHER = "other"


class SourceType(str, Enum):
    MANUAL = "manual"
    IMPORT = "import"
    RSS = "rss"
    API = "api"
    PAGE = "page"


class EventStatus(str, Enum):
    PUBLISHED = "published"
    DRAFT = "draft"
    CANCELLED = "cancelled"


class ModerationReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    POTENTIAL_DUPLICATE = "potential_duplicate"
    PROMPT_INJECTION_SUSPECTED = "prompt_injection_suspected"
    MANUAL_FLAG = "manual_flag"


class SubscriptionChannel(str, Enum):
    TELEGRAM = "telegram"
    WEB = "web"


class FeedbackStatus(str, Enum):
    NEW = "new"
    PROCESSED = "processed"
    REJECTED = "rejected"
