import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.enums import EventCategory

# Timezone Asia/Yekaterinburg (UTC+5) for Bashkortostan
YEKT_TZ = timezone(timedelta(hours=5))

# Regexes for price parsing
PRICE_FREE_REGEX = re.compile(
    r"(?i)(?:^|\s|[.,;!?])(бесплатн\w*|вход\s+свободн\w*|свободный\s+вход|даром|(?<!\d)0\s*(?:руб|р|₽)?)(?:$|\s|[.,;!?])"
)
PRICE_RANGE_REGEX = re.compile(r"(?i)(?:от\s*)?(\d+)\s*(?:до|-|–|—)\s*(\d+)\s*(?:руб|р|₽)?")
PRICE_SINGLE_REGEX = re.compile(r"(?i)(?:от|до|цена:?)?\s*(\d+)\s*(?:руб|р|₽)?")

# Regexes for age parsing
AGE_REGEX = re.compile(r"(?i)(?:возраст:?\s*|для\s+детей\s*)?(\d+)\s*(?:\+|лет|года|год)?")

# Prefix removal for title normalization
TITLE_PREFIXES = [
    "концерт", "спектакль", "выставка", "фестиваль", "экскурсия", "кинопоказ", "мастер-класс", "премьера"
]


class NormalizationService:
    """Сервис нормализации текстовых полей, цен, дат и категорий мероприятий."""

    def normalize_title(self, raw_title: str) -> str:
        """Очищает заголовок от кавычек, префиксов, пометок статуса/дубликатов и приводит к каноническому виду."""
        if not raw_title:
            return ""

        title = raw_title.strip()
        # Замена буквы ё на е
        title = title.replace("ё", "е").replace("Ё", "Е")

        # Удаление служебных пометок статуса и дубликатов в скобках: (ОТМЕНЕНО), (Дубликат из другого источника), [ОТМЕНЕН]
        title = re.sub(r"(?i)\s*[\(\[](?:отменено|отменен|перенесен[оа]|дубликат[^\)\]]*)[\)\]]", "", title)

        # Удаление кавычек
        for q in ['«', '»', '“', '”', '"', "'", '`']:
            title = title.replace(q, "")

        # Удаление лишних пробелов и пунктуации в начале/конце
        title = re.sub(r"\s+", " ", title).strip(" .-,;:!?")

        # Удаление префиксов ("Концерт:", "Спектакль -")
        title_lower = title.lower()
        for prefix in TITLE_PREFIXES:
            if title_lower.startswith(f"{prefix}:") or title_lower.startswith(f"{prefix} -") or title_lower.startswith(f"{prefix} —"):
                parts = re.split(r"[:\-—]", title, maxsplit=1)
                if len(parts) > 1 and parts[1].strip():
                    title = parts[1].strip()
                    break

        return title.strip()

    def parse_price_text(self, raw_price: str | int | float | None) -> tuple[int, int, bool]:
        """Разбирает текстовую формулировку цены в кортеж (price_min, price_max, is_free)."""
        if raw_price is None:
            return (0, 0, False)

        if isinstance(raw_price, (int, float)):
            val = int(raw_price)
            if val <= 0:
                return (0, 0, True)
            return (val, val, False)

        text_val = str(raw_price).strip()
        if not text_val:
            return (0, 0, False)

        # 1. Проверка на бесплатный вход
        if PRICE_FREE_REGEX.search(f" {text_val} "):
            return (0, 0, True)

        # 2. Проверка на диапазон цен ("от 300 до 800 руб")
        range_match = PRICE_RANGE_REGEX.search(text_val)
        if range_match:
            p_min = int(range_match.group(1))
            p_max = int(range_match.group(2))
            if p_min > p_max:
                p_min, p_max = p_max, p_min
            return (p_min, p_max, False)

        # 3. Проверка на единичную цену ("500 руб", "от 300 р", "до 1000")
        single_match = PRICE_SINGLE_REGEX.search(text_val)
        if single_match:
            p = int(single_match.group(1))
            if "до" in text_val.lower() and "от" not in text_val.lower():
                return (0, p, False)
            return (p, p, False)

        return (0, 0, False)

    def parse_date_to_yekaterinburg(self, raw_date: str | datetime | None) -> datetime:
        """Приводит любую дату к часовому поясу Asia/Yekaterinburg (UTC+5)."""
        if raw_date is None:
            raise ValueError("Дата не указана")

        if isinstance(raw_date, datetime):
            if raw_date.tzinfo is None:
                return raw_date.replace(tzinfo=YEKT_TZ)
            return raw_date.astimezone(YEKT_TZ)

        str_date = str(raw_date).strip()
        # Поддержка стандартных форматов
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(str_date, fmt)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=YEKT_TZ)
                return dt.astimezone(YEKT_TZ)
            except ValueError:
                continue

        # ISO parsing fallback
        try:
            dt = datetime.fromisoformat(str_date)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=YEKT_TZ)
            return dt.astimezone(YEKT_TZ)
        except ValueError:
            raise ValueError(f"Не удалось разобрать дату: {str_date}") from None

    def normalize_age_limit(self, raw_age: str | int | None, context_text: str = "") -> int:
        """Округляет возраст к стандартной шкале {0, 6, 12, 16, 18} по требованиям ТЗ."""
        age_val: int = 0

        if isinstance(raw_age, int):
            age_val = raw_age
        elif isinstance(raw_age, str) and raw_age.strip():
            if re.match(r"\s*-\s*\d", raw_age):
                raise ValueError("Возрастное ограничение не может быть отрицательным")
            match = AGE_REGEX.search(raw_age)
            if not match:
                raise ValueError("Не удалось разобрать возрастное ограничение")
            age_val = int(match.group(1))
        elif raw_age is not None and not isinstance(raw_age, str):
            raise ValueError("Некорректное возрастное ограничение")
        if age_val < 0 or age_val > 18:
            raise ValueError("Возрастное ограничение вне диапазона 0–18")

        # Приведение к допустимым значениям 0, 6, 12, 16, 18
        if age_val <= 0:
            return 0
        elif age_val <= 6:
            return 6
        elif age_val <= 12:
            return 12
        elif age_val <= 16:
            return 16
        else:
            return 18

    def normalize_category(
        self,
        raw_category: str | None,
        title: str,
        description: str,
    ) -> tuple[EventCategory, list[str]]:
        """Сопоставляет категорию по синонимам и генерирует теги."""
        combined = f"{raw_category or ''} {title} {description}".lower()
        tags: list[str] = []

        if any(w in combined for w in ["дет", "ребен", "семь", "сказк", "кукольн"]):
            tags.append("дети")
        if any(w in combined for w in ["пушкинск"]):
            tags.append("пушкинская_карта")
        if any(w in combined for w in ["башкирск", "курултай", "сабантуй", "курай"]):
            tags.append("башкирская_культура")
        if any(w in combined for w in ["джаз", "jazz"]):
            tags.append("джаз")
        if any(w in combined for w in ["рок", "rock"]):
            tags.append("рок")
        if any(w in combined for w in ["классическ", "симфони"]):
            tags.append("классика")

        if any(w in combined for w in ["концерт", "оркестр", "филармон", "музык", "песн", "хор"]):
            return EventCategory.CONCERT, tags
        elif any(w in combined for w in ["спектакл", "театр", "драм", "комеди", "балет", "опер"]):
            return EventCategory.THEATER, tags
        elif any(w in combined for w in ["выставк", "музей", "галере", "экспозици"]):
            return EventCategory.EXHIBITION, tags
        elif any(w in combined for w in ["фестивал", "ярмарк", "праздник"]):
            return EventCategory.FESTIVAL, tags
        elif any(w in combined for w in ["кино", "фильм", "кинопоказ"]):
            return EventCategory.CINEMA, tags
        elif any(w in combined for w in ["экскурси", "тур", "поездк"]):
            return EventCategory.EXCURSION, tags

        return EventCategory.OTHER, tags


normalization_service = NormalizationService()
