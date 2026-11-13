import asyncio
import pytest
from app.core.config import Settings, get_settings
from app.core.logging import PIIScrubberProcessor
from app.core.exceptions import (
    AppError,
    EventNotFoundError,
    ValidationFailedError,
    RateLimitExceededError,
    AgentBudgetExceededError,
    UnauthorizedAdminError,
)
from app.core.security import SecurityService
from app.core.circuit_breaker import LLMCircuitBreaker, CircuitState, CircuitOpenError


def test_settings_strictly_comply_with_contract():
    settings = get_settings()
    assert settings.LLM_TIMEOUT_SEC == 6.0
    assert settings.MAX_AGENT_STEPS == 5
    assert settings.MAX_DAILY_USER_BUDGET_RUB == 25.0
    assert settings.MAX_DIALOG_COST_RUB == 5.0
    assert "postgresql" in settings.DATABASE_URL
    assert "postgresql" in settings.CHECKPOINT_DB_URI


def test_pii_scrubber_processor():
    processor = PIIScrubberProcessor()
    raw_event = {
        "event": "user_action",
        "message": "Пользователь +7 (999) 123-45-67 и 89171234567 написал с почты test@example.com с IP 192.168.1.50",
        "user_token": "secret_abc123",
        "api_key": "sk-123456",
        "nested": {
            "phone": "+79998887766",
            "password": "my_super_password",
        },
    }
    scrubbed = processor(None, "info", raw_event)

    assert "+7 (999) 123-45-67" not in scrubbed["message"]
    assert "[SCRUBBED_PHONE]" in scrubbed["message"]
    assert "test@example.com" not in scrubbed["message"]
    assert "[SCRUBBED_EMAIL]" in scrubbed["message"]
    assert "192.168.1.50" not in scrubbed["message"]
    assert "[SCRUBBED_IP]" in scrubbed["message"]
    assert scrubbed["user_token"] == "[SCRUBBED_SECRET]"
    assert scrubbed["api_key"] == "[SCRUBBED_SECRET]"
    assert scrubbed["nested"]["password"] == "[SCRUBBED_SECRET]"
    assert "[SCRUBBED_PHONE]" in scrubbed["nested"]["phone"]


def test_rfc7807_exception_classes():
    err401 = UnauthorizedAdminError()
    assert err401.status_code == 401
    assert err401.code == "UNAUTHORIZED_ADMIN"

    err404 = EventNotFoundError("evt-123")
    assert err404.status_code == 404
    assert err404.code == "EVENT_NOT_FOUND"
    assert "evt-123" in err404.detail

    err422 = ValidationFailedError("Validation error", errors=[{"field": "age"}])
    assert err422.status_code == 422
    assert err422.code == "VALIDATION_FAILED"
    assert err422.errors == [{"field": "age"}]

    err429 = RateLimitExceededError()
    assert err429.status_code == 429
    assert err429.code == "RATE_LIMIT_EXCEEDED"

    err503 = AgentBudgetExceededError()
    assert err503.status_code == 503
    assert err503.code == "AGENT_BUDGET_EXCEEDED"


def test_security_service():
    sec = SecurityService()
    # 1. Idempotency source_hash
    hash1 = sec.compute_source_hash("https://example.com/1", "Концерт", "2026-11-14T19:00:00")
    hash2 = sec.compute_source_hash("https://example.com/1", "концерт", "2026-11-14T19:00:00")
    assert hash1 == hash2
    assert len(hash1) == 64

    # 2. User identifier hash
    uhash = sec.hash_user_identifier("user123")
    assert len(uhash) == 64

    # 3. Admin token verification
    assert sec.verify_admin_token("my_token", "my_token") is True
    assert sec.verify_admin_token("wrong", "my_token") is False
    assert sec.verify_admin_token("", "my_token") is False


@pytest.mark.asyncio
async def test_security_rate_limiting():
    sec = SecurityService()
    key = "test_client_ip"
    # Allow 3 requests in 1 second
    assert await sec.check_rate_limit(key, limit=3, window_sec=1) is True
    assert await sec.check_rate_limit(key, limit=3, window_sec=1) is True
    assert await sec.check_rate_limit(key, limit=3, window_sec=1) is True
    # 4th should be blocked
    assert await sec.check_rate_limit(key, limit=3, window_sec=1) is False


@pytest.mark.asyncio
async def test_circuit_breaker_transitions():
    cb = LLMCircuitBreaker(failure_threshold=2, cooldown_seconds=0.1, timeout_sec=0.05)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 1. First failure
    async def failing_func():
        raise RuntimeError("LLM error")

    with pytest.raises(RuntimeError):
        await cb.call(failing_func)
    assert cb.state == CircuitState.CLOSED

    # 2. Second failure trips the breaker to OPEN
    with pytest.raises(RuntimeError):
        await cb.call(failing_func)
    assert cb.state == CircuitState.OPEN

    # 3. Call blocked while OPEN
    with pytest.raises(CircuitOpenError):
        await cb.call(failing_func)

    # 4. Wait for cooldown to transition to HALF_OPEN
    await asyncio.sleep(0.15)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # 5. Successful call resets to CLOSED
    async def successful_func():
        return "success"

    result = await cb.call(successful_func)
    assert result == "success"
    assert cb.state == CircuitState.CLOSED
