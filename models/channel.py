"""
Channel configuration and state models.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class ChannelConfig(BaseModel):
    """Channel configuration and tracking state."""
    
    channel_id: str = Field(..., description="YouTube channel ID")
    channel_name: str = Field(..., description="Human-readable channel name")
    check_interval: int = Field(3600, ge=300, description="Check interval in seconds")
    telegram_chat_id: str = Field(..., description="Telegram chat ID for notifications")
    last_check: Optional[datetime] = None
    last_video_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    @validator('channel_id')
    def validate_channel_id(cls, v):
        """Validate YouTube channel ID format."""
        if not v.startswith('UC') or len(v) != 24:
            raise ValueError('Invalid YouTube channel ID format - must start with UC and be 24 characters')
        return v
    
    @validator('telegram_chat_id')
    def validate_telegram_chat_id(cls, v):
        """Validate Telegram chat ID format."""
        # Chat IDs can be positive (private chats) or negative (groups/channels)
        try:
            int(v)
        except ValueError:
            raise ValueError('Telegram chat ID must be a valid integer')
        return v
    
    @validator('check_interval')
    def validate_check_interval(cls, v):
        """Validate check interval is reasonable."""
        if v < 300:  # 5 minutes minimum
            raise ValueError('Check interval must be at least 300 seconds (5 minutes)')
        if v > 86400:  # 24 hours maximum
            raise ValueError('Check interval must be at most 86400 seconds (24 hours)')
        return v
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChannelStatus(BaseModel):
    """Channel processing status and statistics."""
    
    channel_id: str
    channel_name: str
    is_active: bool
    last_check: Optional[datetime] = None
    last_successful_check: Optional[datetime] = None
    total_videos_processed: int = 0
    videos_processed_today: int = 0
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }