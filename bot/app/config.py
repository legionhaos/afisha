import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    token: str
    api_base_url: str
    timeout: float
    webapp_url: str = ""

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("Задайте BOT_TOKEN в окружении или .env")
        url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError("API_BASE_URL должен начинаться с http:// или https://")
        timeout = float(os.getenv("API_TIMEOUT", "20"))
        if timeout <= 0:
            raise ValueError("API_TIMEOUT должен быть положительным")
        webapp_url = os.getenv("WEBAPP_URL", "http://localhost:3000/miniapp").strip()
        return cls(token, url, timeout, webapp_url)
