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
    extract_address,
    extract_price,
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


def test_missing_source_facts_are_not_fabricated():
    assert detect_bashkortostan_city(None, None) == ("", False)
    assert extract_price({}) == (None, None, None)
    assert extract_price({"lowPrice": "300"}) == (None, None, None)
    assert extract_price({"price": "0"}) == (0, 0, True)
    assert extract_price({"price": "500.5"}) == (None, None, None)
    assert extract_address({"addressLocality": "Уфа", "streetAddress": "Ленина, 1"}) == "Уфа, Ленина, 1"


def test_clean_kassir_datetime():
    # Явное смещение источника нельзя заменять без подтверждения.
    raw_date = "2026-11-28T19:00:00+00:00"
    cleaned = clean_kassir_datetime(raw_date)
    assert cleaned == "2026-11-28T19:00:00+00:00"

    raw_date_z = "2026-12-05T18:30:00Z"
    cleaned_z = clean_kassir_datetime(raw_date_z)
    assert cleaned_z == "2026-12-05T18:30:00Z"

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
    assert ev["date_start"] == "2026-11-20T19:00:00+00:00"


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
    assert ev["city"] == ""
    assert ev["age_limit"] == "16+"
    assert ev["venue"] == ""
    assert ev["price_min"] is None and ev["price_max"] is None
    assert ev["description"] == ""
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
async def test_crawl_keeps_multiple_showtimes_and_cancelled_status():
    crawler_service = CrawlerService(import_service=MagicMock())
    source = MagicMock()
    source.name = "fixture"
    source.crawl = AsyncMock(return_value=[
        {"title": "Тест", "source_url": "https://example.org/a", "date_start": "2027-01-01", "status": "cancelled"},
        {"title": "Тест", "source_url": "https://example.org/a", "date_start": "2027-01-02", "status": "published"},
    ])
    crawler_service.crawlers = [source]
    crawler_service.verify_url = AsyncMock(return_value=False)
    result = await crawler_service.crawl_all(verify_urls=True)
    assert len(result) == 2
    assert result[0]["status"] == "cancelled"
    assert result[1]["status"] == "draft"


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

    mock_client.reset_mock()
    for url in ("http://ufa.kassir.ru/test", "https://127.0.0.1/test",
                "https://ufa.kassir.ru.evil.example/", "https://user@ufa.kassir.ru/", "https://ufa.kassir.ru:8443/"):
        assert await crawler_service.verify_url(mock_client, url) is False
    mock_client.head.assert_not_awaited()

    mock_client.head.return_value = MagicMock(status_code=302)
    assert await crawler_service.verify_url(mock_client, "https://ufa.kassir.ru/redirect") is False
    mock_client.get.assert_not_awaited()

    mock_client.head.return_value = MagicMock(status_code=405)
    mock_client.get.return_value = MagicMock(status_code=200)
    assert await crawler_service.verify_url(mock_client, "https://ufa.kassir.ru/no-head") is True
    assert mock_client.get.await_args.kwargs["follow_redirects"] is False
