"""
Telegram notification agent with message formatting and delivery management.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from langchain_core.tools import tool

from config.settings import get_settings
from models.video import VideoMetadata
from models.notification import NotificationStatus, NotificationType, NotificationMessage
from tools.telegram_tools import (
    send_video_notification,
    send_telegram_message,
    format_video_notification,
    format_status_message,
    format_error_message,
    validate_telegram_chat
)
from utils import safe_log_text

# Setup logging
logger = logging.getLogger(__name__)


class TelegramAgent:
    """Agent for managing Telegram notifications and message delivery."""
    
    def __init__(self):
        self.settings = get_settings()
        self.notifications_sent = 0
        self.delivery_failures = 0
        
    async def send_video_notification(
        self,
        video: VideoMetadata,
        summary: Optional[str],
        chat_id: str,
        retry_on_failure: bool = True
    ) -> NotificationStatus:
        """
        Send a video notification with retry logic.
        
        Args:
            video: VideoMetadata object
            summary: Video summary text
            chat_id: Telegram chat ID
            retry_on_failure: Whether to retry on delivery failure
            
        Returns:
            NotificationStatus with delivery result
        """
        max_retries = 3 if retry_on_failure else 1
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending video notification attempt {attempt + 1}/{max_retries}")
                
                # Send notification using tool
                notification_status = await send_video_notification.ainvoke({
                    "video": video,
                    "summary": summary,
                    "chat_id": chat_id,
                    "include_thumbnail": True
                })
                
                if notification_status.success:
                    self.notifications_sent += 1
                    logger.info(f"Successfully sent notification for video {video.video_id}")
                    return notification_status
                else:
                    logger.warning(f"Notification delivery failed: {notification_status.error_message}")
                    if attempt == max_retries - 1:
                        self.delivery_failures += 1
                        return notification_status
                    
                    # Wait before retry with exponential backoff
                    wait_time = (2 ** attempt) * 5  # 5, 10, 20 seconds
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                logger.error(f"Unexpected error in notification delivery: {e}")
                if attempt == max_retries - 1:
                    self.delivery_failures += 1
                    return NotificationStatus(
                        video_id=video.video_id,
                        chat_id=chat_id,
                        success=False,
                        error_message=str(e),
                        retry_count=attempt + 1
                    )
                
                # Wait before retry
                wait_time = (2 ** attempt) * 5
                await asyncio.sleep(wait_time)
        
        # Should never reach here, but just in case
        return NotificationStatus(
            video_id=video.video_id,
            chat_id=chat_id,
            success=False,
            error_message="Max retries exceeded",
            retry_count=max_retries
        )
    
    async def send_status_update(
        self,
        channel_name: str,
        videos_processed: int,
        chat_id: str,
        last_check: Optional[datetime] = None
    ) -> NotificationStatus:
        """
        Send a status update message.
        
        Args:
            channel_name: Name of the channel
            videos_processed: Number of videos processed
            chat_id: Telegram chat ID
            last_check: Last check timestamp
            
        Returns:
            NotificationStatus with delivery result
        """
        try:
            logger.info(f"Sending status update for {safe_log_text(channel_name)}")
            
            message_text = format_status_message(
                channel_name=channel_name,
                videos_processed=videos_processed,
                last_check=last_check
            )
            
            notification_status = await send_telegram_message.ainvoke({
                "chat_id": chat_id,
                "message_text": message_text
            })
            
            notification_status.video_id = "status_update"
            
            if notification_status.success:
                logger.info(f"Successfully sent status update for {safe_log_text(channel_name)}")
            else:
                logger.warning(f"Failed to send status update: {notification_status.error_message}")
            
            return notification_status
            
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
            return NotificationStatus(
                video_id="status_update",
                chat_id=chat_id,
                success=False,
                error_message=str(e)
            )
    
    async def send_error_alert(
        self,
        error_type: str,
        error_details: str,
        channel_name: str,
        chat_id: str
    ) -> NotificationStatus:
        """
        Send an error alert message.
        
        Args:
            error_type: Type of error
            error_details: Error details
            channel_name: Name of the affected channel
            chat_id: Telegram chat ID
            
        Returns:
            NotificationStatus with delivery result
        """
        try:
            logger.info(f"Sending error alert for {safe_log_text(channel_name)}")
            
            message_text = format_error_message(
                error_type=error_type,
                error_details=error_details,
                channel_name=channel_name
            )
            
            notification_status = await send_telegram_message.ainvoke({
                "chat_id": chat_id,
                "message_text": message_text
            })
            
            notification_status.video_id = "error_alert"
            
            if notification_status.success:
                logger.info(f"Successfully sent error alert for {safe_log_text(channel_name)}")
            else:
                logger.warning(f"Failed to send error alert: {notification_status.error_message}")
            
            return notification_status
            
        except Exception as e:
            logger.error(f"Error sending error alert: {e}")
            return NotificationStatus(
                video_id="error_alert",
                chat_id=chat_id,
                success=False,
                error_message=str(e)
            )
    
    async def batch_send_notifications(
        self,
        notifications: List[Dict[str, Any]],
        delay_between_messages: float = 1.0
    ) -> List[NotificationStatus]:
        """
        Send multiple notifications with rate limiting.
        
        Args:
            notifications: List of notification dictionaries
            delay_between_messages: Delay between messages in seconds
            
        Returns:
            List of NotificationStatus objects
        """
        results = []
        
        logger.info(f"Sending batch of {len(notifications)} notifications")
        
        for i, notification_data in enumerate(notifications):
            try:
                # Determine notification type and send accordingly
                if notification_data.get("type") == "video":
                    result = await self.send_video_notification(
                        video=notification_data["video"],
                        summary=notification_data.get("summary"),
                        chat_id=notification_data["chat_id"]
                    )
                elif notification_data.get("type") == "status":
                    result = await self.send_status_update(
                        channel_name=notification_data["channel_name"],
                        videos_processed=notification_data["videos_processed"],
                        chat_id=notification_data["chat_id"],
                        last_check=notification_data.get("last_check")
                    )
                elif notification_data.get("type") == "error":
                    result = await self.send_error_alert(
                        error_type=notification_data["error_type"],
                        error_details=notification_data["error_details"],
                        channel_name=notification_data["channel_name"],
                        chat_id=notification_data["chat_id"]
                    )
                else:
                    # Generic message
                    result = await send_telegram_message.ainvoke({
                        "chat_id": notification_data["chat_id"],
                        "message_text": notification_data["message_text"]
                    })
                
                results.append(result)
                
                # Rate limiting delay (except for last message)
                if i < len(notifications) - 1:
                    await asyncio.sleep(delay_between_messages)
                    
            except Exception as e:
                logger.error(f"Error in batch notification {i}: {e}")
                error_result = NotificationStatus(
                    video_id=notification_data.get("video_id", "batch_error"),
                    chat_id=notification_data.get("chat_id", "unknown"),
                    success=False,
                    error_message=str(e)
                )
                results.append(error_result)
        
        successful = sum(1 for r in results if r.success)
        logger.info(f"Batch send complete: {successful}/{len(results)} successful")
        
        return results
    
    async def validate_chat_access(self, chat_id: str) -> bool:
        """
        Validate that the bot has access to a chat.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            True if bot has access, False otherwise
        """
        try:
            return await validate_telegram_chat(chat_id)
        except Exception as e:
            logger.error(f"Error validating chat access for {chat_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "notifications_sent": self.notifications_sent,
            "delivery_failures": self.delivery_failures,
            "success_rate": (
                self.notifications_sent / (self.notifications_sent + self.delivery_failures)
                if (self.notifications_sent + self.delivery_failures) > 0
                else 0.0
            )
        }


# Global agent instance
telegram_agent = TelegramAgent()


# LangChain tools
@tool
async def notify_new_video(
    video: VideoMetadata,
    summary: Optional[str],
    chat_id: str
) -> NotificationStatus:
    """
    Send notification for a new video.
    
    Args:
        video: VideoMetadata object
        summary: Video summary text (optional)
        chat_id: Telegram chat ID
        
    Returns:
        NotificationStatus with delivery result
    """
    return await telegram_agent.send_video_notification(video, summary, chat_id)


@tool
async def notify_channel_status(
    channel_name: str,
    videos_processed: int,
    chat_id: str,
    last_check: Optional[datetime] = None
) -> NotificationStatus:
    """
    Send channel status notification.
    
    Args:
        channel_name: Name of the channel
        videos_processed: Number of videos processed
        chat_id: Telegram chat ID
        last_check: Last check timestamp
        
    Returns:
        NotificationStatus with delivery result
    """
    return await telegram_agent.send_status_update(
        channel_name, videos_processed, chat_id, last_check
    )


@tool
async def notify_error(
    error_type: str,
    error_details: str,
    channel_name: str,
    chat_id: str
) -> NotificationStatus:
    """
    Send error notification.
    
    Args:
        error_type: Type of error
        error_details: Error details
        channel_name: Name of the affected channel
        chat_id: Telegram chat ID
        
    Returns:
        NotificationStatus with delivery result
    """
    return await telegram_agent.send_error_alert(
        error_type, error_details, channel_name, chat_id
    )