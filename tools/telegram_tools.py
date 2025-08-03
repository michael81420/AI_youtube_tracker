"""
Telegram Bot API integration tools with rate limiting and rich formatting.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
from langchain_core.tools import tool

from config.settings import get_settings
from models.video import VideoMetadata
from models.notification import NotificationMessage, NotificationStatus

# Setup logging
logger = logging.getLogger(__name__)

# Custom exceptions
class TelegramError(Exception):
    """Base Telegram API error."""
    pass

class TelegramRateLimitError(TelegramError):
    """Telegram rate limit exceeded."""
    pass

class TelegramAuthError(TelegramError):
    """Telegram authentication error."""  
    pass

class TelegramChatNotFoundError(TelegramError):
    """Telegram chat not found."""
    pass


class TelegramAPIClient:
    """Async Telegram Bot API client with rate limiting."""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"
        self.request_count = 0
        self.last_request_time = None
        
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to Telegram API with rate limiting."""
        
        # Rate limiting: respect Telegram limits (30 messages per second to same chat)
        if self.last_request_time:
            time_since_last = datetime.utcnow() - self.last_request_time
            min_interval = timedelta(seconds=60 / self.settings.telegram_messages_per_minute)
            
            if time_since_last < min_interval:
                sleep_time = (min_interval - time_since_last).total_seconds()
                await asyncio.sleep(sleep_time)
        
        self.last_request_time = datetime.utcnow()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                url = f"{self.base_url}/{endpoint}"
                
                if method.upper() == "GET":
                    response = await client.get(url, params=data or {})
                else:
                    response = await client.post(url, json=data or {})
                
                # Handle different HTTP status codes
                if response.status_code == 200:
                    self.request_count += 1
                    result = response.json()
                    
                    if not result.get("ok"):
                        error_code = result.get("error_code", 0)
                        error_description = result.get("description", "Unknown error")
                        
                        if error_code == 401:
                            raise TelegramAuthError(f"Authentication failed: {error_description}")
                        elif error_code == 400 and "chat not found" in error_description.lower():
                            raise TelegramChatNotFoundError(f"Chat not found: {error_description}")
                        elif error_code == 429:
                            retry_after = result.get("parameters", {}).get("retry_after", 60)
                            logger.warning(f"Rate limited, waiting {retry_after} seconds")
                            await asyncio.sleep(retry_after)
                            return await self._make_request(method, endpoint, data)
                        else:
                            raise TelegramError(f"API error {error_code}: {error_description}")
                    
                    return result
                
                elif response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"HTTP 429: Rate limited, waiting {retry_after} seconds")
                    await asyncio.sleep(retry_after)
                    return await self._make_request(method, endpoint, data)
                
                else:
                    response.raise_for_status()
                    
            except httpx.RequestError as e:
                logger.error(f"HTTP request failed: {e}")
                raise TelegramError(f"Request failed: {e}")
    
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
        disable_web_page_preview: bool = False,
        reply_markup: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send a message to a Telegram chat."""
        
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview
        }
        
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        return await self._make_request("POST", "sendMessage", data)
    
    async def send_photo(
        self,
        chat_id: str,
        photo_url: str,
        caption: Optional[str] = None,
        parse_mode: str = "Markdown"
    ) -> Dict[str, Any]:
        """Send a photo with optional caption."""
        
        data = {
            "chat_id": chat_id,
            "photo": photo_url,
            "parse_mode": parse_mode
        }
        
        if caption:
            data["caption"] = caption
        
        return await self._make_request("POST", "sendPhoto", data)
    
    async def get_chat(self, chat_id: str) -> Dict[str, Any]:
        """Get information about a chat."""
        return await self._make_request("GET", "getChat", {"chat_id": chat_id})
    
    async def get_me(self) -> Dict[str, Any]:
        """Get information about the bot."""
        return await self._make_request("GET", "getMe")


# Global client instance
telegram_client = TelegramAPIClient()


def format_video_notification(video: VideoMetadata, summary: Optional[str] = None) -> str:
    """
    Format a video notification message with rich formatting.
    
    Args:
        video: VideoMetadata object
        summary: Optional video summary
        
    Returns:
        Formatted message string in Markdown
    """
    # Escape special Markdown characters in title
    title = video.title.replace("[", "\\[").replace("]", "\\]").replace("_", "\\_")
    
    # Format duration
    duration_text = ""
    if video.duration_seconds:
        minutes = video.duration_seconds // 60
        seconds = video.duration_seconds % 60
        duration_text = f" ({minutes}:{seconds:02d})"
    
    # Format view count
    view_text = ""
    if video.view_count:
        if video.view_count >= 1_000_000:
            view_text = f" • {video.view_count/1_000_000:.1f}M views"
        elif video.view_count >= 1_000:
            view_text = f" • {video.view_count/1_000:.1f}K views"
        else:
            view_text = f" • {video.view_count} views"
    
    # Start building message
    message_parts = [
        "*New Video Alert*",
        "",
        f"*{title}*{duration_text}",
        f"Published: {video.published_at.strftime('%Y-%m-%d %H:%M')} UTC{view_text}",
        ""
    ]
    
    # Add summary if available
    if summary:
        message_parts.extend([
            "📝 *Summary:*",
            summary,
            ""
        ])
    
    # Add video link
    message_parts.extend([
        f"🔗 [Watch Video]({video.url})",
        ""
    ])
    
    # Add footer
    message_parts.append("_Powered by YouTube Tracker Bot_")
    
    return "\n".join(message_parts)


def format_status_message(
    channel_name: str,
    videos_processed: int,
    last_check: Optional[datetime] = None
) -> str:
    """
    Format a status update message.
    
    Args:
        channel_name: Name of the channel
        videos_processed: Number of videos processed
        last_check: Last check timestamp
        
    Returns:
        Formatted status message
    """
    last_check_text = "Never"
    if last_check:
        last_check_text = last_check.strftime('%Y-%m-%d %H:%M UTC')
    
    return f"""📊 *Channel Status Update*

*Channel:* {channel_name}
*Videos Processed:* {videos_processed}
*Last Check:* {last_check_text}

_Status updated at {datetime.utcnow().strftime('%H:%M UTC')}_"""


def format_error_message(error_type: str, error_details: str, channel_name: str) -> str:
    """
    Format an error alert message.
    
    Args:
        error_type: Type of error
        error_details: Error details
        channel_name: Name of the affected channel
        
    Returns:
        Formatted error message
    """
    return f"""*Error Alert*

*Channel:* {channel_name}
*Error Type:* {error_type}
*Details:* {error_details}
*Time:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

Please check the system logs for more information."""


@tool
async def send_telegram_message(
    chat_id: str,
    message_text: str,
    parse_mode: str = "Markdown",
    disable_web_page_preview: bool = False
) -> NotificationStatus:
    """
    Send a message to a Telegram chat.
    
    Args:
        chat_id: Telegram chat ID
        message_text: Message text to send
        parse_mode: Message parse mode (Markdown, HTML, or None)
        disable_web_page_preview: Whether to disable web page preview
        
    Returns:
        NotificationStatus with delivery result
    """
    try:
        logger.info(f"Sending message to chat {chat_id}")
        
        # Validate message length (Telegram limit: 4096 characters)
        if len(message_text) > 4096:
            logger.warning(f"Message too long ({len(message_text)} chars), truncating")
            message_text = message_text[:4093] + "..."
        
        # Send message
        result = await telegram_client.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        
        # Create notification status
        notification = NotificationStatus(
            video_id="",  # Will be set by caller
            chat_id=chat_id,
            success=True,
            message_id=result["result"]["message_id"]
        )
        
        logger.info(f"Successfully sent message to chat {chat_id}")
        return notification
        
    except Exception as e:
        logger.error(f"Failed to send message to chat {chat_id}: {e}")
        
        notification = NotificationStatus(
            video_id="",  # Will be set by caller
            chat_id=chat_id,
            success=False,
            error_message=str(e)
        )
        
        return notification


@tool
async def send_video_notification(
    video: VideoMetadata,
    summary: Optional[str],
    chat_id: str,
    include_thumbnail: bool = True
) -> NotificationStatus:
    """
    Send a formatted video notification with optional thumbnail.
    
    Args:
        video: VideoMetadata object
        summary: Video summary text
        chat_id: Telegram chat ID
        include_thumbnail: Whether to include video thumbnail
        
    Returns:
        NotificationStatus with delivery result
    """
    try:
        logger.info(f"Sending video notification for {video.video_id} to chat {chat_id}")
        
        # Format notification message
        message_text = format_video_notification(video, summary)
        
        if include_thumbnail and video.thumbnail_url:
            # Send as photo with caption
            result = await telegram_client.send_photo(
                chat_id=chat_id,
                photo_url=video.thumbnail_url,
                caption=message_text,
                parse_mode="Markdown"
            )
        else:
            # Send as text message
            result = await telegram_client.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="Markdown",
                disable_web_page_preview=False
            )
        
        # Create notification status
        notification = NotificationStatus(
            video_id=video.video_id,
            chat_id=chat_id,
            success=True,
            message_id=result["result"]["message_id"]
        )
        
        logger.info(f"Successfully sent video notification for {video.video_id}")
        return notification
        
    except Exception as e:
        logger.error(f"Failed to send video notification for {video.video_id}: {e}")
        
        notification = NotificationStatus(
            video_id=video.video_id,
            chat_id=chat_id,
            success=False,
            error_message=str(e)
        )
        
        return notification


@tool
async def validate_telegram_chat(chat_id: str) -> bool:
    """
    Validate that a Telegram chat exists and bot has access.
    
    Args:
        chat_id: Telegram chat ID to validate
        
    Returns:
        True if chat is valid and accessible, False otherwise
    """
    try:
        await telegram_client.get_chat(chat_id)
        return True
    except TelegramChatNotFoundError:
        return False
    except Exception as e:
        logger.warning(f"Error validating chat {chat_id}: {e}")
        return False


@tool
async def get_bot_info() -> Dict[str, Any]:
    """
    Get information about the Telegram bot.
    
    Returns:
        Bot information dictionary
    """
    try:
        result = await telegram_client.get_me()
        return result["result"]
    except Exception as e:
        logger.error(f"Failed to get bot info: {e}")
        raise TelegramError(f"Failed to get bot info: {e}")


def format_video_message(video: VideoMetadata, summary: Optional[str] = None) -> NotificationMessage:
    """
    Create a formatted NotificationMessage for a video.
    
    Args:
        video: VideoMetadata object
        summary: Optional video summary
        
    Returns:
        NotificationMessage object
    """
    message_text = format_video_notification(video, summary)
    
    return NotificationMessage(
        chat_id="",  # Will be set by caller
        message_text=message_text,
        parse_mode="Markdown",
        disable_web_page_preview=False
    )


def get_telegram_stats() -> Dict[str, Any]:
    """Get Telegram client statistics."""
    return {
        "requests_made": telegram_client.request_count,
        "rate_limit_per_minute": telegram_client.settings.telegram_messages_per_minute,
        "bot_token_configured": bool(telegram_client.settings.telegram_bot_token)
    }