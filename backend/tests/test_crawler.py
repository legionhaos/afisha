import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models.enums import EventCategory, EventStatus
from app.services.crawler_service import (
    CrawlerService,
    KassirCrawler,
    KassyCrawler,
    RusdramCrawler,
    clean_kassir_datetime,
    detect_bashkortostan_city,
)


def test_detect_bashkortostan_city():
    # Города Башкортостана
    city, is_bash = detect_bashkortostan_city("г. Стерлитамак, пр. Ленина 2", "ГДК Стерлитамак")
    assert is_bash is True
    assert city == "Стерлитамак"

    city, is_bash = detect_bashkortostan_city("г. Уфа, ул. Ленина, 114", "Уфа-Арена")
    assert is_bash is True
    assert city == "Уфа"

    city, is_bash = detect_bashkortostan_city("Ишимбай, пр. Октября 10", "ДК Нефтяник")
    assert is_bash is True
    assert city == "Ишимбай"

    # Внешние города должны отсеиваться
    city, is_bash = detect_bashkortostan_city("г. Казань, Площадь Тысячелетия 2", "Татнефть Арена")
    assert is_bash is False

    city, is_bash = detect_bashkortostan_city("Челябинск, Копейское шоссе 64", "ТРЦ Алмаз")
    assert is_bash is False

    city, is_bash = detect_bashkortostan_city("г. Самара, ул. Мичурина", "Экспо-Волга")
    assert is_bash is False


def test_clean_kassir_datetime():
    # Kassir Nuxt сериализует уфимское время со смещением +00:00 или Z
    raw_date = "2026-11-28T19:00:00+00:00"
    cleaned = clean_kassir_datetime(raw_date)
    assert cleaned == "2026-11-28T19:00:00+05:00"

    raw_date_z = "2026-12-05T18:30:00Z"
    cleaned_z = clean_kassir_datetime(raw_date_z)
    assert cleaned_z == "2026-12-05T18:30:00+05:00"

    assert clean_kassir_datetime(None) is None


@pytest.mark.asyncio
async def test_kassir_crawler_parses_json_ld():
    crawler = KassirCrawler()

    mock_json_ld = {
        "@graph": [
            {
                "@type": "Event",
                "name": "Концерт Земфиры",
                "startDate": "2026-11-20T19:00:00+00:00",
                "endDate": "2026-11-20T21:00:00+00:00",
                "eventStatus": "https://schema.org/EventScheduled",
                "url": "https://ufa.kassir.ru/koncert/zemfira",
                "location": {
                    "@type": "Place",
                    "name": "Уфа-Арена",
                    "address": "г. Уфа, ул. Ленина, 114",
                },
                "offers": {
                    "@type": "Offer",
                    "price": 3500,
                    "url": "https://ufa.kassir.ru/koncert/zemfira/buy",
                },
                "description": "Большой сольный концерт в Уфе",
            }
        ]
    }

    html = f"""
    <html>
      <head>
        <script type="application/ld+json">{json.dumps(mock_json_ld)}</script>
      </head>
      <body>Контент</body>
    </html>
    """

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    mock_client.get.return_value = mock_resp

    with patch.object(crawler, "categories", [("koncert", EventCategory.CONCERT)]):
        results = await crawler.crawl(mock_client)

    assert len(results) == 1
    ev = results[0]
    assert ev["title"] == "Концерт Земфиры"
    assert ev["city"] == "Уфа"
    assert ev["venue"] == "Уфа-Арена"
    assert ev["price_min"] == 3500
    assert ev["status"] == EventStatus.PUBLISHED.value
    assert ev["date_start"] == "2026-11-20T19:00:00+05:00"


@pytest.mark.asyncio
async def test_rusdram_crawler_parses_theater_events():
    crawler = RusdramCrawler()

    mock_theater_event = {
        "@context": "https://schema.org",
        "@type": "TheaterEvent",
        "name": "Маскарад",
        "startDate": "2026-11-25T18:00:00+05:00",
        "typicalAgeRange": "16+",
        "eventStatus": "https://schema.org/EventScheduled",
        "url": "https://rusdram.ru/spektakli/maskarad.html",
        "offers": {
            "@type": "Offer",
            "url": "https://ufa.kassy.ru/events/teatr/2-1234/buy/",
        },
    }

    html = f"""
    <html>
      <head>
        <script type="application/ld+json">{json.dumps(mock_theater_event)}</script>
      </head>
      <body>Афиша Русдрам</body>
    </html>
    """

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    mock_client.get.return_value = mock_resp

    results = await crawler.crawl(mock_client)

    assert len(results) == 1
    ev = results[0]
    assert ev["title"] == "Маскарад"
    assert ev["category"] == EventCategory.THEATER.value
    assert ev["city"] == "Уфа"
    assert ev["age_limit"] == "16+"
    assert ev["venue"] == "Государственный академический русский драматический театр Республики Башкортостан"
    assert ev["status"] == EventStatus.PUBLISHED.value


@pytest.mark.asyncio
async def test_kassy_crawler_marks_cancellations():
    crawler = KassyCrawler()

    mock_event_json = {
        "@type": "TheaterEvent",
        "name": "Отмененный спектакль",
        "startDate": "2026-11-30T19:00:00+05:00",
        "eventStatus": "https://schema.org/EventCancelled",
        "location": {
            "name": "Театр оперы и балета",
            "address": "г. Уфа, ул. Ленина, 5",
        },
        "offers": {"price": 1000},
        "description": "Спектакль отменен организатором.",
    }

    mock_client = AsyncMock()

    # Cancellations list page
    resp_list = MagicMock()
    resp_list.status_code = 200
    resp_list.text = '<a href="/events/teatr/99-9999/">Отмена</a>'

    # Single event page
    resp_event = MagicMock()
    resp_event.status_code = 200
    resp_event.text = f'<script type="application/ld+json">{json.dumps(mock_event_json)}</script>'

    mock_client.get.side_effect = [resp_list, resp_event, MagicMock(status_code=404)]

    # Mock range url to 404 to isolate cancellation parsing
    with patch.object(crawler, "base_url", "https://ufa.kassy.ru"):
        results = await crawler.crawl(mock_client)

    assert len(results) >= 1
    cancelled_ev = next(r for r in results if r["title"] == "Отмененный спектакль")
    assert cancelled_ev["status"] == EventStatus.CANCELLED.value
    assert cancelled_ev["city"] == "Уфа"


@pytest.mark.asyncio
async def test_crawler_service_verify_url():
    crawler_service = CrawlerService(import_service=MagicMock())

    mock_client = AsyncMock()

    # Success 200
    mock_resp = MagicMock(status_code=200)
    mock_client.head.return_value = mock_resp
    assert await crawler_service.verify_url(mock_client, "https://ufa.kassir.ru/test") is True

    # Failed 404
    mock_resp_404 = MagicMock(status_code=404)
    mock_client.head.return_value = mock_resp_404
    mock_client.get.return_value = mock_resp_404
    assert await crawler_service.verify_url(mock_client, "https://ufa.kassir.ru/broken") is False
