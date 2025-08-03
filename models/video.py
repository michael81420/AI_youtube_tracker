"""
Video metadata and processing state models.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class VideoMetadata(BaseModel):
    """YouTube video metadata and processing state."""
    
    video_id: str = Field(..., description="YouTube video ID")
    channel_id: str = Field(..., description="YouTube channel ID")
    title: str = Field(..., description="Video title")
    description: str = Field(..., description="Video description")
    published_at: datetime = Field(..., description="Video publication timestamp")
    thumbnail_url: str = Field(..., description="Video thumbnail URL")
    duration: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    processed_at: Optional[datetime] = None
    summary: Optional[str] = None
    notification_sent: bool = False
    
    @validator('video_id')
    def validate_video_id(cls, v):
        """Validate YouTube video ID format."""
        if len(v) != 11:
            raise ValueError('YouTube video ID must be 11 characters long')
        return v
    
    @validator('channel_id')
    def validate_channel_id(cls, v):
        """Validate YouTube channel ID format."""
        if not v.startswith('UC') or len(v) != 24:
            raise ValueError('Invalid YouTube channel ID format - must start with UC and be 24 characters')
        return v
    
    @validator('title')
    def validate_title(cls, v):
        """Validate video title."""
        if not v.strip():
            raise ValueError('Video title cannot be empty')
        return v.strip()
    
    @validator('duration')
    def validate_duration(cls, v):
        """Validate ISO 8601 duration format."""
        if v and not v.startswith('PT'):
            raise ValueError('Duration must be in ISO 8601 format (e.g., PT4M13S)')
        return v
    
    @property
    def url(self) -> str:
        """Get YouTube video URL."""
        return f"https://www.youtube.com/watch?v={self.video_id}"
    
    @property
    def duration_seconds(self) -> Optional[int]:
        """Convert ISO 8601 duration to seconds."""
        if not self.duration:
            return None
        
        # Simple parser for PT format (e.g., PT4M13S, PT1H2M3S)
        duration_str = self.duration[2:]  # Remove 'PT'
        seconds = 0
        
        if 'H' in duration_str:
            hours, duration_str = duration_str.split('H')
            seconds += int(hours) * 3600
        
        if 'M' in duration_str:
            minutes, duration_str = duration_str.split('M')
            seconds += int(minutes) * 60
        
        if 'S' in duration_str:
            secs = duration_str.replace('S', '')
            if secs:
                seconds += int(secs)
        
        return seconds
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class VideoSummary(BaseModel):
    """Video summarization result."""
    
    video_id: str
    summary: str
    summary_length: int = Field(..., description="Summary length in characters")
    model_used: str = Field(..., description="LLM model used for summarization")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processing_time_seconds: Optional[float] = None
    tokens_used: Optional[int] = None
    
    @validator('summary')
    def validate_summary(cls, v):
        """Validate summary content."""
        if not v.strip():
            raise ValueError('Summary cannot be empty')
        if len(v) > 2000:
            raise ValueError('Summary too long - maximum 2000 characters')
        return v.strip()
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }