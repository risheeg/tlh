from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    neon_db_host: str

    # Google Sheets integration
    google_sheet_id: str
    portfolio_snapshot_sheet_id: str
    google_application_credentials: str = "../google_credentials.json"

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
