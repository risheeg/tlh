from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SMTPSettings(BaseModel):
    host: str
    port: int
    user: str
    password: str
    from_email: str
    use_tls: bool = True
    use_ssl: bool = False


class Settings(BaseSettings):
    neon_db_host: str

    # Google Sheets integration
    google_sheet_id: str
    portfolio_snapshot_sheet_id: str
    google_application_credentials: str = "../google_credentials.json"

    # Email SMTP Credentials (parsed from env)
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from_email: str
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    @property
    def smtp(self) -> SMTPSettings:
        """Grouped SMTP settings for convenience."""
        return SMTPSettings(
            host=self.smtp_host,
            port=self.smtp_port,
            user=self.smtp_user,
            password=self.smtp_password,
            from_email=self.smtp_from_email,
            use_tls=self.smtp_use_tls,
            use_ssl=self.smtp_use_ssl,
        )

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
