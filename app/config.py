from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "DAMI Threads Assistant"
    app_env: str = "production"
    app_timezone: str = "Asia/Bangkok"
    app_base_url: str = ""
    app_database_path: Path = Path("data/dami_threads.db")
    app_admin_password: str = ""
    session_secret: str = ""
    token_encryption_key: str = ""

    meta_app_id: str = ""
    meta_app_secret: str = ""
    graph_base_url: str = "https://graph.threads.net"
    oauth_authorize_url: str = "https://threads.net/oauth/authorize"
    graph_api_version: str = "v1.0"
    oauth_scopes: str = Field(
        default="threads_basic,threads_content_publish,threads_keyword_search"
    )

    max_batch_size: int = Field(default=10, ge=1, le=10)
    max_daily_replies: int = Field(default=20, ge=1, le=100)
    send_delay_seconds: int = Field(default=15, ge=3, le=300)

    @property
    def clean_base_url(self) -> str:
        if not self.app_base_url:
            return ""
        url = self.app_base_url.strip().rstrip("/")
        if url.endswith("/login"):
            url = url[:-6].rstrip("/")
        return url

    @property
    def redirect_uri(self) -> str:
        if not self.clean_base_url:
            return ""
        return f"{self.clean_base_url}/auth/threads/callback"

    @property
    def api_root(self) -> str:
        version = self.graph_api_version.strip("/")
        return f"{self.graph_base_url.rstrip('/')}/{version}"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def meta_configured(self) -> bool:
        return bool(self.meta_app_id and self.meta_app_secret and self.redirect_uri)

    def startup_warnings(self) -> list[str]:
        warnings: list[str] = []
        if not self.meta_configured:
            warnings.append("META_APP_ID, META_APP_SECRET hoặc APP_BASE_URL còn thiếu.")
        if self.is_production and self.app_base_url and not self.app_base_url.startswith("https://"):
            warnings.append("APP_BASE_URL production phải dùng HTTPS.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
