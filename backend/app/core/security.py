import asyncio
import hashlib
import hmac
import secrets
import time
from collections import defaultdict


class SecurityService:
    """Security utility methods for hashing, rate limiting, and token verification."""

    def __init__(self) -> None:
        # In-memory sliding window rate limiter: client_key -> list of timestamp floats
        self._rate_limits: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    @staticmethod
    def compute_source_hash(source_url: str, title: str, date_start_iso: str) -> str:
        """SHA-256 hash guaranteeing 100% idempotency for re-imported events."""
        normalized_str = f"{source_url.strip()}|{title.strip().lower()}|{date_start_iso.strip()}"
        return hashlib.sha256(normalized_str.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_user_identifier(raw_id: str, salt: str = "bash_afisha_salt") -> str:
        """Creates an anonymized hash for tracking user daily budgets without storing personal data."""
        return hashlib.sha256(f"{salt}::{raw_id}".encode("utf-8")).hexdigest()

    async def check_rate_limit(
        self,
        client_key: str,
        limit: int = 60,
        window_sec: int = 60,
    ) -> bool:
        """Sliding window rate limit check. Returns True if allowed, False if exceeded."""
        now = time.monotonic()
        cutoff = now - window_sec

        async with self._lock:
            timestamps = self._rate_limits[client_key]
            # Prune old timestamps
            self._rate_limits[client_key] = [t for t in timestamps if t > cutoff]

            if len(self._rate_limits[client_key]) >= limit:
                return False

            self._rate_limits[client_key].append(now)
            return True

    @staticmethod
    def verify_admin_token(token: str, expected_token: str) -> bool:
        """Timing-attack-safe comparison of admin authentication token."""
        if not token or not expected_token:
            return False
        return hmac.compare_digest(token.strip(), expected_token.strip())


security_service = SecurityService()
