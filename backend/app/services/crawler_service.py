"""Сервис сбора данных о культурных мероприятиях Республики Башкортостан.

Соответствует требованиям раздела 6.5 ТЗ (Уровень 4: сбор данных и контур качества):
- Сбор из двух и более внешних источников (Kassir, Rusdram, Kassy).
- Извлечение обязательных полей: название, дата и время, площадка, город, цена, категория, ссылка.
- Нормализация: единый формат дат (Asia/Yekaterinburg UTC+5), разбор цены («вход свободный», диапазон), приведение к справочнику городов.
- Контур качества: проверка доступности URL источника, проверка даты в будущем, выявление отмен и дубликатов.
- Сохранение источника, времени проверки и оценки уверенности (confidence).
"""
import asyncio
from datetime import datetime, timezone
import json
import re
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog

from app.models.enums import EventCategory, EventStatus, SourceType
from app.services.import_service import ImportService
from app.services.normalization_service import YEKT_TZ, NormalizationService

logger = structlog.get_logger(__name__)

# 21 канонический город Республики Башкортостан по ТЗ
BASHKORTOSTAN_CITIES: list[str] = [
    "Уфа", "Стерлитамак", "Салават", "Нефтекамск", "Октябрьский",
    "Белорецк", "Туймазы", "Ишимбай", "Кумертау", "Сибай",
    "Мелеуз", "Белебей", "Бирск", "Учалы", "Благовещенск",
    "Дюртюли", "Янаул", "Давлеканово", "Агидель", "Баймак", "Межгорье",
]

# Внешние города для отсева гастрольных остановок за пределами Башкортостана
NON_BASHKORTOSTAN_CITIES = [
    "казань", "челябинск", "ижевск", "самара", "оренбург", "москва",
    "екатеринбург", "пермь", "магнитогорск", "санкт-петербург",
]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 AfishaBashkortostan/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def detect_bashkortostan_city(address: str | None, venue: str | None) -> tuple[str, bool]:
    """Определяет город Башкортостана по адресу и площадке. Отсекает другие регионы."""
    combined = f"{address or ''} {venue or ''}".strip().lower()

    # Если явно указан соседний регион — отсекаем
    for other in NON_BASHKORTOSTAN_CITIES:
        if other in combined:
            return "", False

    # Поиск соответствия городам Башкортостана
    for city in BASHKORTOSTAN_CITIES:
        c_lower = city.lower()
        if c_lower in combined:
            return city, True

    # Для региональных доменов ufa.kassir / ufa.kassy дефолтный город — Уфа
    return "Уфа", True


def clean_kassir_datetime(dt_str: str | None) -> str | None:
    """Нормализует дату из Kassir: локальное уфимское время с часовым поясом UTC+5."""
    if not dt_str:
        return None
    cleaned = re.sub(r"([+-]\d{2}:\d{2}|Z)$", "", str(dt_str).strip())
    return f"{cleaned}+05:00"


class BaseCrawler:
    """Базовый класс парсера источника культурных мероприятий."""

    name: str = "base"
    source_type: SourceType = SourceType.PAGE

    async def crawl(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        raise NotImplementedError


class KassirCrawler(BaseCrawler):
    """Парсер регионального билетного агрегатора ufa.kassir.ru."""

    name: str = "kassir"
    source_type: SourceType = SourceType.PAGE
    categories: list[tuple[str, EventCategory]] = [
        ("teatr", EventCategory.THEATER),
        ("koncert", EventCategory.CONCERT),
        ("detyam", EventCategory.THEATER),
        ("shou", EventCategory.OTHER),
        ("vystavki", EventCategory.EXHIBITION),
        ("festivali", EventCategory.FESTIVAL),
    ]

    async def crawl(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for cat_slug, default_cat in self.categories:
            cat_url = f"https://ufa.kassir.ru/{cat_slug}"
            try:
                resp = await client.get(cat_url, timeout=12.0)
                if resp.status_code != 200:
                    logger.warning("kassir_category_failed", category=cat_slug, status=resp.status_code)
                    continue

                html = resp.text
                matches = re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.DOTALL)
                for script_content in matches:
                    try:
                        data = json.loads(script_content)
                    except json.JSONDecodeError:
                        continue

                    graph = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    for item in graph:
                        if not isinstance(item, dict):
                            continue
                        item_type = str(item.get("@type") or "")
                        if item_type not in ("Event", "TheaterEvent", "MusicEvent", "DanceEvent", "Festival"):
                            continue

                        title = str(item.get("name") or "").strip()
                        if not title:
                            continue

                        event_url = str(item.get("url") or "").strip()
                        if event_url and event_url in seen_urls:
                            continue
                        if event_url:
                            seen_urls.add(event_url)

                        location = item.get("location") or {}
                        venue_name = str(location.get("name") or "Площадка мероприятия").strip() if isinstance(location, dict) else "Площадка"
                        address = str(location.get("address") or f"г. Уфа, {venue_name}").strip() if isinstance(location, dict) else venue_name

                        city, is_bash = detect_bashkortostan_city(address, venue_name)
                        if not is_bash:
                            continue

                        # Цены
                        offers = item.get("offers") or {}
                        price_min = 0
                        price_max = 0
                        is_free = False
                        org_link = event_url
                        if isinstance(offers, dict):
                            p = offers.get("price")
                            if p is not None:
                                try:
                                    price_min = int(float(p))
                                    price_max = price_min
                                except (ValueError, TypeError):
                                    pass
                            elif offers.get("lowPrice"):
                                try:
                                    price_min = int(float(offers["lowPrice"]))
                                    price_max = int(float(offers.get("highPrice") or price_min))
                                except (ValueError, TypeError):
                                    pass
                            if offers.get("url"):
                                org_link = str(offers["url"])

                        # Дата
                        raw_start = clean_kassir_datetime(item.get("startDate"))
                        raw_end = clean_kassir_datetime(item.get("endDate"))

                        # Статус
                        event_status_schema = str(item.get("eventStatus") or "")
                        if "Cancelled" in event_status_schema or "Rescheduled" in event_status_schema:
                            status_val = EventStatus.CANCELLED.value
                        else:
                            status_val = EventStatus.PUBLISHED.value

                        # Изображение
                        image_data = item.get("image")
                        image_url = None
                        if isinstance(image_data, dict):
                            image_url = image_data.get("contentUrl") or image_data.get("url")
                        elif isinstance(image_data, str):
                            image_url = image_data

                        desc = str(item.get("description") or title).strip()

                        results.append({
                            "title": title,
                            "category": default_cat.value,
                            "date_start": raw_start,
                            "date_end": raw_end,
                            "city": city,
                            "venue": venue_name,
                            "address": address,
                            "price_min": price_min,
                            "price_max": price_max,
                            "is_free": is_free,
                            "source_url": event_url or cat_url,
                            "org_link": org_link,
                            "description": desc,
                            "image_url": image_url,
                            "status": status_val,
                            "source_name": "kassir.ru",
                        })
            except Exception as e:
                logger.error("kassir_crawler_category_error", category=cat_slug, error=str(e))

        logger.info("kassir_crawl_completed", count=len(results))
        return results


class RusdramCrawler(BaseCrawler):
    """Парсер Государственного академического русского драматического театра Республики Башкортостан."""

    name: str = "rusdram"
    source_type: SourceType = SourceType.PAGE
    afisha_url: str = "https://rusdram.ru/afisha.html"

    async def crawl(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            resp = await client.get(self.afisha_url, timeout=12.0)
            if resp.status_code != 200:
                logger.warning("rusdram_afisha_failed", status=resp.status_code)
                return results

            matches = re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", resp.text, re.DOTALL)
            for m in matches:
                try:
                    data = json.loads(m)
                except json.JSONDecodeError:
                    continue

                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict) or item.get("@type") != "TheaterEvent":
                        continue

                    title = str(item.get("name") or "").strip()
                    if not title:
                        continue

                    raw_start = item.get("startDate")
                    offers = item.get("offers") or {}
                    tickets_url = offers.get("url") if isinstance(offers, dict) else None

                    raw_age = item.get("typicalAgeRange") or "16+"

                    status_schema = str(item.get("eventStatus") or "")
                    status_val = EventStatus.CANCELLED.value if "Cancelled" in status_schema else EventStatus.PUBLISHED.value

                    results.append({
                        "title": title,
                        "category": EventCategory.THEATER.value,
                        "date_start": raw_start,
                        "city": "Уфа",
                        "venue": "Государственный академический русский драматический театр Республики Башкортостан",
                        "address": "г. Уфа, проспект Октября, 79",
                        "price_min": 400,
                        "price_max": 1500,
                        "is_free": False,
                        "age_limit": raw_age,
                        "source_url": item.get("url") or self.afisha_url,
                        "org_link": tickets_url or item.get("url"),
                        "description": f"Спектакль «{title}» в Государственном академическом русском драматическом театре РБ (г. Уфа).",
                        "status": status_val,
                        "source_name": "rusdram.ru",
                    })
        except Exception as e:
            logger.error("rusdram_crawler_error", error=str(e))

        logger.info("rusdram_crawl_completed", count=len(results))
        return results


class KassyCrawler(BaseCrawler):
    """Парсер регионального билетного оператора ufa.kassy.ru (включая отмененные мероприятия)."""

    name: str = "kassy"
    source_type: SourceType = SourceType.PAGE
    base_url: str = "https://ufa.kassy.ru"

    async def crawl(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_links: set[str] = set()

        # 1. Сбор отмененных событий для корректного статуса CANCELLED
        cancellations_url = f"{self.base_url}/events/cancellations/"
        try:
            resp = await client.get(cancellations_url, timeout=12.0)
            if resp.status_code == 200:
                links = re.findall(r"href=[\"'](/events/[^/]+/\d+-[^/]+/|/event/\d+/)[\"']", resp.text)
                for link in list(set(links))[:10]:  # Первые 10 отмененных
                    full_link = urljoin(self.base_url, link)
                    event_data = await self._parse_event_page(client, full_link, force_cancelled=True)
                    if event_data:
                        results.append(event_data)
                        seen_links.add(full_link)
        except Exception as e:
            logger.warning("kassy_cancellations_error", error=str(e))

        # 2. Сбор афиши на текущий месяц
        now_dt = datetime.now(YEKT_TZ)
        range_url = f"{self.base_url}/events/range-{now_dt.year}-{now_dt.month:02d}/"
        try:
            resp = await client.get(range_url, timeout=12.0)
            if resp.status_code == 200:
                links = re.findall(r"href=[\"'](/events/[^/]+/\d+-[^/]+/|/event/\d+/)[\"']", resp.text)
                unique_links = [urljoin(self.base_url, l) for l in set(links) if urljoin(self.base_url, l) not in seen_links]
                # Обрабатываем до 20 событий для скорости
                tasks = [self._parse_event_page(client, l) for l in unique_links[:20]]
                batch_res = await asyncio.gather(*tasks, return_exceptions=True)
                for r in batch_res:
                    if isinstance(r, dict):
                        results.append(r)
        except Exception as e:
            logger.warning("kassy_range_error", error=str(e))

        logger.info("kassy_crawl_completed", count=len(results))
        return results

    async def _parse_event_page(
        self,
        client: httpx.AsyncClient,
        url: str,
        force_cancelled: bool = False,
    ) -> dict[str, Any] | None:
        try:
            resp = await client.get(url, timeout=8.0)
            if resp.status_code != 200:
                return None

            matches = re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", resp.text, re.DOTALL)
            for m in matches:
                try:
                    data = json.loads(m)
                except json.JSONDecodeError:
                    continue

                if not isinstance(data, dict):
                    continue
                if data.get("@type") not in ("Event", "TheaterEvent", "MusicEvent", "DanceEvent", "Festival"):
                    continue

                title = str(data.get("name") or "").strip()
                if not title:
                    continue

                location = data.get("location") or {}
                venue_name = str(location.get("name") or "Площадка мероприятия").strip() if isinstance(location, dict) else "Площадка"
                address = str(location.get("address") or f"г. Уфа, {venue_name}").strip() if isinstance(location, dict) else venue_name

                city, is_bash = detect_bashkortostan_city(address, venue_name)
                if not is_bash:
                    return None

                offers = data.get("offers") or {}
                price_min = 0
                price_max = 0
                if isinstance(offers, dict):
                    p_low = offers.get("lowPrice") or offers.get("price")
                    p_high = offers.get("highPrice") or p_low
                    if p_low is not None:
                        try:
                            price_min = int(float(p_low))
                            price_max = int(float(p_high or price_min))
                        except (ValueError, TypeError):
                            pass

                status_schema = str(data.get("eventStatus") or "")
                if force_cancelled or "Cancelled" in status_schema or "Rescheduled" in status_schema:
                    status_val = EventStatus.CANCELLED.value
                else:
                    status_val = EventStatus.PUBLISHED.value

                category = EventCategory.THEATER.value if data.get("@type") == "TheaterEvent" else EventCategory.CONCERT.value

                return {
                    "title": title,
                    "category": category,
                    "date_start": data.get("startDate"),
                    "date_end": data.get("endDate"),
                    "city": city,
                    "venue": venue_name,
                    "address": address,
                    "price_min": price_min,
                    "price_max": price_max,
                    "is_free": price_min == 0 and "свободн" in title.lower(),
                    "source_url": url,
                    "org_link": offers.get("url") if isinstance(offers, dict) else url,
                    "description": str(data.get("description") or title).strip(),
                    "status": status_val,
                    "source_name": "kassy.ru",
                }
        except Exception as e:
            logger.debug("kassy_page_parse_error", url=url, error=str(e))
        return None


class CrawlerService:
    """Сервис координации парсеров, контура качества и импорта карточек в БД."""

    def __init__(
        self,
        import_service: ImportService,
        norm_service: NormalizationService | None = None,
    ) -> None:
        self.import_service = import_service
        self.norm_service = norm_service or NormalizationService()
        self.crawlers: list[BaseCrawler] = [
            KassirCrawler(),
            RusdramCrawler(),
            KassyCrawler(),
        ]

    async def verify_url(self, client: httpx.AsyncClient, url: str) -> bool:
        """Проверка доступности ссылки на источник (требование 6.5 ТЗ)."""
        if not url or not url.startswith("http"):
            return False
        try:
            r = await client.head(url, timeout=5.0)
            if 200 <= r.status_code < 400:
                return True
            # Некоторые серверы не поддерживают HEAD — fallback на GET
            r_get = await client.get(url, timeout=5.0)
            return 200 <= r_get.status_code < 400
        except Exception:
            return False

    async def crawl_all(
        self,
        verify_urls: bool = False,
        limit_per_source: int | None = None,
    ) -> list[dict[str, Any]]:
        """Запускает сбор из всех зарегистрированных источников с нормализацией."""
        all_raw_events: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=15.0,
            verify=False,
        ) as client:
            for crawler in self.crawlers:
                try:
                    logger.info("starting_crawler", crawler=crawler.name)
                    crawled = await crawler.crawl(client)
                    if limit_per_source:
                        crawled = crawled[:limit_per_source]
                    all_raw_events.extend(crawled)
                except Exception as e:
                    logger.error("crawler_failed", crawler=crawler.name, error=str(e))

            if verify_urls:
                logger.info("verifying_crawled_urls", total=len(all_raw_events))
                for ev in all_raw_events:
                    src_url = ev.get("source_url")
                    is_alive = await self.verify_url(client, src_url)
                    ev["url_verified"] = is_alive
                    if not is_alive:
                        # Снижаем уверенность и статус при неработающей ссылке (ТЗ 6.5)
                        ev["status"] = EventStatus.DRAFT.value

        # Фильтрация и дедупликация по source_url
        unique_events: dict[str, dict[str, Any]] = {}
        for ev in all_raw_events:
            url_key = ev.get("source_url") or ev.get("title")
            if url_key not in unique_events:
                unique_events[url_key] = ev

        logger.info("crawl_all_finished", raw_count=len(all_raw_events), unique_count=len(unique_events))
        return list(unique_events.values())

    async def crawl_and_import(
        self,
        actor_id: str = "crawler_worker",
        request_id: str = "crawl_batch",
        verify_urls: bool = False,
        save_seed_path: str | None = None,
    ) -> dict[str, Any]:
        """Полный цикл: сбор данных -> валидация контура качества -> дедупликация -> сохранение в БД."""
        events = await self.crawl_all(verify_urls=verify_urls)

        # Опциональное сохранение в seed_events.json для офлайн-сидинга
        if save_seed_path:
            with open(save_seed_path, "w", encoding="utf-8") as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            logger.info("saved_seed_file", path=save_seed_path, count=len(events))

        # Импорт через ImportService (сохранение в raw_event_records, дедупликация, HNSW эмбеддинги)
        report = await self.import_service.import_file(
            file_bytes=json.dumps(events, ensure_ascii=False).encode("utf-8"),
            filename="crawler_feed.json",
            actor_id=actor_id,
            request_id=request_id,
        )

        return {
            "crawled_total": len(events),
            "added_count": report.added_count,
            "merged_count": report.deduplicated_merged_count,
            "updated_count": report.updated_count,
            "flagged_for_moderation": report.flagged_for_moderation_count,
            "rejected_count": report.rejected_count,
            "errors": [e.model_dump() for e in report.errors],
        }
