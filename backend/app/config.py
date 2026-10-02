from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = "your_google_ai_studio_api_key_here"
    database_url: str = "postgresql+asyncpg://vma:vma_password@localhost:5432/vma_ai"
    gemini_model: str = "gemini-3.8-live"
    default_practice_id: int = 1
    environment: str = "dev"

    # PHI safety:
    # Keep this false unless you explicitly want verbose debug logging.
    log_phi: bool = False


settings = Settings()