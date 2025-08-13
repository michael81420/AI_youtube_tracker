"""
CLI interface for YouTube Tracker Agent System.
"""

import asyncio
import argparse
import sys
import json
import logging
from datetime import datetime
from typing import Optional

from agents.orchestrator import orchestrator_agent
from tools.youtube_tools import get_quota_usage
from tools.telegram_tools import get_telegram_stats, get_bot_info
from agents.summarizer_agent import get_summarizer_stats
from schedulers.channel_scheduler import channel_scheduler

# Setup logging
logger = logging.getLogger(__name__)


def print_success(message: str) -> None:
    """Print success message in green."""
    print(f"[SUCCESS] {message}")


def print_error(message: str) -> None:
    """Print error message in red."""
    print(f"[ERROR] {message}")


def print_info(message: str) -> None:
    """Print info message."""
    print(f"[INFO] {message}")


def print_warning(message: str) -> None:
    """Print warning message in yellow."""
    print(f"[WARNING] {message}")


async def start_command() -> None:
    """Start the YouTube tracker system and keep it running."""
    print_info("Starting YouTube Tracker system...")
    
    try:
        result = await orchestrator_agent.start()
        if orchestrator_agent.is_running:
            print_success("YouTube Tracker started successfully!")
            print_info("System is now monitoring configured channels")
            print_info("Press Ctrl+C to stop the system")
            
            # Keep the system running
            try:
                from storage.process_state import process_state_manager
                while True:
                    await asyncio.sleep(1)
                    # Check for stop signal from another process
                    if process_state_manager.check_stop_signal():
                        print_info("\nReceived stop signal from another process...")
                        process_state_manager.clear_stop_signal()
                        break
            except KeyboardInterrupt:
                print_info("\nShutting down YouTube Tracker...")
            
            # Stop the system
            await orchestrator_agent.stop()
            print_success("YouTube Tracker stopped successfully!")
        else:
            print_error("Failed to start YouTube Tracker")
    except Exception as e:
        print_error(f"Error starting system: {e}")


async def stop_command() -> None:
    """Stop the YouTube tracker system."""
    print_info("Stopping YouTube Tracker system...")
    
    try:
        from storage.process_state import process_state_manager
        
        # First try to send stop signal to running process
        if process_state_manager.send_stop_signal():
            print_info("Stop signal sent to running process")
            print_success("YouTube Tracker stop requested successfully!")
        else:
            # No running process found, try local stop
            await orchestrator_agent.stop()
            print_success("YouTube Tracker stopped successfully!")
    except Exception as e:
        print_error(f"Error stopping system: {e}")


async def add_channel_command(
    channel_id: str,
    telegram_chat_id: Optional[str] = None,
    check_interval: int = 3600
) -> None:
    """Add a channel to monitoring by channel ID only."""
    # Use default chat ID from settings if not provided
    if telegram_chat_id is None:
        from config.settings import get_settings
        settings = get_settings()
        telegram_chat_id = settings.telegram_chat_id
        print_info(f"Using default Telegram chat ID: {telegram_chat_id}")
    
    print_info(f"Fetching channel information for {channel_id}...")
    
    try:
        # Get channel information from YouTube API
        from tools.youtube_tools import YouTubeAPIClient
        youtube_client = YouTubeAPIClient()
        channel_info = await youtube_client.get_channel_info(channel_id)
        
        channel_name = channel_info["snippet"]["title"]
        print_info(f"Found channel: {channel_name}")
        
        result = await orchestrator_agent.add_channel(
            channel_id=channel_id,
            channel_name=channel_name,
            telegram_chat_id=telegram_chat_id,
            check_interval=check_interval,
            start_monitoring=True
        )
        
        if result["success"]:
            print_success(f"Channel '{channel_name}' added successfully!")
            if result.get("scheduled"):
                print_info(f"Channel scheduled for monitoring every {check_interval} seconds")
            else:
                print_warning("Channel added but not scheduled (system may not be running)")
        else:
            print_error(f"Failed to add channel: {result.get('error', 'Unknown error')}")
    
    except Exception as e:
        print_error(f"Error adding channel: {e}")


async def remove_channel_command() -> None:
    """Remove a channel from monitoring with interactive selection."""
    from storage.database import get_session, Channel, DatabaseUtils
    
    print_info("Fetching active channels...")
    
    try:
        # Get active channels from database
        async for session in get_session():
            channels = await DatabaseUtils.get_active_channels(session)
            break
        
        if not channels:
            print_warning("No active channels found in database. Nothing to remove.")
            return
        
        # Display available channels
        print_info(f"Found {len(channels)} active channel(s):")
        print("")
        
        for i, channel in enumerate(channels, 1):
            print(f"  {i}. {channel.channel_name} ({channel.channel_id})")
        
        print("")
        
        # Get user selection
        while True:
            try:
                choice = input("Select channel number to remove (or 'q' to quit): ").strip()
                
                if choice.lower() == 'q':
                    print_info("Operation cancelled.")
                    return
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(channels):
                    selected_channel = channels[choice_num - 1]
                    break
                else:
                    print_error(f"Please enter a number between 1 and {len(channels)}")
            except ValueError:
                print_error("Please enter a valid number or 'q' to quit")
        
        # Confirm removal
        print(f"\nSelected channel: {selected_channel.channel_name} ({selected_channel.channel_id})")
        confirm = input("Are you sure you want to remove this channel? (y/N): ").strip().lower()
        
        if confirm != 'y':
            print_info("Operation cancelled.")
            return
        
        # Remove the channel
        print_info(f"Removing channel {selected_channel.channel_name}...")
        
        result = await orchestrator_agent.remove_channel(selected_channel.channel_id)
        
        if result["success"]:
            print_success(f"Channel '{selected_channel.channel_name}' removed successfully!")
        else:
            print_error(f"Failed to remove channel: {result.get('error', 'Unknown error')}")
    
    except Exception as e:
        print_error(f"Error removing channel: {e}")


async def check_now_command(channel_id: str, force_check: bool = False) -> None:
    """Trigger immediate check for a channel."""
    if force_check:
        print_info(f"Triggering FORCED check for channel {channel_id} (may re-process old videos)...")
    else:
        print_info(f"Triggering immediate check for channel {channel_id}...")
    
    try:
        result = await orchestrator_agent.trigger_manual_check(channel_id, force_check=force_check)
        
        videos_processed = result.get("videos_processed", 0)
        notifications_sent = result.get("notifications_sent", 0)
        errors = result.get("errors", [])
        
        if result["success"]:
            if videos_processed > 0:
                print_success(f"Check completed! Processed {videos_processed} video(s), sent {notifications_sent} notification(s)")
            else:
                print_success("Check completed! No new videos found")
        elif videos_processed > 0:
            # Partial success - some work was done despite errors
            print_warning(f"Check completed with issues: Processed {videos_processed} video(s), sent {notifications_sent} notification(s)")
            if errors:
                print_info(f"Encountered {len(errors)} error(s) during processing")
        else:
            print_error(f"Check failed: {result.get('error', 'Unknown error')}")
            if errors:
                print_info(f"Errors: {'; '.join(errors[:3])}")  # Show first 3 errors
    
    except Exception as e:
        print_error(f"Error checking channel: {e}")


async def status_command() -> None:
    """Show system status."""
    print_info("Getting system status...")
    
    try:
        status = await orchestrator_agent.get_system_status()
        
        if "error" in status:
            print_error(f"Error getting status: {status['error']}")
            return
        
        # Orchestrator status
        orchestrator = status["orchestrator"]
        print(f"\nSystem Status")
        print(f"   Running: {'Yes' if orchestrator['is_running'] else 'No'}")
        print(f"   Active Operations: {orchestrator['active_operations']}")
        print(f"   Total Operations: {orchestrator['stats']['total_operations']}")
        print(f"   Success Rate: {orchestrator['stats']['successful_operations']}/{orchestrator['stats']['total_operations']}")
        
        # Scheduler status
        scheduler = status["scheduler"]
        print(f"\nScheduler Status")
        print(f"   Running: {'Yes' if scheduler['is_running'] else 'No'}")
        print(f"   Scheduled Jobs: {scheduler['scheduled_jobs']}")
        print(f"   Jobs Executed: {scheduler['jobs_executed']}")
        print(f"   Jobs Failed: {scheduler['jobs_failed']}")
        
        # Circuit breaker status
        circuit = status["circuit_breaker"]
        print(f"\nCircuit Breaker Status")
        print(f"   Open Circuits: {circuit['open_circuits']}")
        print(f"   Total Failures: {circuit['total_failures']}")
        
        # Channels
        channels = status["channels"]
        print(f"\nChannels ({channels['total_active']} active)")
        for channel in channels["channels"][:10]:  # Show first 10
            last_check = channel["last_check"]
            if last_check:
                if isinstance(last_check, str):
                    last_check_str = datetime.fromisoformat(last_check).strftime("%Y-%m-%d %H:%M UTC")
                else:
                    last_check_str = last_check.strftime("%Y-%m-%d %H:%M UTC")
            else:
                last_check_str = "Never"
            
            scheduled_icon = "[SCHEDULED]" if channel.get("is_scheduled", False) else "[NOT SCHEDULED]"
            print(f"   {scheduled_icon} {channel['channel_name'][:30]} (Last: {last_check_str})")
        
        if len(channels["channels"]) > 10:
            print(f"   ... and {len(channels['channels']) - 10} more channels")
    
    except Exception as e:
        print_error(f"Error getting status: {e}")


async def health_command() -> None:
    """Check system health."""
    print_info("Performing health check...")
    
    try:
        health = await orchestrator_agent.health_check()
        
        if health["healthy"]:
            print_success("System is healthy!")
        else:
            print_warning("System has issues:")
            for issue in health["issues"]:
                print(f"   [WARN] {issue}")
    
    except Exception as e:
        print_error(f"Error checking health: {e}")


async def stats_command() -> None:
    """Show detailed statistics."""
    print_info("Getting system statistics...")
    
    try:
        # YouTube API stats
        youtube_stats = get_quota_usage()
        print(f"\nYouTube API Stats")
        print(f"   Quota Used: {youtube_stats['quota_used_today']}/10,000")
        print(f"   Requests Made: {youtube_stats['requests_made']}")
        print(f"   Quota Remaining: {youtube_stats['quota_remaining']}")
        
        # Telegram stats
        telegram_stats = get_telegram_stats()
        print(f"\nTelegram Stats")
        print(f"   Requests Made: {telegram_stats['requests_made']}")
        print(f"   Rate Limit: {telegram_stats['rate_limit_per_minute']}/min")
        print(f"   Bot Configured: {'Yes' if telegram_stats['bot_token_configured'] else 'No'}")
        
        # Summarizer stats
        summarizer_stats = get_summarizer_stats()
        print(f"\nSummarizer Stats")
        print(f"   Provider: {summarizer_stats['provider']}")
        print(f"   Model: {summarizer_stats['model']}")
        print(f"   Requests Made: {summarizer_stats['requests_made']}")
        print(f"   Rate Limit: {summarizer_stats['rate_limit_per_minute']}/min")
        
        # Get orchestrator stats
        status = await orchestrator_agent.get_system_status()
        if "error" not in status:
            recent_ops = status.get("recent_operations", [])
            if recent_ops:
                print(f"\nRecent Operations ({len(recent_ops)})")
                for op in recent_ops[-5:]:  # Last 5 operations
                    timestamp = datetime.fromisoformat(op["timestamp"]).strftime("%H:%M:%S")
                    success_icon = "[OK]" if op["success"] else "[ERR]"
                    print(f"   {success_icon} {timestamp} - {op['operation']} ({op.get('channel_id', 'N/A')})")
    
    except Exception as e:
        print_error(f"Error getting statistics: {e}")


async def test_apis_command() -> None:
    """Test API connectivity."""
    print_info("Testing API connectivity...")
    
    # Test Telegram bot
    try:
        bot_info = await get_bot_info()
        print_success(f"[SUCCESS] Telegram Bot: {bot_info['first_name']} (@{bot_info['username']})")
    except Exception as e:
        print_error(f"[ERROR] Telegram Bot: {e}")
    
    # Test YouTube API (by checking quota)
    try:
        youtube_stats = get_quota_usage()
        print_success(f"[SUCCESS] YouTube API: {youtube_stats['quota_remaining']} quota remaining")
    except Exception as e:
        print_error(f"[ERROR] YouTube API: {e}")
    
    # Test database
    try:
        from storage.database import init_database
        await init_database()
        print_success("[SUCCESS] Database: Connection successful")
    except Exception as e:
        print_error(f"[ERROR] Database: {e}")


async def process_retries_command() -> None:
    """Process Telegram retry queue manually."""
    print_info("Processing Telegram retry queue...")
    
    try:
        from tools.telegram_tools import process_retry_queue
        
        result = await process_retry_queue.ainvoke({})
        
        if result["success"]:
            print_info(f"Processing completed: {result['message']}")
            
            if result["processed"] > 0:
                print_info(f"  - Processed: {result['processed']} notifications")
                print_info(f"  - Succeeded: {result['succeeded']}")
                print_info(f"  - Failed: {result['failed']}")
                
                if result.get("processed_ids"):
                    print_info(f"  - Video IDs: {', '.join(result['processed_ids'][:5])}{'...' if len(result['processed_ids']) > 5 else ''}")
            else:
                print_info("No notifications were ready for retry")
        else:
            print_error(f"Failed to process retry queue: {result.get('error', 'Unknown error')}")
    
    except Exception as e:
        print_error(f"Error processing retry queue: {e}")


async def cleanup_retry_queue_command() -> None:
    """Clean up retry queue by removing duplicates and expired items."""
    print_info("Cleaning up Telegram retry queue...")
    
    try:
        from tools.telegram_tools import RetryQueueManager
        
        result = await RetryQueueManager.cleanup_retry_queue()
        
        if result["success"]:
            print_info(f"Cleanup completed: {result['message']}")
            print_info(f"  - Original count: {result['original_count']}")
            print_info(f"  - Final count: {result['final_count']}")
            print_info(f"  - Items cleaned: {result['cleaned']}")
        else:
            print_error(f"Failed to clean retry queue: {result.get('error', 'Unknown error')}")
    
    except Exception as e:
        print_error(f"Error cleaning retry queue: {e}")


async def clear_videos_command(
    channel_id: Optional[str] = None,
    confirm: bool = False,
    keep_notifications: bool = False
) -> None:
    """Clear processed videos from database."""
    from storage.database import get_session, Video, Notification, DatabaseUtils
    from sqlalchemy import select, delete, func
    
    try:
        # Get count of videos to be deleted
        async for session in get_session():
            if channel_id:
                count_query = select(func.count(Video.id)).where(Video.channel_id == channel_id)
                channel_name_result = await DatabaseUtils.get_channel_by_id(session, channel_id)
                if not channel_name_result:
                    print_error(f"Channel {channel_id} not found")
                    return
                scope_desc = f"for channel '{channel_name_result.channel_name}'"
            else:
                count_query = select(func.count(Video.id))
                scope_desc = "for all channels"
            
            result = await session.execute(count_query)
            video_count = result.scalar()
            
            if video_count == 0:
                print_info(f"No videos found {scope_desc}")
                return
            
            # Show what will be deleted
            print_warning(f"This will delete {video_count} video record(s) {scope_desc}")
            if not keep_notifications:
                # Count notifications that will be deleted
                if channel_id:
                    notif_query = select(func.count(Notification.id)).where(Notification.channel_id == channel_id)
                else:
                    notif_query = select(func.count(Notification.id))
                notif_result = await session.execute(notif_query)
                notif_count = notif_result.scalar()
                if notif_count > 0:
                    print_warning(f"This will also delete {notif_count} notification record(s)")
            else:
                print_info("Notification records will be preserved")
            
            # Confirmation prompt
            if not confirm:
                print("")
                response = input("Are you sure you want to proceed? [y/N]: ").strip().lower()
                if response not in ['y', 'yes']:
                    print_info("Operation cancelled")
                    return
            
            print_info("Clearing videos from database...")
            
            # Delete notifications first (if not keeping them)
            notifications_deleted = 0
            if not keep_notifications:
                if channel_id:
                    notif_delete = delete(Notification).where(Notification.channel_id == channel_id)
                else:
                    notif_delete = delete(Notification)
                notif_result = await session.execute(notif_delete)
                notifications_deleted = notif_result.rowcount
            
            # Delete videos
            if channel_id:
                video_delete = delete(Video).where(Video.channel_id == channel_id)
            else:
                video_delete = delete(Video)
            
            video_result = await session.execute(video_delete)
            videos_deleted = video_result.rowcount
            
            await session.commit()
            break
        
        # Success message
        if videos_deleted > 0:
            print_success(f"Successfully deleted {videos_deleted} video record(s)")
            if notifications_deleted > 0:
                print_success(f"Successfully deleted {notifications_deleted} notification record(s)")
            elif keep_notifications:
                print_info("Notification records were preserved")
            
            # Reset last_check for affected channels to allow re-processing
            if channel_id:
                print_info("Resetting last check time for channel to allow re-processing")
                async for session in get_session():
                    channel = await DatabaseUtils.get_channel_by_id(session, channel_id)
                    if channel:
                        channel.last_check = None
                        channel.last_video_id = None
                        await session.commit()
                    break
            else:
                print_info("Resetting last check times for all channels")
                async for session in get_session():
                    channels = await DatabaseUtils.get_active_channels(session)
                    for channel in channels:
                        channel.last_check = None
                        channel.last_video_id = None
                    await session.commit()
                    break
            
            print_success("Video history cleared successfully!")
            if channel_id:
                print_info(f"Channel {channel_id} will re-process videos on next check")
            else:
                print_info("All channels will re-process videos on next check")
        else:
            print_warning("No videos were deleted")
    
    except Exception as e:
        print_error(f"Error clearing videos: {e}")
        # Rollback will happen automatically


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="YouTube Tracker Agent System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py start                              # Start the system
  python main.py add-channel UC123...              # Add channel (auto-fetch name)
  python main.py remove-channel                    # Interactive channel removal
  python main.py check-now UC123...                # Manual check (new videos only)
  python main.py check-now UC123... --force       # Force check (may re-send)
  python main.py status                            # Show status
  python main.py test-apis                         # Test API connectivity
  python main.py process-retries                   # Process failed Telegram notifications
  python main.py clear-videos                      # Clear all video history
  python main.py clear-videos --channel-id UC123... # Clear specific channel
  python main.py clear-videos --confirm            # Skip confirmation
  python main.py stop                              # Stop the system
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Start command
    subparsers.add_parser("start", help="Start the YouTube tracker system")
    
    # Stop command
    subparsers.add_parser("stop", help="Stop the YouTube tracker system")
    
    # Add channel command
    add_parser = subparsers.add_parser("add-channel", help="Add a channel to monitoring")
    add_parser.add_argument("channel_id", help="YouTube channel ID (starts with UC)")
    add_parser.add_argument("--chat-id", dest="telegram_chat_id", help="Telegram chat ID for notifications (optional, uses .env default)")
    add_parser.add_argument("--interval", type=int, default=3600, help="Check interval in seconds (default: 3600)")
    
    # Remove channel command
    remove_parser = subparsers.add_parser("remove-channel", help="Remove a channel from monitoring")
    
    # Check now command
    check_parser = subparsers.add_parser("check-now", help="Trigger immediate check for a channel")
    check_parser.add_argument("channel_id", help="YouTube channel ID")
    check_parser.add_argument("--force", action="store_true", help="Force check (may re-process old videos)")
    
    # Status command
    subparsers.add_parser("status", help="Show system status")
    
    # Health command
    subparsers.add_parser("health", help="Check system health")
    
    # Stats command
    subparsers.add_parser("stats", help="Show detailed statistics")
    
    # Test APIs command
    subparsers.add_parser("test-apis", help="Test API connectivity")
    
    # Process retry queue command
    subparsers.add_parser("process-retries", help="Process Telegram retry queue")
    
    # Cleanup retry queue command
    subparsers.add_parser("cleanup-retries", help="Clean up retry queue (remove duplicates and expired items)")
    
    # Clear videos command
    clear_parser = subparsers.add_parser("clear-videos", help="Clear processed videos from database")
    clear_parser.add_argument("--channel-id", help="Only clear videos for specific channel (optional)")
    clear_parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    clear_parser.add_argument("--keep-notifications", action="store_true", help="Keep notification records")
    
    return parser


async def main() -> None:
    """Main CLI function."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Setup logging for CLI
    import logging
    logging.basicConfig(
        level=logging.WARNING,  # Only show warnings and errors in CLI
        format='%(levelname)s: %(message)s'
    )
    
    try:
        if args.command == "start":
            await start_command()
        
        elif args.command == "stop":
            await stop_command()
        
        elif args.command == "add-channel":
            await add_channel_command(
                channel_id=args.channel_id,
                telegram_chat_id=args.telegram_chat_id,
                check_interval=args.interval
            )
        
        elif args.command == "remove-channel":
            await remove_channel_command()
        
        elif args.command == "check-now":
            await check_now_command(args.channel_id, force_check=args.force)
        
        elif args.command == "status":
            await status_command()
        
        elif args.command == "health":
            await health_command()
        
        elif args.command == "stats":
            await stats_command()
        
        elif args.command == "test-apis":
            await test_apis_command()
        
        elif args.command == "process-retries":
            await process_retries_command()
        
        elif args.command == "cleanup-retries":
            await cleanup_retry_queue_command()
        
        elif args.command == "clear-videos":
            await clear_videos_command(
                channel_id=args.channel_id,
                confirm=args.confirm,
                keep_notifications=args.keep_notifications
            )
        
        else:
            print_error(f"Unknown command: {args.command}")
            parser.print_help()
    
    except KeyboardInterrupt:
        print_info("\nOperation cancelled by user")
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        # Clean up resources
        try:
            from storage.database import close_database
            await close_database()
        except Exception as cleanup_error:
            logger.warning(f"Error during cleanup: {cleanup_error}")


if __name__ == "__main__":
    # Run the async main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_info("\nGoodbye!")
    except Exception as e:
        print_error(f"Fatal error: {e}")
        sys.exit(1)