"""
Main workflow orchestration chain for YouTube tracking process.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.runnables.base import RunnableSequence

from config.settings import get_settings
from models.channel import ChannelConfig
from models.video import VideoMetadata
from agents.youtube_tracker import youtube_tracker_agent
from agents.summarizer_agent import summarizer_agent
from agents.telegram_agent import telegram_agent
from utils import safe_log_text

# Setup logging
logger = logging.getLogger(__name__)


class TrackingChainError(Exception):
    """Base tracking chain error."""
    pass


class TrackingChain:
    """Main workflow chain orchestrating the YouTube tracking process."""
    
    def __init__(self):
        self.settings = get_settings()
        self.executions = 0
        self.successful_executions = 0
        
    async def execute_tracking_workflow(
        self,
        channel_config: ChannelConfig,
        force_check: bool = False
    ) -> Dict[str, Any]:
        """
        Execute the complete tracking workflow for a channel.
        
        Workflow: Check → Summarize → Notify → Update
        
        Args:
            channel_config: Channel configuration
            force_check: Force check even if within interval
            
        Returns:
            Workflow execution result
        """
        logger.info(f"Starting tracking workflow for {safe_log_text(channel_config.channel_name)}")
        start_time = datetime.utcnow()
        
        workflow_result = {
            "channel_id": channel_config.channel_id,
            "channel_name": channel_config.channel_name,
            "success": False,
            "steps_completed": [],
            "videos_processed": 0,
            "notifications_sent": 0,
            "errors": [],
            "execution_time_seconds": 0
        }
        
        self.executions += 1
        
        try:
            # Step 1: Check for new videos
            check_result = await self._check_for_videos(channel_config, force_check)
            workflow_result["steps_completed"].append("check")
            
            if not check_result["success"]:
                workflow_result["errors"].extend(check_result.get("errors", []))
                return workflow_result
            
            videos = check_result.get("videos", [])
            if not videos:
                logger.info(f"No new videos found for {safe_log_text(channel_config.channel_name)}")
                workflow_result["success"] = True
                workflow_result["no_new_videos"] = True
                return workflow_result
            
            logger.info(f"Found {len(videos)} new videos for {safe_log_text(channel_config.channel_name)}")
            
            # Step 2-4: Process each video individually (includes deduplication, summarization, notification, and database update)
            processed_videos = []
            notifications_sent = 0
            
            from agents.youtube_tracker import youtube_tracker_agent
            
            for video in videos:
                try:
                    process_result = await youtube_tracker_agent._process_video(video, channel_config)
                    processed_videos.append(process_result)
                    
                    if process_result.get("notification_sent", False):
                        notifications_sent += 1
                    
                    if process_result.get("error"):
                        workflow_result["errors"].append(f"Video {video.video_id}: {process_result['error']}")
                    
                except Exception as e:
                    error_msg = f"Failed to process video {video.video_id}: {str(e)}"
                    logger.error(error_msg)
                    workflow_result["errors"].append(error_msg)
            
            workflow_result["steps_completed"].extend(["process", "summarize", "notify", "update"])
            workflow_result["notifications_sent"] = notifications_sent
            
            # Calculate final results
            workflow_result["videos_processed"] = len([v for v in processed_videos if not v.get("already_processed", False)])
            workflow_result["success"] = len(workflow_result["errors"]) == 0
            
            if workflow_result["success"]:
                self.successful_executions += 1
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            workflow_result["execution_time_seconds"] = execution_time
            
            logger.info(
                f"Completed tracking workflow for {channel_config.channel_name}: "
                f"{'SUCCESS' if workflow_result['success'] else 'PARTIAL'} - "
                f"{workflow_result['videos_processed']} videos, "
                f"{workflow_result['notifications_sent']} notifications in {execution_time:.2f}s"
            )
            
            return workflow_result
            
        except Exception as e:
            error_msg = f"Unexpected error in tracking workflow: {str(e)}"
            logger.error(f"Channel {safe_log_text(channel_config.channel_name)}: {error_msg}")
            workflow_result["errors"].append(error_msg)
            
            # Send error notification
            try:
                await telegram_agent.send_error_alert(
                    error_type="Workflow Error",
                    error_details=error_msg,
                    channel_name=channel_config.channel_name,
                    chat_id=channel_config.telegram_chat_id
                )
            except Exception as notify_error:
                logger.error(f"Failed to send error notification: {notify_error}")
            
            return workflow_result
    
    async def _check_for_videos(
        self,
        channel_config: ChannelConfig,
        force_check: bool
    ) -> Dict[str, Any]:
        """Step 1: Check for new videos."""
        logger.info(f"Step 1: Checking for new videos in {safe_log_text(channel_config.channel_name)}")
        
        try:
            from tools.youtube_tools import get_channel_videos
            from datetime import timedelta
            
            # Determine published_after timestamp
            if channel_config.last_check and not force_check:
                published_after = channel_config.last_check
            else:
                published_after = datetime.utcnow() - timedelta(days=1)
            
            # Get max videos from settings
            settings = get_settings()
            
            videos = await get_channel_videos.ainvoke({
                "channel_id": channel_config.channel_id,
                "published_after": published_after,
                "max_results": settings.max_videos_per_check
            })
            
            return {
                "success": True,
                "videos": videos,
                "count": len(videos)
            }
            
        except Exception as e:
            error_msg = f"Failed to check for videos: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "videos": [],
                "errors": [error_msg]
            }
    
    async def _summarize_videos(self, videos: List[VideoMetadata]) -> Dict[str, Any]:
        """Step 2: Summarize videos using LLM."""
        logger.info(f"Step 2: Summarizing {len(videos)} videos")
        
        summaries = {}
        errors = []
        
        for video in videos:
            try:
                summary_result = await summarizer_agent.summarize_video(video)
                summaries[video.video_id] = summary_result.summary
                logger.debug(f"Summarized video {video.video_id}")
                
            except Exception as e:
                error_msg = f"Failed to summarize video {video.video_id}: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)
                summaries[video.video_id] = None
        
        return {
            "success": len(errors) == 0,
            "summaries": summaries,
            "errors": errors
        }
    
    async def _send_notifications(
        self,
        videos: List[VideoMetadata],
        summaries: Dict[str, Optional[str]],
        channel_config: ChannelConfig
    ) -> Dict[str, Any]:
        """Step 3: Send Telegram notifications."""
        logger.info(f"Step 3: Sending notifications for {len(videos)} videos")
        
        notifications_sent = 0
        errors = []
        
        # Rate limiting between notifications
        for i, video in enumerate(videos):
            try:
                summary = summaries.get(video.video_id)
                
                notification_result = await telegram_agent.send_video_notification(
                    video=video,
                    summary=summary,
                    chat_id=channel_config.telegram_chat_id
                )
                
                if notification_result.success:
                    notifications_sent += 1
                    logger.debug(f"Sent notification for video {video.video_id}")
                else:
                    error_msg = f"Notification failed for video {video.video_id}: {notification_result.error_message}"
                    logger.warning(error_msg)
                    errors.append(error_msg)
                
                # Rate limiting delay (except for last notification)
                if i < len(videos) - 1:
                    await asyncio.sleep(2.0)  # 2 second delay between notifications
                    
            except Exception as e:
                error_msg = f"Unexpected error sending notification for {video.video_id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        return {
            "success": len(errors) == 0,
            "notifications_sent": notifications_sent,
            "errors": errors
        }
    
    async def _update_database_state(
        self,
        videos: List[VideoMetadata],
        channel_config: ChannelConfig,
        summaries: Dict[str, Optional[str]] = None,
        notifications_sent: int = 0
    ) -> Dict[str, Any]:
        """Step 4: Update database with processing state."""
        logger.info(f"Step 4: Updating database state for {len(videos)} videos")
        
        try:
            # Save each video to database  
            for i, video in enumerate(videos):
                try:
                    summary = summaries.get(video.video_id) if summaries else None
                    # Each video gets individual notification status - assuming notifications were sent in order
                    notification_sent = i < notifications_sent
                    
                    await youtube_tracker_agent._save_video_to_database(
                        video=video,
                        summary=summary,
                        notification_sent=notification_sent
                    )
                    logger.debug(f"Saved video {video.video_id} to database")
                    
                except Exception as e:
                    logger.error(f"Failed to save video {video.video_id}: {e}")
            
            # Update channel state
            await youtube_tracker_agent._update_channel_state(channel_config, videos)
            
            return {"success": True}
            
        except Exception as e:
            error_msg = f"Failed to update database state: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "errors": [error_msg]
            }
    
    async def execute_batch_workflow(
        self,
        channel_configs: List[ChannelConfig],
        force_check: bool = False,
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Execute tracking workflow for multiple channels concurrently.
        
        Args:
            channel_configs: List of channel configurations
            force_check: Force check for all channels
            max_concurrent: Maximum concurrent executions
            
        Returns:
            List of workflow results
        """
        logger.info(f"Starting batch workflow for {len(channel_configs)} channels")
        
        # Create semaphore to limit concurrent executions
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def _execute_with_semaphore(config):
            async with semaphore:
                return await self.execute_tracking_workflow(config, force_check)
        
        # Execute all workflows concurrently
        tasks = [
            _execute_with_semaphore(config)
            for config in channel_configs
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_result = {
                    "channel_id": channel_configs[i].channel_id,
                    "channel_name": channel_configs[i].channel_name,
                    "success": False,
                    "errors": [str(result)],
                    "execution_time_seconds": 0
                }
                processed_results.append(error_result)
            else:
                processed_results.append(result)
        
        successful = sum(1 for r in processed_results if r["success"])
        logger.info(f"Batch workflow complete: {successful}/{len(channel_configs)} successful")
        
        return processed_results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get chain execution statistics."""
        return {
            "total_executions": self.executions,
            "successful_executions": self.successful_executions,
            "success_rate": (
                self.successful_executions / self.executions
                if self.executions > 0
                else 0.0
            )
        }


# Global chain instance
tracking_chain = TrackingChain()


# Convenience functions for LangChain integration
async def execute_channel_tracking(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tracking workflow for a single channel (LangChain compatible)."""
    channel_config = inputs["channel_config"]
    force_check = inputs.get("force_check", False)
    
    return await tracking_chain.execute_tracking_workflow(channel_config, force_check)


async def execute_batch_tracking(inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Execute tracking workflow for multiple channels (LangChain compatible)."""
    channel_configs = inputs["channel_configs"]
    force_check = inputs.get("force_check", False)
    max_concurrent = inputs.get("max_concurrent", 3)
    
    return await tracking_chain.execute_batch_workflow(
        channel_configs, force_check, max_concurrent
    )


def create_tracking_chain() -> RunnableSequence:
    """
    Create a LangChain compatible tracking chain.
    
    Returns:
        RunnableSequence for tracking workflow
    """
    return (
        RunnablePassthrough()
        | RunnableLambda(execute_channel_tracking)
    )


def create_batch_tracking_chain() -> RunnableSequence:
    """
    Create a LangChain compatible batch tracking chain.
    
    Returns:
        RunnableSequence for batch tracking workflow
    """
    return (
        RunnablePassthrough()
        | RunnableLambda(execute_batch_tracking)
    )