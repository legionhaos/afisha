"""Circuit breaker for external model calls."""

import asyncio
import time
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """The provider is unavailable or the circuit is open."""


class LLMCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60,
                 timeout_seconds: float = 6.0) -> None:
        if failure_threshold < 1 or cooldown_seconds < 0 or timeout_seconds <= 0:
            raise ValueError("Invalid circuit breaker configuration")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.timeout_seconds = timeout_seconds
        self.last_failure_time = 0.0
        self._probe_running = False
        self._generation = 0

    def can_execute(self) -> bool:
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time < self.cooldown_seconds:
                return False
            self.state = CircuitState.HALF_OPEN
        return not self._probe_running if self.state == CircuitState.HALF_OPEN else True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self._probe_running = False
        self._generation += 1

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._generation += 1
        self._probe_running = False

    async def call(self, coro_func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        if not self.can_execute():
            raise CircuitOpenError("LLM circuit is open")
        probe = self.state == CircuitState.HALF_OPEN
        generation = self._generation
        if probe:
            self._probe_running = True
        try:
            result = await asyncio.wait_for(coro_func(*args, **kwargs), timeout=self.timeout_seconds)
        except asyncio.CancelledError:
            if probe and generation == self._generation:
                self._probe_running = False
            raise
        except Exception as exc:
            if generation == self._generation:
                self.record_failure()
            raise CircuitOpenError("Model provider call failed") from exc
        if generation == self._generation:
            self.record_success()
        return result
