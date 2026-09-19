from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # LINE Messaging API
    LINE_CHANNEL_SECRET: str = Field(default="mock_line_channel_secret")
    LINE_CHANNEL_ACCESS_TOKEN: str = Field(default="mock_line_channel_access_token")

    # Google Gemini API
    GEMINI_API_KEY: str = Field(default="mock_gemini_api_key")

    # App Settings
    PORT: int = Field(default=8000)
    HOST: str = Field(default="0.0.0.0")
    DATABASE_URL: str = Field(default="sqlite:///./line_cal.db")

    # User Default Profile (Suphakorn's metrics)
    USER_DEFAULT_GENDER: str = Field(default="male")
    USER_DEFAULT_AGE: int = Field(default=22)
    USER_DEFAULT_HEIGHT_CM: float = Field(default=174.0)
    USER_DEFAULT_WEIGHT_KG: float = Field(default=72.0)
    USER_DEFAULT_DAILY_TARGET_KCAL: float = Field(default=1950.0)
    USER_DEFAULT_TARGET_PROTEIN_G: float = Field(default=145.0)
    USER_DEFAULT_TARGET_CARBS_G: float = Field(default=220.0)
    USER_DEFAULT_TARGET_FAT_G: float = Field(default=55.0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
