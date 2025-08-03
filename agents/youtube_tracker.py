"""
Main YouTube tracking agent with tool composition and coordination.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from models.channel import ChannelConfig, ChannelStatus
from models.video import VideoMetadata, VideoSummary
from models.notification import NotificationStatus
from storage.database import get_session, DatabaseUtils
from storage.database import Channel, Video, Notification
from tools.youtube_tools import get_channel_videos, get_video_metadata
from agents.summarizer_agent import summarize_video_content
from agents.telegram_agent import notify_new_video, notify_error
from utils import safe_log_text

# Setup logging
logger = logging.getLogger(__name__)


class YouTubeTrackerAgent:
    """Main agent for tracking YouTube channels and coordinating video processing."""
    
    def __init__(self):
        self.settings = get_settings()
        self.channels_processed = 0
        self.videos_processed = 0
        self.errors_encountered = 0
        
    async def track_channel(
        self,
        channel_config: ChannelConfig,
        force_check: bool = False
    ) -> Dict[str, Any]:
        """
        Track a YouTube channel for new videos.
        
        Args:
            channel_config: Channel configuration and state
            force_check: Force check even if within check interval
            
        Returns:
            Dictionary with tracking results
        """
        logger.info(f"Starting tracking for channel {channel_config.channel_id} ({safe_log_text(channel_config.channel_name)})")
        start_time = datetime.utcnow()
        
        result = {
            "channel_id": channel_config.channel_id,
            "channel_name": channel_config.channel_name,
            "success": False,
            "videos_found": 0,
            "videos_processed": 0,
            "notifications_sent": 0,
            "errors": [],
            "processing_time_seconds": 0
        }
        
        try:
            # Check if we should skip this check based on interval
            if not force_check and channel_config.last_check:
                time_since_check = datetime.utcnow() - channel_config.last_check
                if time_since_check.total_seconds() < channel_config.check_interval:
                    logger.info(f"Skipping channel {channel_config.channel_id} - within check interval")
                    result["success"] = True
                    result["skipped"] = True
                    return result
            
            # Get new videos from channel
            try:
                published_after = channel_config.last_check or (datetime.utcnow() - timedelta(days=1))
                videos = await get_channel_videos(
                    channel_id=channel_config.channel_id,
                    published_after=published_after,
                    max_results=self.settings.max_videos_per_check
                )
                result["videos_found"] = len(videos)
                logger.info(f"Found {len(videos)} videos for channel {channel_config.channel_id}")
                
            except Exception as e:
                error_msg = f"Failed to fetch videos: {str(e)}"
                logger.error(f"Channel {channel_config.channel_id}: {error_msg}")
                result["errors"].append(error_msg)
                self.errors_encountered += 1
                
                # Send error notification
                await self._send_error_notification(
                    channel_config=channel_config,
                    error_type="YouTube API Error",
                    error_details=error_msg
                )
                return result
            
            # Process each video
            processed_videos = []
            for video in videos:
                try:
                    processed_video = await self._process_video(video, channel_config)
                    if processed_video:
                        processed_videos.append(processed_video)
                        result["videos_processed"] += 1
                        
                except Exception as e:
                    error_msg = f"Failed to process video {video.video_id}: {str(e)}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                    continue
            
            # Update channel state in database
            try:
                await self._update_channel_state(channel_config, videos)
                logger.info(f"Updated channel state for {channel_config.channel_id}")
                
            except Exception as e:
                error_msg = f"Failed to update channel state: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
            
            # Calculate results
            result["success"] = True
            result["notifications_sent"] = sum(
                1 for v in processed_videos if v.get("notification_sent", False)
            )
            self.channels_processed += 1
            self.videos_processed += len(processed_videos)
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            result["processing_time_seconds"] = processing_time
            
            logger.info(
                f"Completed tracking for {channel_config.channel_name}: "
                f"{result['videos_processed']} videos processed, "
                f"{result['notifications_sent']} notifications sent in {processing_time:.2f}s"
            )
            
            return result
            
        except Exception as e:
            error_msg = f"Unexpected error tracking channel: {str(e)}"
            logger.error(f"Channel {channel_config.channel_id}: {error_msg}")
            result["errors"].append(error_msg)
            self.errors_encountered += 1
            return result
    
    async def _process_video(
        self,
        video: VideoMetadata,
        channel_config: ChannelConfig
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single video: summarize and send notification.
        
        Args:
            video: Video metadata
            channel_config: Channel configuration
            
        Returns:
            Processing result dictionary or None if failed
        """
        logger.info(f"Processing video {video.video_id}: {safe_log_text(video.title)}")
        
        result = {
            "video_id": video.video_id,
            "title": video.title,
            "summary_generated": False,
            "notification_sent": False,
            "error": None
        }
        
        try:
            # Check if video already exists in database and handle notification status
            async for session in get_session():
                existing_video = await DatabaseUtils.get_video_by_id(session, video.video_id)
                if existing_video:
                    # If notification already sent, skip completely
                    if existing_video.notification_sent:
                        logger.info(f"Video {video.video_id} notification already sent, skipping")
                        result["already_processed"] = True
                        result["notification_sent"] = True
                        return result
                    
                    # If processed but notification not sent, skip to notification step
                    if existing_video.processed_at and existing_video.summary:
                        logger.info(f"Video {video.video_id} already processed, proceeding to notification")
                        result["already_processed"] = True
                        result["summary_generated"] = True
                        result["summary"] = existing_video.summary
                        
                        # Send notification for already processed video
                        try:
                            notification_result = await notify_new_video.ainvoke({
                                "video": video,
                                "summary": existing_video.summary,
                                "chat_id": channel_config.telegram_chat_id
                            })
                            
                            result["notification_sent"] = notification_result.success
                            if not notification_result.success:
                                result["notification_error"] = notification_result.error_message
                            
                        except Exception as e:
                            result["notification_error"] = f"Notification failed: {str(e)}"
                            logger.error(f"Video {video.video_id}: Notification failed: {e}")
                        
                        # Update notification status in database
                        await self._save_video_to_database(
                            video=video,
                            summary=existing_video.summary,
                            notification_sent=result["notification_sent"]
                        )
                        
                        return result
                break
            
            # Generate summary
            try:
                summary_result = await summarize_video_content.ainvoke({"video": video})
                result["summary_generated"] = True
                result["summary"] = summary_result.summary
                logger.info(f"Generated summary for video {video.video_id}")
                
            except Exception as e:
                error_msg = f"Summarization failed: {str(e)}"
                logger.warning(f"Video {video.video_id}: {error_msg}")
                result["error"] = error_msg
                summary_result = None
            
            # Send notification (always send, even if summarization failed)
            try:
                summary_text = summary_result.summary if summary_result else None
                notification_result = await notify_new_video.ainvoke({
                    "video": video,
                    "summary": summary_text,
                    "chat_id": channel_config.telegram_chat_id
                })
                
                result["notification_sent"] = notification_result.success
                if not notification_result.success:
                    result["notification_error"] = notification_result.error_message
                
                logger.info(f"Notification sent for video {video.video_id}: {notification_result.success}")
                
            except Exception as e:
                error_msg = f"Notification failed: {str(e)}"
                logger.warning(f"Video {video.video_id}: {error_msg}")
                result["notification_error"] = error_msg
            
            # Save to database
            try:
                await self._save_video_to_database(
                    video=video,
                    summary=summary_result.summary if summary_result else None,
                    notification_sent=result["notification_sent"]
                )
                logger.info(f"Saved video {video.video_id} to database")
                
            except Exception as e:
                error_msg = f"Database save failed: {str(e)}"
                logger.error(f"Video {video.video_id}: {error_msg}")
                result["database_error"] = error_msg
            
            return result
            
        except Exception as e:
            error_msg = f"Unexpected error processing video: {str(e)}"
            logger.error(f"Video {video.video_id}: {error_msg}")
            result["error"] = error_msg
            return result
    
    async def _save_video_to_database(
        self,
        video: VideoMetadata,
        summary: Optional[str] = None,
        notification_sent: bool = False
    ) -> None:
        """Save video and processing state to database."""
        
        async for session in get_session():
            try:
                # Create or update video record
                existing_video = await DatabaseUtils.get_video_by_id(session, video.video_id)
                
                if existing_video:
                    # Update existing video
                    existing_video.processed_at = datetime.utcnow()
                    existing_video.summary = summary
                    existing_video.notification_sent = notification_sent
                    existing_video.view_count = video.view_count
                    existing_video.like_count = video.like_count
                    existing_video.comment_count = video.comment_count
                else:
                    # Create new video record
                    new_video = Video(
                        video_id=video.video_id,
                        channel_id=video.channel_id,
                        title=video.title,
                        description=video.description,
                        published_at=video.published_at,
                        thumbnail_url=video.thumbnail_url,
                        duration=video.duration,
                        view_count=video.view_count,
                        like_count=video.like_count,
                        comment_count=video.comment_count,
                        processed_at=datetime.utcnow(),
                        summary=summary,
                        notification_sent=notification_sent
                    )
                    session.add(new_video)
                
                await session.commit()
                logger.debug(f"Saved video {video.video_id} to database")
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Database error saving video {video.video_id}: {e}")
                raise
            break
    
    async def _update_channel_state(
        self,
        channel_config: ChannelConfig,
        videos: List[VideoMetadata]
    ) -> None:
        """Update channel state in database."""
        
        async for session in get_session():
            try:
                # Get or create channel record
                channel = await DatabaseUtils.get_channel_by_id(session, channel_config.channel_id)
                
                if channel:
                    # Update existing channel
                    channel.last_check = datetime.utcnow()
                    if videos:
                        channel.last_video_id = videos[0].video_id  # Most recent video
                    channel.channel_name = channel_config.channel_name  # Update name if changed
                else:
                    # Create new channel record
                    channel = Channel(
                        channel_id=channel_config.channel_id,
                        channel_name=channel_config.channel_name,
                        check_interval=channel_config.check_interval,
                        telegram_chat_id=channel_config.telegram_chat_id,
                        last_check=datetime.utcnow(),
                        last_video_id=videos[0].video_id if videos else None,
                        is_active=True
                    )
                    session.add(channel)
                
                await session.commit()
                logger.debug(f"Updated channel state for {channel_config.channel_id}")
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Database error updating channel {channel_config.channel_id}: {e}")
                raise
            break
    
    async def _send_error_notification(
        self,
        channel_config: ChannelConfig,
        error_type: str,
        error_details: str
    ) -> None:
        """Send error notification to Telegram."""
        try:
            await notify_error(
                error_type=error_type,
                error_details=error_details,
                channel_name=channel_config.channel_name,
                chat_id=channel_config.telegram_chat_id
            )
            logger.info(f"Sent error notification for channel {safe_log_text(channel_config.channel_name)}")
            
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
    
    async def get_channel_status(self, channel_id: str) -> Optional[ChannelStatus]:
        """
        Get status information for a channel.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            ChannelStatus object or None if not found
        """
        try:
            async for session in get_session():
                channel = await DatabaseUtils.get_channel_by_id(session, channel_id)
                if not channel:
                    return None
                
                # Get video statistics
                from sqlalchemy import select, func
                video_count_result = await session.execute(
                    select(func.count(Video.id)).where(Video.channel_id == channel_id)
                )
                total_videos = video_count_result.scalar() or 0
                
                # Get today's video count
                today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                today_count_result = await session.execute(
                    select(func.count(Video.id)).where(
                        Video.channel_id == channel_id,
                        Video.processed_at >= today
                    )
                )
                videos_today = today_count_result.scalar() or 0
                
                return ChannelStatus(
                    channel_id=channel.channel_id,
                    channel_name=channel.channel_name,
                    is_active=channel.is_active,
                    last_check=channel.last_check,
                    last_successful_check=channel.last_check,  # Simplified
                    total_videos_processed=total_videos,
                    videos_processed_today=videos_today,
                    consecutive_failures=0,  # Would need tracking logic
                    last_error=None,
                    last_error_time=None
                )
                break
                
        except Exception as e:
            logger.error(f"Error getting channel status for {channel_id}: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "channels_processed": self.channels_processed,
            "videos_processed": self.videos_processed,
            "errors_encountered": self.errors_encountered,
            "success_rate": (
                self.channels_processed / (self.channels_processed + self.errors_encountered)
                if (self.channels_processed + self.errors_encountered) > 0
                else 0.0
            )
        }


# Global agent instance
youtube_tracker_agent = YouTubeTrackerAgent()


# LangChain tools
@tool
async def track_youtube_channel(
    channel_id: str,
    channel_name: str,
    telegram_chat_id: str,
    check_interval: int = 3600,
    force_check: bool = False
) -> Dict[str, Any]:
    """
    Track a YouTube channel for new videos.
    
    Args:
        channel_id: YouTube channel ID
        channel_name: Human-readable channel name
        telegram_chat_id: Telegram chat ID for notifications
        check_interval: Check interval in seconds
        force_check: Force check even if within interval
        
    Returns:
        Tracking result dictionary
    """
    channel_config = ChannelConfig(
        channel_id=channel_id,
        channel_name=channel_name,
        telegram_chat_id=telegram_chat_id,
        check_interval=check_interval
    )
    
    return await youtube_tracker_agent.track_channel(channel_config, force_check)


@tool
async def get_youtube_channel_status(channel_id: str) -> Optional[ChannelStatus]:
    """
    Get status information for a YouTube channel.
    
    Args:
        channel_id: YouTube channel ID
        
    Returns:
        ChannelStatus object or None if not found
    """
    return await youtube_tracker_agent.get_channel_status(channel_id)


@tool
async def process_single_video(
    video_id: str,
    telegram_chat_id: str
) -> Dict[str, Any]:
    """
    Process a single video by ID.
    
    Args:
        video_id: YouTube video ID
        telegram_chat_id: Telegram chat ID for notification
        
    Returns:
        Processing result dictionary
    """
    try:
        # Get video metadata
        video = await get_video_metadata(video_id)
        
        # Create temporary channel config
        channel_config = ChannelConfig(
            channel_id=video.channel_id,
            channel_name="Manual Processing",
            telegram_chat_id=telegram_chat_id
        )
        
        # Process the video
        result = await youtube_tracker_agent._process_video(video, channel_config)
        
        return {
            "success": True,
            "video_id": video_id,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error processing single video {video_id}: {e}")
        return {
            "success": False,
            "video_id": video_id,
            "error": str(e)
        }