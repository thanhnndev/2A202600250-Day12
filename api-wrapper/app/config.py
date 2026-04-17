import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    PORT: int = 18001
    LOG_LEVEL: str = "info"

    AGENT_API_KEY: str = "sk-mock-day12-key-2026"

    BACKEND_URL: str = "http://localhost:18000"

    REDIS_URL: str = "redis://localhost:6379/0"

    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_WINDOW: int = 60

    COST_LIMIT_USD: float = 10.0
    COST_PER_REQUEST: float = 0.05

    APP_VERSION: str = "1.0.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
