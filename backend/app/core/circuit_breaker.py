import asyncio
import enum
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""


class LLMCircuitBreaker:
    """Circuit breaker pattern implementation for LLM calls.

    Protects against external provider failures, cascading timeouts,
    and automatically triggers fallback degradation mode.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        timeout_sec: float = 6.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.timeout_sec = timeout_sec

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def can_execute(self) -> bool:
        """Checks whether an execution can be attempted under current breaker state."""
        now = time.monotonic()
        if self._state == CircuitState.OPEN:
            if now - self._last_failure_time >= self.cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info("circuit_breaker_transition", state="HALF_OPEN")
                return True
            return False
        return True

    def record_success(self) -> None:
        """Records a successful call and resets the circuit breaker to CLOSED."""
        if self._state != CircuitState.CLOSED or self._failure_count > 0:
            logger.info("circuit_breaker_recovered", previous_state=self._state.value)
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def record_failure(self, exc: Exception | None = None) -> None:
        """Records a failure or timeout, tripping the circuit breaker to OPEN when threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        logger.warning(
            "circuit_breaker_failure_recorded",
            failure_count=self._failure_count,
            threshold=self.failure_threshold,
            error=str(exc) if exc else "timeout_or_error",
        )

        if self._failure_count >= self.failure_threshold or self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.error("circuit_breaker_opened", cooldown=self.cooldown_seconds)

    async def call(
        self,
        coro_func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Executes a coroutine with timeout and circuit state protection."""
        async with self._lock:
            if not self.can_execute():
                raise CircuitOpenError(
                    f"LLM circuit breaker is OPEN. Cooldown remaining: "
                    f"{max(0.0, self.cooldown_seconds - (time.monotonic() - self._last_failure_time)):.1f}s"
                )

        try:
            result = await asyncio.wait_for(
                coro_func(*args, **kwargs),
                timeout=self.timeout_sec,
            )
            async with self._lock:
                self.record_success()
            return result
        except TimeoutError as te:
            async with self._lock:
                self.record_failure(te)
            raise TimeoutError(f"LLM call exceeded timeout of {self.timeout_sec}s") from te
        except Exception as e:
            async with self._lock:
                self.record_failure(e)
            raise


# Global instance with default 6-second timeout strictly as per specification
llm_circuit_breaker = LLMCircuitBreaker(
    failure_threshold=3,
    cooldown_seconds=60.0,
    timeout_sec=6.0,
)
