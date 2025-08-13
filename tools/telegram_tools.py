"""
Telegram Bot API integration tools with rate limiting and rich formatting.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

import httpx
from langchain_core.tools import tool

from config.settings import get_settings
from models.video import VideoMetadata
from models.notification import NotificationMessage, NotificationStatus

# Setup logging
logger = logging.getLogger(__name__)

# Retry queue for failed notifications
RETRY_QUEUE_FILE = Path("data/telegram_retry_queue.json")
# Default retry delay is now configurable via environment variable
# RETRY_DELAY_MINUTES is now loaded from settings
MAX_RETRY_ATTEMPTS = 3

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


class RetryQueueManager:
    """Manages the retry queue for failed Telegram notifications."""
    
    @staticmethod
    async def add_to_retry_queue(
        video: VideoMetadata,
        summary: Optional[str],
        chat_id: str,
        include_thumbnail: bool,
        retry_count: int = 0,
        error_message: str = ""
    ):
        """Add a failed notification to the retry queue with duplicate prevention."""
        
        # Don't add if retry count exceeds maximum
        if retry_count >= MAX_RETRY_ATTEMPTS:
            logger.warning(f"Not adding video {video.video_id} to retry queue - exceeds max attempts ({MAX_RETRY_ATTEMPTS})")
            return
        
        retry_item = {
            "video": {
                "video_id": video.video_id,
                "channel_id": video.channel_id,
                "title": video.title,
                "description": video.description,
                "published_at": video.published_at.isoformat(),
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "view_count": video.view_count,
                "like_count": video.like_count,
                "comment_count": video.comment_count,
                "url": video.url
            },
            "summary": summary,
            "chat_id": chat_id,
            "include_thumbnail": include_thumbnail,
            "retry_count": retry_count,
            "error_message": error_message,
            "retry_after": (datetime.utcnow() + timedelta(minutes=get_settings().telegram_retry_delay_minutes)).isoformat(),
            "added_at": datetime.utcnow().isoformat()
        }
        
        # Ensure data directory exists
        RETRY_QUEUE_FILE.parent.mkdir(exist_ok=True)
        
        # Load existing queue
        queue = []
        if RETRY_QUEUE_FILE.exists():
            try:
                with open(RETRY_QUEUE_FILE, 'r', encoding='utf-8') as f:
                    queue = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load retry queue: {e}")
                queue = []
        
        # Check for existing duplicate entries for this video_id + chat_id combination
        existing_count = sum(1 for item in queue 
                           if item.get("video", {}).get("video_id") == video.video_id 
                           and item.get("chat_id") == chat_id)
        
        if existing_count > 0:
            logger.warning(f"Video {video.video_id} already has {existing_count} entries in retry queue for chat {chat_id} - not adding duplicate")
            return
        
        # Add new item
        queue.append(retry_item)
        
        # Save queue
        try:
            with open(RETRY_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=2, ensure_ascii=False)
            logger.info(f"Added video {video.video_id} to retry queue (attempt {retry_count + 1})")
        except IOError as e:
            logger.error(f"Failed to save retry queue: {e}")
    
    @staticmethod
    async def get_ready_retries() -> List[Dict]:
        """Get retry items that are ready to be processed."""
        if not RETRY_QUEUE_FILE.exists():
            return []
        
        try:
            with open(RETRY_QUEUE_FILE, 'r', encoding='utf-8') as f:
                queue = json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
        
        now = datetime.utcnow()
        ready_items = []
        
        for item in queue:
            retry_after = datetime.fromisoformat(item["retry_after"])
            if now >= retry_after:
                ready_items.append(item)
        
        return ready_items
    
    @staticmethod
    async def remove_from_queue(video_id: str):
        """Remove an item from the retry queue."""
        if not RETRY_QUEUE_FILE.exists():
            return
        
        try:
            with open(RETRY_QUEUE_FILE, 'r', encoding='utf-8') as f:
                queue = json.load(f)
            
            # Filter out the item
            queue = [item for item in queue if item["video"]["video_id"] != video_id]
            
            with open(RETRY_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=2, ensure_ascii=False)
                
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to update retry queue: {e}")
    
    @staticmethod
    async def update_retry_count(video_id: str, new_retry_count: int):
        """Update retry count for a specific video in the queue."""
        if not RETRY_QUEUE_FILE.exists():
            return
        
        try:
            with open(RETRY_QUEUE_FILE, 'r', encoding='utf-8') as f:
                queue = json.load(f)
            
            # Update retry count for matching items
            updated = False
            for item in queue:
                if item["video"]["video_id"] == video_id:
                    item["retry_count"] = new_retry_count
                    # Update retry_after time for next attempt
                    item["retry_after"] = (datetime.utcnow() + timedelta(minutes=get_settings().telegram_retry_delay_minutes)).isoformat()
                    updated = True
            
            if updated:
                with open(RETRY_QUEUE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(queue, f, indent=2, ensure_ascii=False)
                    
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to update retry count in queue: {e}")
    
    @staticmethod
    async def cleanup_retry_queue():
        """Clean up retry queue by removing duplicates and expired items."""
        if not RETRY_QUEUE_FILE.exists():
            return {"cleaned": 0, "message": "No retry queue file found"}
        
        try:
            with open(RETRY_QUEUE_FILE, 'r', encoding='utf-8') as f:
                queue = json.load(f)
            
            original_count = len(queue)
            
            # Remove items that exceed max retry attempts
            queue = [item for item in queue if item.get("retry_count", 0) < MAX_RETRY_ATTEMPTS]
            
            # Remove duplicates - keep only the latest entry for each video_id + chat_id combination
            seen = {}
            cleaned_queue = []
            
            # Sort by added_at to keep the latest entries
            queue.sort(key=lambda x: x.get("added_at", ""))
            
            for item in queue:
                video_id = item.get("video", {}).get("video_id")
                chat_id = item.get("chat_id")
                key = f"{video_id}_{chat_id}"
                
                if key not in seen:
                    seen[key] = True
                    cleaned_queue.append(item)
            
            # Save cleaned queue
            with open(RETRY_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cleaned_queue, f, indent=2, ensure_ascii=False)
            
            cleaned_count = original_count - len(cleaned_queue)
            logger.info(f"Cleaned retry queue: removed {cleaned_count} items ({original_count} -> {len(cleaned_queue)})")
            
            return {
                "success": True,
                "cleaned": cleaned_count,
                "original_count": original_count,
                "final_count": len(cleaned_queue),
                "message": f"Cleaned {cleaned_count} duplicate/expired items from retry queue"
            }
            
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to clean retry queue: {e}")
            return {
                "success": False,
                "cleaned": 0,
                "error": str(e),
                "message": "Failed to clean retry queue"
            }


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
        disable_web_page_preview: bool = False,
        reply_markup: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send a message to a Telegram chat."""
        
        data = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview
        }
        
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        return await self._make_request("POST", "sendMessage", data)
    
    async def send_photo(
        self,
        chat_id: str,
        photo_url: str,
        caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a photo with optional caption."""
        
        data = {
            "chat_id": chat_id,
            "photo": photo_url
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
    title = video.title.replace("\\", "\\\\").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]").replace("_", "\\_").replace("`", "\\`")
    
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
            "*Summary:*",
            summary,
            ""
        ])
    
    # Add video link
    message_parts.extend([
        f"[Watch Video]({video.url})",
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
    
    return f"""*Channel Status Update*

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
    disable_web_page_preview: bool = False
) -> NotificationStatus:
    """
    Send a message to a Telegram chat.
    
    Args:
        chat_id: Telegram chat ID
        message_text: Message text to send
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
            # Telegram photo captions are limited to 1024 characters
            if len(message_text) > 1000:  # Leave some margin for safety
                # Send photo with short caption, then follow with full message
                # Use the already escaped title from the main formatting
                escaped_title = video.title.replace("\\", "\\\\").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]").replace("_", "\\_").replace("`", "\\`")
                short_caption = f"*{escaped_title[:100]}{'...' if len(escaped_title) > 100 else ''}*\n\n[Watch Video]({video.url})"
                
                try:
                    result = await telegram_client.send_photo(
                        chat_id=chat_id,
                        photo_url=video.thumbnail_url,
                        caption=short_caption,
                                            )
                    
                    # Send full message as follow-up text
                    await telegram_client.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        disable_web_page_preview=True
                    )
                    
                except Exception as e:
                    logger.warning(f"Photo with caption failed, falling back to text-only: {e}")
                    # Fallback to text message
                    result = await telegram_client.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        disable_web_page_preview=False
                    )
            else:
                try:
                    result = await telegram_client.send_photo(
                        chat_id=chat_id,
                        photo_url=video.thumbnail_url,
                        caption=message_text
                    )
                except Exception as e:
                    logger.warning(f"Photo with caption failed, falling back to text-only: {e}")
                    # Fallback to text message
                    result = await telegram_client.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        disable_web_page_preview=False
                    )
        else:
            # Send as text message
            result = await telegram_client.send_message(
                chat_id=chat_id,
                text=message_text,
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
        
        # Check if this is a retry attempt or already being processed by retry queue
        retry_count = getattr(video, '_retry_count', 0)
        is_retry_processing = getattr(video, '_is_retry_processing', False)
        
        # Only add to retry queue if not already being processed by retry queue and under max attempts
        if not is_retry_processing and retry_count < MAX_RETRY_ATTEMPTS:
            await RetryQueueManager.add_to_retry_queue(
                video=video,
                summary=summary,
                chat_id=chat_id,
                include_thumbnail=include_thumbnail,
                retry_count=retry_count,
                error_message=str(e)
            )
            logger.info(f"Video {video.video_id} added to retry queue (attempt {retry_count + 1}/{MAX_RETRY_ATTEMPTS})")
        elif is_retry_processing:
            logger.debug(f"Video {video.video_id} failed during retry processing - will not re-add to queue")
        else:
            logger.warning(f"Video {video.video_id} exceeded max retry attempts ({MAX_RETRY_ATTEMPTS}), giving up")
        
        notification = NotificationStatus(
            video_id=video.video_id,
            chat_id=chat_id,
            success=False,
            error_message=str(e),
            retry_count=retry_count
        )
        
        return notification


@tool
async def process_retry_queue() -> Dict[str, Any]:
    """
    Process pending retry notifications.
    
    Returns:
        Dict with processing results
    """
    try:
        ready_items = await RetryQueueManager.get_ready_retries()
        
        if not ready_items:
            return {
                "success": True,
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "message": "No items ready for retry"
            }
        
        logger.info(f"Processing {len(ready_items)} retry notifications")
        
        succeeded = 0
        failed = 0
        processed_ids = []
        
        for item in ready_items:
            try:
                # Check if this item has exceeded max retry attempts
                current_retry_count = item["retry_count"] + 1
                if current_retry_count > MAX_RETRY_ATTEMPTS:
                    # Remove from queue - exceeded max attempts
                    await RetryQueueManager.remove_from_queue(item["video"]["video_id"])
                    logger.warning(f"Video {item['video']['video_id']} exceeded max retry attempts ({MAX_RETRY_ATTEMPTS}), removing from queue")
                    failed += 1
                    processed_ids.append(item["video"]["video_id"])
                    continue
                
                # Reconstruct VideoMetadata from stored data
                video_data = item["video"]
                video = VideoMetadata(
                    video_id=video_data["video_id"],
                    channel_id=video_data.get("channel_id", "UCRETRY_PLACEHOLDER_0000"),  # Use stored channel_id or 24-char placeholder
                    title=video_data["title"],
                    description=video_data["description"],
                    published_at=datetime.fromisoformat(video_data["published_at"]),
                    thumbnail_url=video_data["thumbnail_url"],
                    duration=video_data["duration"],
                    view_count=video_data["view_count"],
                    like_count=video_data["like_count"],
                    comment_count=video_data["comment_count"],
                    url=video_data["url"]
                )
                
                # Mark as retry processing to prevent re-adding to queue
                setattr(video, '_retry_count', current_retry_count)
                setattr(video, '_is_retry_processing', True)
                
                # Use direct Telegram client call instead of send_video_notification
                # to avoid re-adding to retry queue
                try:
                    message_text = format_video_notification(video, item["summary"])
                    
                    if item["include_thumbnail"] and video.thumbnail_url:
                        # Try sending with thumbnail
                        if len(message_text) > 1000:
                            # Send photo with short caption, then follow with full message
                            escaped_title = video.title.replace("\\", "\\\\").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]")\
                                                    .replace("_", "\\_").replace("`", "\\`")
                            short_caption = f"*{escaped_title[:100]}{'...' if len(escaped_title) > 100 else ''}*\n\n[Watch Video]({video.url})"
                            
                            try:
                                await telegram_client.send_photo(
                                    chat_id=item["chat_id"],
                                    photo_url=video.thumbnail_url,
                                    caption=short_caption
                                )
                                await telegram_client.send_message(
                                    chat_id=item["chat_id"],
                                    text=message_text,
                                    disable_web_page_preview=True
                                )
                            except Exception:
                                # Fallback to text message
                                await telegram_client.send_message(
                                    chat_id=item["chat_id"],
                                    text=message_text,
                                    disable_web_page_preview=False
                                )
                        else:
                            try:
                                await telegram_client.send_photo(
                                    chat_id=item["chat_id"],
                                    photo_url=video.thumbnail_url,
                                    caption=message_text
                                )
                            except Exception:
                                # Fallback to text message
                                await telegram_client.send_message(
                                    chat_id=item["chat_id"],
                                    text=message_text,
                                    disable_web_page_preview=False
                                )
                    else:
                        # Send as text message
                        await telegram_client.send_message(
                            chat_id=item["chat_id"],
                            text=message_text,
                            disable_web_page_preview=False
                        )
                    
                    # Success - remove from queue
                    await RetryQueueManager.remove_from_queue(video.video_id)
                    succeeded += 1
                    logger.info(f"Retry successful for video {video.video_id}")
                    
                except Exception as send_error:
                    # Failed to send - check if we should retry again or give up
                    if current_retry_count >= MAX_RETRY_ATTEMPTS:
                        # Remove from queue - exceeded max attempts
                        await RetryQueueManager.remove_from_queue(video.video_id)
                        logger.warning(f"Video {video.video_id} exceeded max retry attempts after failure, removing from queue")
                    else:
                        # Update retry count in queue for next attempt
                        await RetryQueueManager.update_retry_count(video.video_id, current_retry_count)
                        logger.warning(f"Retry failed for video {video.video_id} (attempt {current_retry_count}/{MAX_RETRY_ATTEMPTS}): {send_error}")
                    
                    failed += 1
                
                processed_ids.append(video.video_id)
                
                # Small delay between retries to avoid rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing retry item: {e}")
                # Remove problematic item from queue
                if "video" in item and "video_id" in item["video"]:
                    await RetryQueueManager.remove_from_queue(item["video"]["video_id"])
                failed += 1
        
        return {
            "success": True,
            "processed": len(processed_ids),
            "succeeded": succeeded,
            "failed": failed,
            "processed_ids": processed_ids,
            "message": f"Processed {len(processed_ids)} retry notifications: {succeeded} succeeded, {failed} failed"
        }
        
    except Exception as e:
        logger.error(f"Error processing retry queue: {e}")
        return {
            "success": False,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "error": str(e),
            "message": "Failed to process retry queue"
        }


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
        disable_web_page_preview=False
    )


def get_telegram_stats() -> Dict[str, Any]:
    """Get Telegram client statistics."""
    return {
        "requests_made": telegram_client.request_count,
        "rate_limit_per_minute": telegram_client.settings.telegram_messages_per_minute,
        "bot_token_configured": bool(telegram_client.settings.telegram_bot_token)
    }