"""
Master orchestrator agent coordinating all YouTube tracking workflows.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict, deque

from langchain_core.tools import tool

from config.settings import get_settings
from models.channel import ChannelConfig, ChannelStatus
from storage.database import get_session, DatabaseUtils, Channel
from storage.process_state import process_state_manager
from schedulers.channel_scheduler import channel_scheduler
from chains.tracking_chain import tracking_chain
from agents.telegram_agent import telegram_agent
from utils import safe_log_text

# Setup logging
logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker for failing channels."""
    
    def __init__(self, failure_threshold: int = 5, timeout_minutes: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timedelta(minutes=timeout_minutes)
        self.failure_counts = defaultdict(int)
        self.last_failure_times = {}
        self.open_circuits = set()
    
    def record_failure(self, channel_id: str) -> None:
        """Record a failure for a channel."""
        self.failure_counts[channel_id] += 1
        self.last_failure_times[channel_id] = datetime.utcnow()
        
        if self.failure_counts[channel_id] >= self.failure_threshold:
            self.open_circuits.add(channel_id)
            logger.warning(f"Circuit breaker opened for channel {channel_id}")
    
    def record_success(self, channel_id: str) -> None:
        """Record a success for a channel."""
        if channel_id in self.failure_counts:
            self.failure_counts[channel_id] = 0
        if channel_id in self.open_circuits:
            self.open_circuits.remove(channel_id)
            logger.info(f"Circuit breaker closed for channel {channel_id}")
    
    def is_circuit_open(self, channel_id: str) -> bool:
        """Check if circuit is open for a channel."""
        if channel_id not in self.open_circuits:
            return False
        
        # Check if timeout has passed
        last_failure = self.last_failure_times.get(channel_id)
        if last_failure and datetime.utcnow() - last_failure > self.timeout:
            # Try to close the circuit
            self.open_circuits.remove(channel_id)
            self.failure_counts[channel_id] = 0
            logger.info(f"Circuit breaker timeout expired for channel {channel_id}, allowing retry")
            return False
        
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "open_circuits": len(self.open_circuits),
            "channels_with_failures": len(self.failure_counts),
            "total_failures": sum(self.failure_counts.values())
        }


class OrchestratorAgent:
    """Master orchestrator coordinating all YouTube tracking operations."""
    
    def __init__(self):
        self.settings = get_settings()
        self.circuit_breaker = CircuitBreaker()
        self.is_running = False
        self.active_operations = set()
        self.operation_history = deque(maxlen=100)  # Keep last 100 operations
        self.stats = {
            "total_operations": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "channels_managed": 0
        }
    
    async def start(self) -> None:
        """Start the orchestrator and scheduler."""
        if self.is_running:
            logger.warning("Orchestrator already running")
            return
        
        logger.info("Starting YouTube Tracker Orchestrator")
        
        try:
            # Initialize database
            from storage.database import init_database
            await init_database()
            logger.info("Database initialized")
            
            # Start scheduler
            await channel_scheduler.start()
            logger.info("Scheduler started")
            
            self.is_running = True
            logger.info("Orchestrator started successfully")
            
            # Write process state
            self._update_process_state()
            
        except Exception as e:
            logger.error(f"Failed to start orchestrator: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the orchestrator and scheduler."""
        if not self.is_running:
            logger.warning("Orchestrator not running")
            return
        
        logger.info("Stopping YouTube Tracker Orchestrator")
        
        try:
            # Stop scheduler
            await channel_scheduler.stop()
            logger.info("Scheduler stopped")
            
            # Wait for active operations to complete
            if self.active_operations:
                logger.info(f"Waiting for {len(self.active_operations)} active operations to complete")
                await asyncio.sleep(5)  # Give some time for operations to finish
            
            self.is_running = False
            logger.info("Orchestrator stopped successfully")
            
            # Clean up process state
            self._cleanup_process_state()
            
        except Exception as e:
            logger.error(f"Error stopping orchestrator: {e}")
    
    async def add_channel(
        self,
        channel_id: str,
        channel_name: str,
        telegram_chat_id: str,
        check_interval: int = 3600,
        start_monitoring: bool = True
    ) -> Dict[str, Any]:
        """
        Add a new channel to monitoring.
        
        Args:
            channel_id: YouTube channel ID
            channel_name: Human-readable channel name
            telegram_chat_id: Telegram chat ID for notifications
            check_interval: Check interval in seconds
            start_monitoring: Whether to start monitoring immediately
            
        Returns:
            Operation result dictionary
        """
        operation_id = f"add_channel_{channel_id}_{datetime.utcnow().timestamp()}"
        self.active_operations.add(operation_id)
        
        try:
            logger.info(f"Adding channel {safe_log_text(channel_name)} ({channel_id})")
            
            # Validate channel exists on YouTube
            from tools.youtube_tools import validate_channel_id
            is_valid = await validate_channel_id.ainvoke({"channel_id": channel_id})
            if not is_valid:
                return {
                    "success": False,
                    "error": f"YouTube channel {channel_id} not found or inaccessible"
                }
            
            # Validate Telegram chat
            from tools.telegram_tools import validate_telegram_chat
            is_telegram_valid = await validate_telegram_chat.ainvoke({"chat_id": telegram_chat_id})
            if not is_telegram_valid:
                return {
                    "success": False,
                    "error": f"Telegram chat {telegram_chat_id} not accessible"
                }
            
            # Create channel configuration
            channel_config = ChannelConfig(
                channel_id=channel_id,
                channel_name=channel_name,
                telegram_chat_id=telegram_chat_id,
                check_interval=check_interval,
                is_active=True
            )
            
            # Save to database
            async for session in get_session():
                existing_channel = await DatabaseUtils.get_channel_by_id(session, channel_id)
                
                if existing_channel:
                    # Update existing channel
                    existing_channel.channel_name = channel_name
                    existing_channel.telegram_chat_id = telegram_chat_id
                    existing_channel.check_interval = check_interval
                    existing_channel.is_active = True
                    logger.info(f"Updated existing channel {channel_id}")
                else:
                    # Create new channel
                    new_channel = Channel(
                        channel_id=channel_id,
                        channel_name=channel_name,
                        telegram_chat_id=telegram_chat_id,
                        check_interval=check_interval,
                        is_active=True
                    )
                    session.add(new_channel)
                    self.stats["channels_managed"] += 1
                    logger.info(f"Added new channel {channel_id}")
                
                await session.commit()
                break
            
            # Add to scheduler if monitoring should start
            if start_monitoring and self.is_running:
                job_id = await channel_scheduler.schedule_channel(
                    channel_config=channel_config,
                    start_immediately=False
                )
                logger.info(f"Scheduled channel {safe_log_text(channel_name)} with job ID: {job_id}")
            
            self.stats["total_operations"] += 1
            self.stats["successful_operations"] += 1
            
            # Record operation
            self.operation_history.append({
                "operation": "add_channel",
                "channel_id": channel_id,
                "timestamp": datetime.utcnow(),
                "success": True
            })
            
            return {
                "success": True,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "scheduled": start_monitoring and self.is_running
            }
            
        except Exception as e:
            error_msg = f"Failed to add channel {channel_id}: {str(e)}"
            logger.error(error_msg)
            
            self.stats["total_operations"] += 1
            self.stats["failed_operations"] += 1
            
            return {
                "success": False,
                "error": error_msg
            }
        finally:
            self.active_operations.discard(operation_id)
    
    async def remove_channel(self, channel_id: str) -> Dict[str, Any]:
        """
        Remove a channel from monitoring.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            Operation result dictionary
        """
        operation_id = f"remove_channel_{channel_id}_{datetime.utcnow().timestamp()}"
        self.active_operations.add(operation_id)
        
        try:
            logger.info(f"Removing channel {channel_id}")
            
            # Remove from scheduler
            if self.is_running:
                removed = await channel_scheduler.unschedule_channel(channel_id)
                if removed:
                    logger.info(f"Unscheduled channel {channel_id}")
            
            # Update database (mark as inactive instead of deleting)
            async for session in get_session():
                channel = await DatabaseUtils.get_channel_by_id(session, channel_id)
                
                if channel:
                    channel.is_active = False
                    await session.commit()
                    logger.info(f"Marked channel {channel_id} as inactive")
                    
                    self.stats["total_operations"] += 1
                    self.stats["successful_operations"] += 1
                    
                    return {
                        "success": True,
                        "channel_id": channel_id,
                        "message": "Channel removed from monitoring"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Channel {channel_id} not found"
                    }
                break
            
        except Exception as e:
            error_msg = f"Failed to remove channel {channel_id}: {str(e)}"
            logger.error(error_msg)
            
            self.stats["total_operations"] += 1
            self.stats["failed_operations"] += 1
            
            return {
                "success": False,
                "error": error_msg
            }
        finally:
            self.active_operations.discard(operation_id)
    
    async def trigger_manual_check(
        self,
        channel_id: str,
        force_check: bool = True
    ) -> Dict[str, Any]:
        """
        Trigger manual check for a specific channel.
        
        Args:
            channel_id: YouTube channel ID
            force_check: Force check even if within interval
            
        Returns:
            Operation result dictionary
        """
        operation_id = f"manual_check_{channel_id}_{datetime.utcnow().timestamp()}"
        self.active_operations.add(operation_id)
        
        try:
            # Check circuit breaker
            if self.circuit_breaker.is_circuit_open(channel_id):
                return {
                    "success": False,
                    "error": f"Channel {channel_id} is temporarily disabled due to repeated failures"
                }
            
            logger.info(f"Triggering manual check for channel {channel_id}")
            
            # Get channel configuration
            async for session in get_session():
                channel = await DatabaseUtils.get_channel_by_id(session, channel_id)
                
                if not channel:
                    return {
                        "success": False,
                        "error": f"Channel {channel_id} not found"
                    }
                
                channel_config = ChannelConfig(
                    channel_id=channel.channel_id,
                    channel_name=channel.channel_name,
                    telegram_chat_id=channel.telegram_chat_id,
                    check_interval=channel.check_interval,
                    last_check=channel.last_check,
                    last_video_id=channel.last_video_id,
                    is_active=channel.is_active
                )
                break
            
            # Execute tracking workflow
            result = await tracking_chain.execute_tracking_workflow(
                channel_config=channel_config,
                force_check=force_check
            )
            
            # Update circuit breaker
            if result["success"] and not result.get("errors"):
                self.circuit_breaker.record_success(channel_id)
            elif result.get("errors"):
                self.circuit_breaker.record_failure(channel_id)
            
            self.stats["total_operations"] += 1
            if result["success"]:
                self.stats["successful_operations"] += 1
            else:
                self.stats["failed_operations"] += 1
            
            # Record operation
            self.operation_history.append({
                "operation": "manual_check",
                "channel_id": channel_id,
                "timestamp": datetime.utcnow(),
                "success": result["success"],
                "videos_processed": result.get("videos_processed", 0)
            })
            
            return result
            
        except Exception as e:
            error_msg = f"Manual check failed for channel {channel_id}: {str(e)}"
            logger.error(error_msg)
            
            self.circuit_breaker.record_failure(channel_id)
            self.stats["total_operations"] += 1
            self.stats["failed_operations"] += 1
            
            return {
                "success": False,
                "error": error_msg
            }
        finally:
            self.active_operations.discard(operation_id)
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        try:
            # First try to read from process state (for inter-process status check)
            process_state = process_state_manager.read_state()
            if process_state and not self.is_running:
                # Another process is running, return its state
                async for session in get_session():
                    active_channels = await DatabaseUtils.get_active_channels(session)
                    
                    return {
                        "orchestrator": {
                            "is_running": process_state.get("is_running", False),
                            "active_operations": process_state.get("active_operations", 0),
                            "stats": {"total_operations": 0, "successful_operations": 0, "failed_operations": 0}
                        },
                        "scheduler": {
                            "is_running": process_state.get("scheduler_running", False),
                            "scheduled_jobs": 0,
                            "jobs_executed": 0,
                            "jobs_failed": 0
                        },
                        "circuit_breaker": process_state.get("circuit_breaker_stats", {"open_circuits": 0, "total_failures": 0}),
                        "channels": {
                            "total_active": len(active_channels),
                            "channels": [
                                {
                                    "channel_id": ch.channel_id,
                                    "channel_name": ch.channel_name,
                                    "last_check": ch.last_check,
                                }
                                for ch in active_channels
                            ]
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    }
            # Get active channels
            async for session in get_session():
                active_channels = await DatabaseUtils.get_active_channels(session)
                
                # Get scheduler status
                scheduler_stats = channel_scheduler.get_stats()
                
                # Get circuit breaker stats
                circuit_stats = self.circuit_breaker.get_stats()
                
                # Get recent operations
                recent_operations = list(self.operation_history)[-10:]  # Last 10 operations
                
                return {
                    "orchestrator": {
                        "is_running": self.is_running,
                        "active_operations": len(self.active_operations),
                        "stats": self.stats
                    },
                    "scheduler": scheduler_stats,
                    "circuit_breaker": circuit_stats,
                    "channels": {
                        "total_active": len(active_channels),
                        "channels": [
                            {
                                "channel_id": ch.channel_id,
                                "channel_name": ch.channel_name,
                                "last_check": ch.last_check,
                                "is_scheduled": channel_scheduler.get_job_by_channel(ch.channel_id) is not None
                            }
                            for ch in active_channels
                        ]
                    },
                    "recent_operations": recent_operations,
                    "timestamp": datetime.utcnow()
                }
                break
                
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow()
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform system health check."""
        health_status = {
            "healthy": True,
            "issues": [],
            "timestamp": datetime.utcnow()
        }
        
        try:
            # Check if orchestrator is running
            if not self.is_running:
                health_status["healthy"] = False
                health_status["issues"].append("Orchestrator not running")
            
            # Check scheduler
            if not channel_scheduler.is_running:
                health_status["healthy"] = False
                health_status["issues"].append("Scheduler not running")
            
            # Check database connectivity
            try:
                async for session in get_session():
                    await DatabaseUtils.get_active_channels(session)
                    break
            except Exception as e:
                health_status["healthy"] = False
                health_status["issues"].append(f"Database connectivity issue: {str(e)}")
            
            # Check for too many failed operations
            if self.stats["total_operations"] > 0:
                failure_rate = self.stats["failed_operations"] / self.stats["total_operations"]
                if failure_rate > 0.5:  # More than 50% failure rate
                    health_status["healthy"] = False
                    health_status["issues"].append(f"High failure rate: {failure_rate:.2%}")
            
            # Check circuit breaker
            circuit_stats = self.circuit_breaker.get_stats()
            if circuit_stats["open_circuits"] > 0:
                health_status["issues"].append(f"{circuit_stats['open_circuits']} channels disabled by circuit breaker")
            
            return health_status
            
        except Exception as e:
            return {
                "healthy": False,
                "issues": [f"Health check error: {str(e)}"],
                "timestamp": datetime.utcnow()
            }
    
    def _update_process_state(self) -> None:
        """Update process state for inter-process communication."""
        try:
            state = {
                "is_running": self.is_running,
                "scheduler_running": getattr(channel_scheduler, 'is_running', False),
                "active_operations": len(self.active_operations),
                "circuit_breaker_stats": self.circuit_breaker.get_stats()
            }
            process_state_manager.write_state(state)
            logger.info(f"Process state updated: {state}")
        except Exception as e:
            logger.warning(f"Failed to update process state: {e}")
    
    def _cleanup_process_state(self) -> None:
        """Clean up process state files."""
        try:
            process_state_manager.cleanup_state()
        except Exception as e:
            logger.warning(f"Failed to cleanup process state: {e}")


# Global orchestrator instance
orchestrator_agent = OrchestratorAgent()


# LangChain tools
@tool
async def start_orchestrator() -> Dict[str, Any]:
    """
    Start the YouTube tracker orchestrator.
    
    Returns:
        Operation result dictionary
    """
    try:
        await orchestrator_agent.start()
        return {"success": True, "message": "Orchestrator started successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
async def stop_orchestrator() -> Dict[str, Any]:
    """
    Stop the YouTube tracker orchestrator.
    
    Returns:
        Operation result dictionary
    """
    try:
        await orchestrator_agent.stop()
        return {"success": True, "message": "Orchestrator stopped successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
async def add_channel_to_monitoring(
    channel_id: str,
    channel_name: str,
    telegram_chat_id: str,
    check_interval: int = 3600
) -> Dict[str, Any]:
    """
    Add a channel to YouTube monitoring.
    
    Args:
        channel_id: YouTube channel ID
        channel_name: Human-readable channel name
        telegram_chat_id: Telegram chat ID for notifications
        check_interval: Check interval in seconds
        
    Returns:
        Operation result dictionary
    """
    return await orchestrator_agent.add_channel(
        channel_id, channel_name, telegram_chat_id, check_interval
    )


@tool
async def remove_channel_from_monitoring(channel_id: str) -> Dict[str, Any]:
    """
    Remove a channel from YouTube monitoring.
    
    Args:
        channel_id: YouTube channel ID
        
    Returns:
        Operation result dictionary
    """
    return await orchestrator_agent.remove_channel(channel_id)


@tool
async def check_channel_now(channel_id: str) -> Dict[str, Any]:
    """
    Trigger immediate check for a channel.
    
    Args:
        channel_id: YouTube channel ID
        
    Returns:
        Operation result dictionary
    """
    return await orchestrator_agent.trigger_manual_check(channel_id)


@tool
async def get_system_status() -> Dict[str, Any]:
    """
    Get comprehensive system status.
    
    Returns:
        System status dictionary
    """
    return await orchestrator_agent.get_system_status()


@tool
async def perform_health_check() -> Dict[str, Any]:
    """
    Perform system health check.
    
    Returns:
        Health status dictionary
    """
    return await orchestrator_agent.health_check()