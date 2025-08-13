"""
APScheduler-based channel monitoring with SQLAlchemy persistence.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.job import Job

from config.settings import get_settings
from models.channel import ChannelConfig
from storage.database import get_session, DatabaseUtils
from chains.tracking_chain import tracking_chain

# Setup logging
logger = logging.getLogger(__name__)


class ChannelScheduler:
    """Scheduler for managing periodic YouTube channel monitoring."""
    
    def __init__(self):
        self.settings = get_settings()
        self.scheduler = None
        self.is_running = False
        self.jobs_executed = 0
        self.jobs_failed = 0
        
    async def initialize(self) -> None:
        """Initialize the scheduler with job store and executors."""
        if self.scheduler:
            logger.warning("Scheduler already initialized")
            return
        
        # Configure job stores
        jobstores = {
            'default': SQLAlchemyJobStore(url=self.settings.scheduler_jobstore_url)
        }
        
        # Configure executors
        executors = {
            'default': AsyncIOExecutor()
        }
        
        # Job defaults
        job_defaults = {
            'coalesce': True,  # Combine multiple pending executions into one
            'max_instances': 1,  # Only one instance of each job can run at a time
            'replace_existing': True  # Replace existing job if scheduling again
        }
        
        # Create scheduler
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        # Add event listeners
        self.scheduler.add_listener(self._job_executed_listener, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error_listener, EVENT_JOB_ERROR)
        self.scheduler.add_listener(self._job_missed_listener, EVENT_JOB_MISSED)
        
        logger.info("Scheduler initialized with SQLAlchemy job store")
    
    async def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler:
            await self.initialize()
        
        if self.is_running:
            logger.warning("Scheduler already running")
            return
        
        self.scheduler.start()
        self.is_running = True
        logger.info("Scheduler started")
        
        # Load existing channels from database and schedule them
        await self._load_and_schedule_channels()
        
        # Schedule retry queue processing
        await self._schedule_retry_processing()
    
    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self.is_running:
            logger.warning("Scheduler not running")
            return
        
        if self.scheduler:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("Scheduler stopped")
    
    async def schedule_channel(
        self,
        channel_config: ChannelConfig,
        start_immediately: bool = False
    ) -> str:
        """
        Schedule a channel for periodic monitoring.
        
        Args:
            channel_config: Channel configuration
            start_immediately: Whether to start monitoring immediately
            
        Returns:
            Job ID for the scheduled channel
        """
        if not self.scheduler:
            await self.initialize()
        
        job_id = f"channel_{channel_config.channel_id}"
        
        # Calculate next run time
        if start_immediately:
            next_run_time = datetime.utcnow() + timedelta(seconds=10)  # Small delay
        else:
            next_run_time = datetime.utcnow() + timedelta(seconds=channel_config.check_interval)
        
        # Schedule the job - only pass serializable data
        job = self.scheduler.add_job(
            func=execute_scheduled_tracking,
            trigger='interval',
            seconds=channel_config.check_interval,
            args=[channel_config.channel_id],  # Only pass channel_id string
            id=job_id,
            name=f"Track {channel_config.channel_name}",
            next_run_time=next_run_time,
            replace_existing=True
        )
        
        logger.info(
            f"Scheduled channel {channel_config.channel_name} "
            f"(interval: {channel_config.check_interval}s, next run: {next_run_time})"
        )
        
        return job_id
    
    async def unschedule_channel(self, channel_id: str) -> bool:
        """
        Unschedule a channel from monitoring.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            True if job was removed, False if not found
        """
        if not self.scheduler:
            logger.warning("Scheduler not initialized")
            return False
        
        job_id = f"channel_{channel_id}"
        
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Unscheduled channel {channel_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to unschedule channel {channel_id}: {e}")
            return False
    
    async def reschedule_channel(
        self,
        channel_config: ChannelConfig
    ) -> str:
        """
        Reschedule a channel with updated configuration.
        
        Args:
            channel_config: Updated channel configuration
            
        Returns:
            Job ID for the rescheduled channel
        """
        # Remove existing job if it exists
        await self.unschedule_channel(channel_config.channel_id)
        
        # Schedule with new configuration
        return await self.schedule_channel(channel_config)
    
    
    async def _load_and_schedule_channels(self) -> None:
        """Load active channels from database and schedule them."""
        try:
            async for session in get_session():
                active_channels = await DatabaseUtils.get_active_channels(session)
                
                logger.info(f"Loading {len(active_channels)} active channels from database")
                
                for channel in active_channels:
                    try:
                        channel_config = ChannelConfig(
                            channel_id=channel.channel_id,
                            channel_name=channel.channel_name,
                            check_interval=channel.check_interval,
                            telegram_chat_id=channel.telegram_chat_id,
                            last_check=channel.last_check,
                            last_video_id=channel.last_video_id,
                            is_active=channel.is_active
                        )
                        
                        await self.schedule_channel(channel_config, start_immediately=False)
                        
                    except Exception as e:
                        logger.error(f"Failed to schedule channel {channel.channel_id}: {e}")
                
                break
                
        except Exception as e:
            logger.error(f"Failed to load channels from database: {e}")
    
    async def _schedule_retry_processing(self) -> None:
        """Schedule Telegram retry queue processing."""
        try:
            # Schedule retry processing every 5 minutes
            job = self.scheduler.add_job(
                func=self._process_telegram_retries,
                trigger='interval',
                minutes=5,
                id='telegram_retry_processor',
                name='Telegram Retry Queue Processor',
                max_instances=1,
                coalesce=True,
                misfire_grace_time=60
            )
            
            logger.info("Scheduled Telegram retry queue processing (every 5 minutes)")
            
        except Exception as e:
            logger.error(f"Failed to schedule retry processing: {e}")
    
    async def _process_telegram_retries(self) -> None:
        """Process Telegram retry queue."""
        try:
            from tools.telegram_tools import process_retry_queue
            
            logger.debug("Processing Telegram retry queue")
            result = await process_retry_queue.ainvoke({})
            
            if result["processed"] > 0:
                logger.info(f"Retry queue processing: {result['message']}")
            
        except Exception as e:
            logger.error(f"Error in retry queue processing: {e}")
    
    def _job_executed_listener(self, event) -> None:
        """Handle job execution events."""
        self.jobs_executed += 1
        logger.debug(f"Job executed: {event.job_id}")
    
    def _job_error_listener(self, event) -> None:
        """Handle job error events."""
        self.jobs_failed += 1
        logger.error(f"Job failed: {event.job_id} - {event.exception}")
    
    def _job_missed_listener(self, event) -> None:
        """Handle missed job events."""
        logger.warning(f"Job missed: {event.job_id}")
    
    def get_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """
        Get information about all scheduled jobs.
        
        Returns:
            List of job information dictionaries
        """
        if not self.scheduler:
            return []
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger),
                "args": [str(arg) for arg in job.args] if job.args else []
            })
        
        return jobs
    
    def get_job_by_channel(self, channel_id: str) -> Optional[Job]:
        """
        Get job information for a specific channel.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            Job object or None if not found
        """
        if not self.scheduler:
            return None
        
        job_id = f"channel_{channel_id}"
        return self.scheduler.get_job(job_id)
    
    async def trigger_channel_now(self, channel_id: str) -> bool:
        """
        Trigger immediate execution of a channel's tracking job.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            True if job was triggered, False if not found
        """
        if not self.scheduler:
            logger.warning("Scheduler not initialized")
            return False
        
        job_id = f"channel_{channel_id}"
        
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                # Modify job to run immediately
                job.modify(next_run_time=datetime.utcnow())
                logger.info(f"Triggered immediate execution for channel {channel_id}")
                return True
            else:
                logger.warning(f"Job not found for channel {channel_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to trigger job for channel {channel_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        scheduled_jobs = len(self.get_scheduled_jobs()) if self.scheduler else 0
        
        return {
            "is_running": self.is_running,
            "scheduled_jobs": scheduled_jobs,
            "jobs_executed": self.jobs_executed,
            "jobs_failed": self.jobs_failed,
            "success_rate": (
                (self.jobs_executed - self.jobs_failed) / self.jobs_executed
                if self.jobs_executed > 0
                else 0.0
            )
        }


# Global scheduler instance
channel_scheduler = ChannelScheduler()


# Standalone function for scheduled jobs (avoids serialization issues)
async def execute_scheduled_tracking(channel_id: str) -> None:
    """
    Standalone function to execute tracking workflow for scheduled jobs.
    This avoids APScheduler serialization issues with instance methods.
    """
    from chains.tracking_chain import tracking_chain
    from models.channel import ChannelConfig
    from storage.database import get_session, DatabaseUtils
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Executing scheduled tracking for channel {channel_id}")
    
    try:
        # Get channel configuration from database
        async for session in get_session():
            channel = await DatabaseUtils.get_channel_by_id(session, channel_id)
            if not channel:
                logger.error(f"Channel {channel_id} not found in database")
                return
            
            # Check if channel is active before proceeding
            if not channel.is_active:
                logger.info(f"Skipping tracking for inactive channel {channel_id}")
                return
            
            # Convert to ChannelConfig
            channel_config = ChannelConfig(
                channel_id=channel.channel_id,
                channel_name=channel.channel_name,
                telegram_chat_id=channel.telegram_chat_id,
                check_interval=channel.check_interval,
                last_check=channel.last_check,
                last_video_id=channel.last_video_id,
                is_active=channel.is_active
            )
            
            # Execute the tracking workflow
            result = await tracking_chain.execute_tracking_workflow(
                channel_config=channel_config,
                force_check=False
            )
            
            if result["success"]:
                logger.info(f"Scheduled tracking completed for {channel_id}: {result['videos_processed']} videos processed")
            else:
                logger.warning(f"Scheduled tracking completed with errors for {channel_id}: {result.get('errors', [])}")
            
            break
            
    except Exception as e:
        logger.error(f"Error in scheduled tracking for {channel_id}: {e}")


# Convenience functions
async def start_scheduler() -> None:
    """Start the global channel scheduler."""
    await channel_scheduler.start()


async def stop_scheduler() -> None:
    """Stop the global channel scheduler."""
    await channel_scheduler.stop()


async def add_channel_to_scheduler(
    channel_config: ChannelConfig,
    start_immediately: bool = False
) -> str:
    """Add a channel to the scheduler."""
    return await channel_scheduler.schedule_channel(channel_config, start_immediately)


async def remove_channel_from_scheduler(channel_id: str) -> bool:
    """Remove a channel from the scheduler."""
    return await channel_scheduler.unschedule_channel(channel_id)


async def trigger_channel_check(channel_id: str) -> bool:
    """Trigger immediate check for a channel."""
    return await channel_scheduler.trigger_channel_now(channel_id)