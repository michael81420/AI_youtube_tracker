"""
Test to verify that channels with no new videos don't send notifications.
This test ensures the system correctly handles cases where no new videos are uploaded.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from models.video import VideoMetadata
from models.channel import ChannelConfig
from storage.database import Video, Channel, get_session, DatabaseUtils
from schedulers.channel_scheduler import execute_scheduled_tracking


class TestNoNewVideosBehavior:
    """Test behavior when channels have no new videos."""
    
    async def test_no_new_videos_no_notifications(self):
        """Test that channels with no new videos don't send any notifications."""
        print("="*70)
        print("Testing: No New Videos = No Notifications")
        print("="*70)
        
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        
        test_channel = ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="No Videos Test Channel",
            telegram_chat_id="123456789",
            check_interval=3600,
            is_active=True,
            last_check=datetime.utcnow() - timedelta(hours=2)  # Last checked 2 hours ago
        )
        
        print(f"Channel: {test_channel.channel_name}")
        print(f"Last check: {test_channel.last_check}")
        print(f"Current time: {datetime.utcnow()}")
        
        # Mock get_channel_videos to return empty list (no new videos)
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[])
            
            # Mock notification to ensure it's never called
            with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                mock_notify.ainvoke = AsyncMock()
                
                print("\n1. First check - no new videos...")
                # Import here to avoid circular import
                from chains.tracking_chain import TrackingChain
                tracking_chain = TrackingChain()
                result1 = await tracking_chain.execute_tracking_workflow(
                    channel_config=test_channel,
                    force_check=False
                )
                
                # Verify first check
                print(f"   Success: {result1['success']}")
                print(f"   No new videos flag: {result1.get('no_new_videos', False)}")
                print(f"   Videos processed: {result1['videos_processed']}")
                print(f"   Notifications sent: {result1['notifications_sent']}")
                print(f"   API calls made: {mock_get_videos.ainvoke.call_count}")
                print(f"   Notification calls: {mock_notify.ainvoke.call_count}")
                
                assert result1["success"], "Check should succeed even with no new videos"
                assert result1.get("no_new_videos", False), "Should be flagged as no new videos"
                assert result1["videos_processed"] == 0, "Should process 0 videos"
                assert result1["notifications_sent"] == 0, "Should send 0 notifications"
                assert mock_get_videos.ainvoke.call_count == 1, "Should call YouTube API once"
                assert mock_notify.ainvoke.call_count == 0, "Should NOT call notification API"
                
                print("   [OK] First check behaved correctly")
                
                print("\n2. Second check - still no new videos...")
                result2 = await tracking_chain.execute_tracking_workflow(
                    channel_config=test_channel,
                    force_check=False
                )
                
                # Verify second check
                print(f"   Success: {result2['success']}")
                print(f"   No new videos flag: {result2.get('no_new_videos', False)}")
                print(f"   Videos processed: {result2['videos_processed']}")
                print(f"   Notifications sent: {result2['notifications_sent']}")
                print(f"   Total API calls: {mock_get_videos.ainvoke.call_count}")
                print(f"   Total notification calls: {mock_notify.ainvoke.call_count}")
                
                assert result2["success"], "Second check should also succeed"
                assert result2.get("no_new_videos", False), "Should still be flagged as no new videos"
                assert result2["videos_processed"] == 0, "Should still process 0 videos"
                assert result2["notifications_sent"] == 0, "Should still send 0 notifications"
                assert mock_get_videos.ainvoke.call_count == 2, "Should call YouTube API twice total"
                assert mock_notify.ainvoke.call_count == 0, "Should STILL not call notification API"
                
                print("   [OK] Second check behaved correctly")
        
        print("\n" + "="*70)
        print("[SUCCESS] No new videos correctly results in no notifications!")
        print("="*70)
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        return True
    
    async def test_scheduled_tracking_no_new_videos(self):
        """Test that scheduled tracking handles no new videos correctly."""
        print("\n" + "="*70)
        print("Testing: Scheduled Tracking with No New Videos")
        print("="*70)
        
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        
        test_channel = ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="Scheduled No Videos Test",
            telegram_chat_id="987654321",
            check_interval=3600,
            is_active=True
        )
        
        # Save channel to database for scheduled tracking
        async for session in get_session():
            channel_record = Channel(
                channel_id=test_channel.channel_id,
                channel_name=test_channel.channel_name,
                check_interval=test_channel.check_interval,
                telegram_chat_id=test_channel.telegram_chat_id,
                is_active=test_channel.is_active,
                last_check=datetime.utcnow() - timedelta(hours=1),  # Last checked 1 hour ago
                last_video_id=None
            )
            session.add(channel_record)
            await session.commit()
            break
        
        # Mock get_channel_videos to return empty list
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[])
            
            # Mock notification to ensure it's never called
            with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                mock_notify.ainvoke = AsyncMock()
                
                print("Executing scheduled tracking...")
                await execute_scheduled_tracking(test_channel.channel_id)
                
                print(f"   YouTube API calls: {mock_get_videos.ainvoke.call_count}")
                print(f"   Notification calls: {mock_notify.ainvoke.call_count}")
                
                assert mock_get_videos.ainvoke.call_count == 1, "Should call YouTube API once in scheduled tracking"
                assert mock_notify.ainvoke.call_count == 0, "Should NOT call notification API in scheduled tracking"
                
                print("   [OK] Scheduled tracking handled no new videos correctly")
        
        print("\n[SUCCESS] Scheduled tracking with no new videos works correctly!")
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        return True
    
    async def test_published_after_timestamp_usage(self):
        """Test that the system correctly uses published_after timestamp to avoid re-processing."""
        print("\n" + "="*70)
        print("Testing: Published After Timestamp Usage")
        print("="*70)
        
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        
        last_check_time = datetime.utcnow() - timedelta(hours=3)
        test_channel = ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="Timestamp Test Channel",
            telegram_chat_id="555666777",
            check_interval=3600,
            is_active=True,
            last_check=last_check_time
        )
        
        print(f"Last check time: {last_check_time}")
        print(f"Current time: {datetime.utcnow()}")
        
        # Mock get_channel_videos to capture the call arguments
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[])
            
            print("Executing check...")
            # Import here to avoid circular import
            from chains.tracking_chain import TrackingChain
            tracking_chain = TrackingChain()
            result = await tracking_chain.execute_tracking_workflow(
                channel_config=test_channel,
                force_check=False
            )
            
            # Verify the API was called with correct timestamp
            assert mock_get_videos.ainvoke.call_count == 1, "Should call YouTube API once"
            call_args = mock_get_videos.ainvoke.call_args[0][0]  # First positional argument (dict)
            
            print(f"   API call arguments:")
            print(f"     channel_id: {call_args['channel_id']}")
            print(f"     published_after: {call_args['published_after']}")
            print(f"     max_results: {call_args['max_results']}")
            
            # The published_after should be the last_check time
            assert call_args["channel_id"] == test_channel.channel_id
            assert call_args["published_after"] == last_check_time, f"published_after should be {last_check_time}, got {call_args['published_after']}"
            
            print("   [OK] Correct published_after timestamp used")
        
        print("\n[SUCCESS] Published after timestamp is used correctly!")
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        return True
    
    async def cleanup_test_data(self, channel_id: str):
        """Clean up test data from database."""
        async for session in get_session():
            try:
                # Clean up channel
                channel_record = await DatabaseUtils.get_channel_by_id(session, channel_id)
                if channel_record:
                    await session.delete(channel_record)
                    await session.commit()
                    
                # Clean up any videos from this channel
                from sqlalchemy import select
                videos_to_delete = await session.execute(
                    select(Video).where(Video.channel_id == channel_id)
                )
                for video in videos_to_delete.scalars():
                    await session.delete(video)
                await session.commit()
                    
            except Exception:
                # Ignore cleanup errors
                pass
            break


async def run_tests():
    """Run all no new videos behavior tests."""
    test_class = TestNoNewVideosBehavior()
    
    print("Running No New Videos Behavior Tests...")
    
    try:
        # Test 1: Basic no new videos behavior
        success1 = await test_class.test_no_new_videos_no_notifications()
        
        # Test 2: Scheduled tracking with no new videos
        success2 = await test_class.test_scheduled_tracking_no_new_videos()
        
        # Test 3: Timestamp usage verification
        success3 = await test_class.test_published_after_timestamp_usage()
        
        if success1 and success2 and success3:
            print("\n" + "="*70)
            print("[SUCCESS] ALL NO NEW VIDEOS TESTS PASSED!")
            print("✓ Channels with no new videos don't send notifications")
            print("✓ Scheduled tracking handles no new videos correctly") 
            print("✓ Published after timestamp is used correctly")
            print("="*70)
            return True
        else:
            print("\n[ERROR] Some tests failed!")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    if success:
        exit(0)
    else:
        exit(1)