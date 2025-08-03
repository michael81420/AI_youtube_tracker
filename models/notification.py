"""
Notification tracking and status models.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, validator


class NotificationType(str, Enum):
    """Types of notifications."""
    NEW_VIDEO = "new_video"
    SUMMARY_READY = "summary_ready" 
    ERROR_ALERT = "error_alert"
    STATUS_UPDATE = "status_update"


class NotificationStatus(BaseModel):
    """Notification delivery tracking."""
    
    video_id: str
    chat_id: str
    notification_type: NotificationType = NotificationType.NEW_VIDEO
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    message_id: Optional[int] = None
    success: bool
    error_message: Optional[str] = None
    retry_count: int = 0
    
    @validator('chat_id')
    def validate_chat_id(cls, v):
        """Validate Telegram chat ID format."""
        try:
            int(v)
        except ValueError:
            raise ValueError('Chat ID must be a valid integer')
        return v
    
    @validator('error_message')
    def validate_error_message(cls, v, values):
        """Validate error message is present when success is False."""
        if not values.get('success') and not v:
            raise ValueError('Error message required when success is False')
        return v
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class NotificationMessage(BaseModel):
    """Formatted notification message."""
    
    chat_id: str
    message_text: str
    parse_mode: str = "Markdown"
    disable_web_page_preview: bool = False
    reply_markup: Optional[dict] = None
    
    @validator('message_text')
    def validate_message_text(cls, v):
        """Validate message content."""
        if not v.strip():
            raise ValueError('Message text cannot be empty')
        if len(v) > 4096:  # Telegram limit
            raise ValueError('Message text too long - maximum 4096 characters')
        return v.strip()
    
    @validator('parse_mode')
    def validate_parse_mode(cls, v):
        """Validate Telegram parse mode."""
        valid_modes = ['Markdown', 'MarkdownV2', 'HTML']
        if v not in valid_modes:
            raise ValueError(f'Parse mode must be one of: {valid_modes}')
        return v


class NotificationTemplate(BaseModel):
    """Template for generating notifications."""
    
    template_name: str
    notification_type: NotificationType
    subject_template: str
    body_template: str
    include_thumbnail: bool = True
    include_summary: bool = True
    
    @validator('template_name')
    def validate_template_name(cls, v):
        """Validate template name."""
        if not v.strip():
            raise ValueError('Template name cannot be empty')
        return v.strip().lower()
    
    def format_message(self, video_data: dict, summary: Optional[str] = None) -> str:
        """Format notification message using template."""
        context = {
            **video_data,
            'summary': summary or 'Summary not available'
        }
        
        try:
            formatted_body = self.body_template.format(**context)
            return formatted_body
        except KeyError as e:
            raise ValueError(f"Template formatting error - missing key: {e}")


class NotificationQueue(BaseModel):
    """Notification queue item."""
    
    queue_id: str = Field(..., description="Unique queue item ID")
    video_id: str
    chat_id: str
    notification_type: NotificationType
    priority: int = Field(1, ge=1, le=5, description="Priority level (1=highest, 5=lowest)")
    scheduled_for: datetime = Field(default_factory=datetime.utcnow)
    attempts: int = 0
    max_attempts: int = 3
    status: str = Field("pending", description="Queue status: pending, processing, sent, failed")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('status')
    def validate_status(cls, v):
        """Validate queue status."""
        valid_statuses = ['pending', 'processing', 'sent', 'failed']
        if v not in valid_statuses:
            raise ValueError(f'Status must be one of: {valid_statuses}')
        return v
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }