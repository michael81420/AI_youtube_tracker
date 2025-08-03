"""
Notification delivery chain with retry logic and error handling.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.runnables.base import RunnableSequence

from config.settings import get_settings
from models.video import VideoMetadata
from models.notification import NotificationStatus, NotificationType
from agents.telegram_agent import telegram_agent
from utils import safe_log_text

# Setup logging
logger = logging.getLogger(__name__)


class NotificationChain:
    """Chain for managing notification delivery with retry logic."""
    
    def __init__(self):
        self.settings = get_settings()
        self.notifications_processed = 0
        self.delivery_failures = 0
        
    async def send_video_notification(
        self,
        video: VideoMetadata,
        summary: Optional[str],
        chat_id: str,
        max_retries: int = 3,
        retry_delay: float = 5.0
    ) -> NotificationStatus:
        """
        Send video notification with retry logic.
        
        Args:
            video: Video metadata
            summary: Video summary
            chat_id: Telegram chat ID
            max_retries: Maximum retry attempts
            retry_delay: Base delay between retries
            
        Returns:
            NotificationStatus with delivery result
        """
        logger.info(f"Sending video notification: {safe_log_text(video.title)}")
        
        self.notifications_processed += 1
        
        for attempt in range(max_retries):
            try:
                notification_result = await telegram_agent.send_video_notification(
                    video=video,
                    summary=summary,
                    chat_id=chat_id,
                    retry_on_failure=False  # We handle retries here
                )
                
                if notification_result.success:
                    logger.info(f"Successfully sent notification for {video.video_id}")
                    return notification_result
                else:
                    logger.warning(f"Notification attempt {attempt + 1} failed: {notification_result.error_message}")
                    
                    if attempt == max_retries - 1:
                        self.delivery_failures += 1
                        notification_result.retry_count = attempt + 1
                        return notification_result
                    
                    # Exponential backoff with jitter
                    delay = retry_delay * (2 ** attempt) + (0.1 * retry_delay)
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                logger.error(f"Notification attempt {attempt + 1} error: {e}")
                
                if attempt == max_retries - 1:
                    self.delivery_failures += 1
                    return NotificationStatus(
                        video_id=video.video_id,
                        chat_id=chat_id,
                        success=False,
                        error_message=str(e),
                        retry_count=attempt + 1
                    )
                
                # Exponential backoff
                delay = retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
        
        # Should never reach here
        return NotificationStatus(
            video_id=video.video_id,
            chat_id=chat_id,
            success=False,
            error_message="Max retries exceeded",
            retry_count=max_retries
        )
    
    async def send_batch_notifications(
        self,
        notifications: List[Dict[str, Any]],
        delay_between_messages: float = 2.0,
        max_concurrent: int = 3
    ) -> List[NotificationStatus]:
        """
        Send multiple notifications with rate limiting and concurrency control.
        
        Args:
            notifications: List of notification dictionaries
            delay_between_messages: Delay between messages
            max_concurrent: Maximum concurrent notifications
            
        Returns:
            List of NotificationStatus objects
        """
        logger.info(f"Sending batch of {len(notifications)} notifications")
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def _send_with_semaphore(notification_data, index):
            async with semaphore:
                # Add delay based on index to avoid rate limiting
                if index > 0:
                    await asyncio.sleep(delay_between_messages * (index % max_concurrent))
                
                return await self._send_single_notification(notification_data)
        
        # Execute all notifications
        tasks = [
            _send_with_semaphore(notification, i)
            for i, notification in enumerate(notifications)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_result = NotificationStatus(
                    video_id=notifications[i].get("video_id", "unknown"),
                    chat_id=notifications[i].get("chat_id", "unknown"),
                    success=False,
                    error_message=str(result)
                )
                processed_results.append(error_result)
            else:
                processed_results.append(result)
        
        successful = sum(1 for r in processed_results if r.success)
        logger.info(f"Batch notifications complete: {successful}/{len(notifications)} successful")
        
        return processed_results
    
    async def _send_single_notification(self, notification_data: Dict[str, Any]) -> NotificationStatus:
        """Send a single notification based on type."""
        notification_type = notification_data.get("type", "video")
        
        if notification_type == "video":
            return await self.send_video_notification(
                video=notification_data["video"],
                summary=notification_data.get("summary"),
                chat_id=notification_data["chat_id"]
            )
        elif notification_type == "status":
            return await telegram_agent.send_status_update(
                channel_name=notification_data["channel_name"],
                videos_processed=notification_data["videos_processed"],
                chat_id=notification_data["chat_id"],
                last_check=notification_data.get("last_check")
            )
        elif notification_type == "error":
            return await telegram_agent.send_error_alert(
                error_type=notification_data["error_type"],
                error_details=notification_data["error_details"],
                channel_name=notification_data["channel_name"],
                chat_id=notification_data["chat_id"]
            )
        else:
            # Generic message
            from tools.telegram_tools import send_telegram_message
            return await send_telegram_message(
                chat_id=notification_data["chat_id"],
                message_text=notification_data["message_text"],
                parse_mode=notification_data.get("parse_mode", "Markdown")
            )
    
    async def send_summary_notification(
        self,
        channel_name: str,
        videos_processed: int,
        notifications_sent: int,
        errors: List[str],
        chat_id: str
    ) -> NotificationStatus:
        """
        Send a summary notification after processing multiple videos.
        
        Args:
            channel_name: Name of the channel
            videos_processed: Number of videos processed
            notifications_sent: Number of notifications sent
            errors: List of errors encountered
            chat_id: Telegram chat ID
            
        Returns:
            NotificationStatus with delivery result
        """
        logger.info(f"Sending summary notification for {safe_log_text(channel_name)}")
        
        # Format summary message
        error_text = ""
        if errors:
            error_count = len(errors)
            error_text = f"\n⚠️ {error_count} error{'s' if error_count > 1 else ''} encountered"
        
        summary_text = f"""📊 *Processing Summary for {channel_name}*

✅ Videos processed: {videos_processed}
📬 Notifications sent: {notifications_sent}
🕒 Completed at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}{error_text}

_Automated by YouTube Tracker Bot_ 🤖"""
        
        try:
            from tools.telegram_tools import send_telegram_message
            result = await send_telegram_message(
                chat_id=chat_id,
                message_text=summary_text,
                parse_mode="Markdown"
            )
            
            result.video_id = "summary"
            return result
            
        except Exception as e:
            logger.error(f"Failed to send summary notification: {e}")
            return NotificationStatus(
                video_id="summary",
                chat_id=chat_id,
                success=False,
                error_message=str(e)
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get notification chain statistics."""
        return {
            "notifications_processed": self.notifications_processed,
            "delivery_failures": self.delivery_failures,
            "success_rate": (
                (self.notifications_processed - self.delivery_failures) / self.notifications_processed
                if self.notifications_processed > 0
                else 0.0
            )
        }


# Global chain instance
notification_chain = NotificationChain()


# LangChain compatible functions
async def send_video_notification_chain(inputs: Dict[str, Any]) -> NotificationStatus:
    """Send video notification (LangChain compatible)."""
    return await notification_chain.send_video_notification(
        video=inputs["video"],
        summary=inputs.get("summary"),
        chat_id=inputs["chat_id"],
        max_retries=inputs.get("max_retries", 3)
    )


async def send_batch_notifications_chain(inputs: Dict[str, Any]) -> List[NotificationStatus]:
    """Send batch notifications (LangChain compatible)."""
    return await notification_chain.send_batch_notifications(
        notifications=inputs["notifications"],
        delay_between_messages=inputs.get("delay_between_messages", 2.0),
        max_concurrent=inputs.get("max_concurrent", 3)
    )


def create_notification_chain() -> RunnableSequence:
    """
    Create a LangChain compatible notification chain.
    
    Returns:
        RunnableSequence for notification delivery
    """
    return (
        RunnablePassthrough()
        | RunnableLambda(send_video_notification_chain)
    )


def create_batch_notification_chain() -> RunnableSequence:
    """
    Create a LangChain compatible batch notification chain.
    
    Returns:
        RunnableSequence for batch notification delivery
    """
    return (
        RunnablePassthrough()
        | RunnableLambda(send_batch_notifications_chain)
    )