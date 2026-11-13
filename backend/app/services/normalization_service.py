import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.models.enums import EventCategory, ModerationReason


YEKT_TZ = ZoneInfo("Asia/Yekaterinburg")


class NormalizationService:
    def normalize_title(self, raw_title: str) -> str:
        text = raw_title.lower().replace("ё", "е")
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        text = re.sub(r"^(?:(?:концерт|спектакль|премьера)\b\s*)+", "", text.strip())
        return " ".join(text.split())

    def parse_price_string(self, raw_price: str | int | None) -> tuple[int, int, bool]:
        if raw_price is None or str(raw_price).strip() == "":
            raise ValueError("Цена не указана")
        text = str(raw_price).lower().replace(" ", " ")
        if re.search(r"бесплатн|вход\s+свободн", text):
            if re.search(r"\d", text):
                raise ValueError("Противоречивое указание цены")
            return 0, 0, True
        if re.match(r"\s*-\s*\d", text):
            raise ValueError("Цена не может быть отрицательной")
        # Spaces between thousands are accepted only in groups of exactly three.
        numbers = re.findall(r"\d{1,3}(?:[  ]\d{3})+|\d+", text)
        if re.search(r"\d[.,]\d", text):
            raise ValueError("Дробная цена не поддерживается")
        if not 1 <= len(numbers) <= 2:
            raise ValueError("Не удалось разобрать цену")
        if len(numbers) == 1 and re.search(r"\b(?:от|до)\s*\d", text):
            raise ValueError("Цена содержит только одну границу диапазона")
        values = [int(re.sub(r"\s", "", value)) for value in numbers]
        if len(values) == 2 and values[0] > values[1]:
            raise ValueError("Минимальная цена больше максимальной")
        low, high = values[0], values[-1]
        if high > 2_147_483_647:
            raise ValueError("Цена превышает допустимый диапазон")
        return low, high, high == 0

    def parse_date_range(
        self, raw_date_start: str, raw_date_end: str | None
    ) -> tuple[datetime, datetime | None]:
        zone = YEKT_TZ

        def parse(value: str) -> datetime:
            try:
                result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
                    try:
                        result = datetime.strptime(value.strip(), fmt)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError(f"Не удалось разобрать дату: {value}") from None
            return result.replace(tzinfo=zone) if result.tzinfo is None else result.astimezone(zone)

        start = parse(raw_date_start)
        end = parse(raw_date_end) if raw_date_end else None
        if end is not None and end < start:
            raise ValueError("Дата окончания раньше даты начала")
        return start, end

    def parse_date_to_yekaterinburg(self, raw_date: str | datetime) -> datetime:
        if isinstance(raw_date, datetime):
            return raw_date.replace(tzinfo=YEKT_TZ) if raw_date.tzinfo is None else raw_date.astimezone(YEKT_TZ)
        return self.parse_date_range(raw_date, None)[0]

    def parse_price_text(self, raw_price: str | int | None) -> tuple[int, int, bool]:
        return self.parse_price_string(raw_price)

    def normalize_category(
        self, raw_category: str, title: str, description: str
    ) -> tuple[EventCategory, list[str]]:
        text = " ".join((raw_category or "", title or "", description or "")).lower().replace("ё", "е")
        synonyms = {
            EventCategory.CONCERT: ("концерт", "музыкальн", "симфоническ"),
            EventCategory.THEATER: ("театр", "спектакл", "постановк"),
            EventCategory.EXHIBITION: ("выставк", "экспозиц"),
            EventCategory.FESTIVAL: ("фестивал",),
            EventCategory.CINEMA: ("кино", "фильм", "кинопоказ"),
            EventCategory.EXCURSION: ("экскурси",),
        }
        declared = (raw_category or "").lower().replace("ё", "е")
        category = next((item for item, words in synonyms.items() if any(word in declared for word in words)), None)
        if category is None:
            category = next((item for item, words in synonyms.items() if any(word in text for word in words)), EventCategory.OTHER)
        tags = ["дети"] if re.search(r"детск|ребен|утренник", text) else []
        return category, tags

    def normalize_age_limit(self, raw_age: str | int | None) -> int:
        if raw_age is None or str(raw_age).strip() == "":
            return 0
        match = re.fullmatch(r"\s*(0|6|12|16|18)\s*\+?\s*", str(raw_age))
        if match is None:
            raise ValueError("Некорректное возрастное ограничение")
        return int(match.group(1))

    async def normalize_raw_payload(
        self, raw_payload: dict[str, Any], dict_repo: Any
    ) -> tuple[dict[str, Any], float, ModerationReason | None]:
        data = dict(raw_payload)
        required = ("title", "date_start", "city", "venue", "address", "description", "source_url")
        missing = [field for field in required if data.get(field) is None or not str(data[field]).strip()]
        if missing:
            raise ValueError(f"Отсутствуют обязательные поля: {', '.join(missing)}")
        for field in required:
            if not isinstance(data[field], str):
                raise ValueError(f"Поле {field} должно быть строкой")
            data[field] = data[field].strip()
        for field, limit in (("city", 120), ("venue", 255)):
            if len(data[field]) > limit:
                raise ValueError(f"Поле {field} превышает {limit} символов")
        data["normalized_title"] = self.normalize_title(str(data["title"]))
        if not data["normalized_title"]:
            raise ValueError("Название не содержит смыслового текста")
        data["date_start"], data["date_end"] = self.parse_date_range(
            str(data["date_start"]), str(data["date_end"]) if data.get("date_end") else None
        )
        price = data.get("price")
        if price is None or price == "":
            price = data.get("price_min")
            if price is not None and data.get("price_max") not in (None, ""):
                price = f"{price} - {data['price_max']}"
        data["price_min"], data["price_max"], data["is_free"] = self.parse_price_string(price)
        if data.get("duration_min") not in (None, ""):
            data["duration_min"] = int(data["duration_min"])
            if not 0 < data["duration_min"] <= 2_147_483_647:
                raise ValueError("Продолжительность вне допустимого диапазона")
        else:
            data["duration_min"] = None
        for field, minimum, maximum in (("lat", -90, 90), ("lon", -180, 180)):
            value = data.get(field)
            if value is None or str(value).strip() == "":
                data[field] = None
                continue
            try:
                coordinate = Decimal(str(value).strip().replace(",", "."))
                if not coordinate.is_finite() or not minimum <= coordinate <= maximum:
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise ValueError(f"Некорректная координата {field}") from None
            data[field] = coordinate
        for field in ("language", "org_link"):
            value = data.get(field)
            data[field] = str(value).strip() if value is not None and str(value).strip() else None
        if data["language"] and len(data["language"]) > 64:
            raise ValueError("Поле language превышает 64 символа")
        raw_category = data.get("category") or ""
        try:
            category = EventCategory(str(raw_category).lower())
            _, tags = self.normalize_category("", str(data["title"]), str(data["description"]))
        except ValueError:
            category, tags = self.normalize_category(str(raw_category), str(data["title"]), str(data["description"]))
        data["category"] = category
        original_tags = data.get("tags") or []
        if isinstance(original_tags, str):
            original_tags = [tag.strip() for tag in original_tags.split(",") if tag.strip()]
        if not isinstance(original_tags, list) or any(not isinstance(tag, str) for tag in original_tags):
            raise ValueError("Теги должны быть списком строк")
        data["tags"] = list(dict.fromkeys([*(tag.strip() for tag in original_tags if tag.strip()), *tags]))
        data["age_limit"] = self.normalize_age_limit(data.get("age_limit"))
        city = await dict_repo.resolve_city_name(str(data["city"]))
        confidence = 1.0 if city else 0.7
        if city:
            data["city"] = city
        reason = ModerationReason.LOW_CONFIDENCE if city is None else None
        return data, confidence, reason


normalization_service = NormalizationService()
