"""
Configuration management using Pydantic Settings.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with validation."""
    
    # YouTube Data API v3
    youtube_api_key: str = Field(..., description="YouTube Data API v3 key")
    
    # Telegram Bot
    telegram_bot_token: str = Field(..., description="Telegram bot token")
    telegram_chat_id: str = Field(..., description="Default Telegram chat ID for notifications")
    
    # LLM Provider (at least one required)
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(None, description="Anthropic API key")
    gemini_api_key: Optional[str] = Field(None, description="Google Gemini API key")
    llm_provider: str = Field("openai", description="LLM provider to use: openai, anthropic, or gemini")
    llm_model: str = Field("gpt-4o-mini", description="LLM model to use for summarization")
    
    # Database Configuration
    database_url: str = Field(
        "sqlite+aiosqlite:///./youtube_tracker.db",
        description="Database connection URL"
    )
    
    # Scheduling
    scheduler_jobstore_url: str = Field(
        "sqlite:///./scheduler_jobs.db",
        description="APScheduler job store URL"
    )
    
    # Logging Configuration
    log_level: str = Field("INFO", description="Logging level")
    log_file: str = Field("./logs/youtube_tracker.log", description="Log file path")
    
    # Environment
    environment: str = Field("development", description="Environment: development, production")
    
    # Rate Limiting
    youtube_requests_per_minute: int = Field(50, description="YouTube API requests per minute")
    telegram_messages_per_minute: int = Field(20, description="Telegram messages per minute")
    llm_requests_per_minute: int = Field(3, description="LLM API requests per minute")
    
    # Video Processing
    max_videos_per_check: int = Field(1, description="Maximum number of videos to process per check")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @validator('llm_provider')
    def validate_llm_provider(cls, v):
        """Validate LLM provider."""
        if v not in ['openai', 'anthropic', 'gemini']:
            raise ValueError('llm_provider must be one of: "openai", "anthropic", or "gemini"')
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'log_level must be one of: {valid_levels}')
        return v.upper()
    
    def validate_api_keys(self) -> None:
        """Validate that required API keys are present based on provider."""
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("openai_api_key is required when using OpenAI provider")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("anthropic_api_key is required when using Anthropic provider")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("gemini_api_key is required when using Gemini provider")
    
    def setup_logging(self) -> None:
        """Setup logging configuration."""
        # Create logs directory if it doesn't exist
        log_path = Path(self.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        
        # Set specific logger levels
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.validate_api_keys()
    settings.setup_logging()
    return settings