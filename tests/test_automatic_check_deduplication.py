"""
Test cases for automatic check deduplication mechanism.
Tests that scheduled/automatic checks don't send duplicate notifications.
"""

import pytest
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from models.video import VideoMetadata
from models.channel import ChannelConfig
from storage.database import Video, Channel, get_session, DatabaseUtils
from agents.youtube_tracker import youtube_tracker_agent
from chains.tracking_chain import tracking_chain
from schedulers.channel_scheduler import execute_scheduled_tracking


class TestAutomaticCheckDeduplication:
    """Test cases for automatic check deduplication."""
    
    @pytest.fixture
    async def test_video_new(self):
        """Create a test video for new video scenario."""
        return VideoMetadata(
            video_id="AUTOTEST123",  # 11 character test ID
            channel_id="UC1234567890123456789012",
            title="New Video for Auto Check Test",
            description="A new video to test automatic check deduplication",
            published_at=datetime.utcnow(),
            thumbnail_url="https://example.com/thumb.jpg",
            duration="PT3M45S",
            view_count=500,
            like_count=25,
            comment_count=5
        )
    
    @pytest.fixture
    async def test_channel_auto(self):
        """Create a test channel config for automatic check."""
        return ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="Auto Check Test Channel",
            telegram_chat_id="987654321",
            check_interval=3600,
            is_active=True
        )
    
    async def test_no_new_videos_double_check(self, test_channel_auto):
        """Test that channel with no new videos gets checked twice but doesn't duplicate processing."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        
        # Mock get_channel_videos to return empty list (no new videos)
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[])
            
            # First automatic check - should succeed with no videos
            result1 = await tracking_chain.execute_tracking_workflow(
                channel_config=test_channel_auto,
                force_check=False
            )
            
            # Verify first check
            assert result1["success"], f"First check should succeed: {result1.get('errors', [])}"
            assert result1.get("no_new_videos", False), "First check should indicate no new videos"
            assert result1["videos_processed"] == 0, "First check should process 0 videos"
            assert result1["notifications_sent"] == 0, "First check should send 0 notifications"
            
            # Second automatic check - should also succeed with no videos
            result2 = await tracking_chain.execute_tracking_workflow(
                channel_config=test_channel_auto,
                force_check=False
            )
            
            # Verify second check
            assert result2["success"], f"Second check should succeed: {result2.get('errors', [])}"
            assert result2.get("no_new_videos", False), "Second check should indicate no new videos"
            assert result2["videos_processed"] == 0, "Second check should process 0 videos"
            assert result2["notifications_sent"] == 0, "Second check should send 0 notifications"
            
            # Verify API was called twice (once for each check)
            assert mock_get_videos.ainvoke.call_count == 2, "API should be called for both checks"
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
    
    async def test_new_video_double_check_only_first_notifies(self, test_video_new, test_channel_auto):
        """Test that new video only gets notified on first check, second check skips notification."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_new.video_id)
        
        # Mock get_channel_videos to return the test video
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[test_video_new])
            
            # Mock notification sending to track calls
            with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                # Configure mock to return success
                mock_notify.return_value = AsyncMock()
                mock_notify.return_value.success = True
                mock_notify.return_value.error_message = None
                mock_notify.ainvoke = AsyncMock()
                mock_notify.ainvoke.return_value = AsyncMock()
                mock_notify.ainvoke.return_value.success = True
                mock_notify.ainvoke.return_value.error_message = None
                
                # First automatic check - should process video and send notification
                result1 = await tracking_chain.execute_tracking_workflow(
                    channel_config=test_channel_auto,
                    force_check=False
                )
                
                # Verify first check
                assert result1["success"], f"First check should succeed: {result1.get('errors', [])}"
                assert result1["videos_processed"] == 1, "First check should process 1 video"
                assert result1["notifications_sent"] == 1, "First check should send 1 notification"
                
                # Verify notification was called
                assert mock_notify.ainvoke.call_count == 1, "Notification should be sent once"
                
                # Verify video is in database with notification_sent = True
                async for session in get_session():
                    video_record = await DatabaseUtils.get_video_by_id(session, test_video_new.video_id)
                    assert video_record is not None, "Video should be saved to database"
                    assert video_record.notification_sent, "Video should be marked as notified"
                    break
                
                # Second automatic check - should find same video but skip notification
                result2 = await tracking_chain.execute_tracking_workflow(
                    channel_config=test_channel_auto,
                    force_check=False
                )
                
                # Verify second check
                assert result2["success"], f"Second check should succeed: {result2.get('errors', [])}"
                assert result2["videos_processed"] == 0, "Second check should process 0 videos (already processed)"
                assert result2["notifications_sent"] == 0, "Second check should send 0 notifications"
                
                # Verify notification was NOT called again
                assert mock_notify.ainvoke.call_count == 1, "Notification should still be called only once"
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_new.video_id)
    
    async def test_scheduled_tracking_deduplication(self, test_video_new, test_channel_auto):
        """Test that scheduled tracking properly handles deduplication."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_new.video_id)
        
        # First, save the channel to database so scheduled tracking can find it
        async for session in get_session():
            channel_record = Channel(
                channel_id=test_channel_auto.channel_id,
                channel_name=test_channel_auto.channel_name,
                check_interval=test_channel_auto.check_interval,
                telegram_chat_id=test_channel_auto.telegram_chat_id,
                is_active=test_channel_auto.is_active,
                last_check=None,
                last_video_id=None
            )
            session.add(channel_record)
            await session.commit()
            break
        
        # Mock get_channel_videos to return the test video
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[test_video_new])
            
            # Mock notification sending to track calls
            with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                # Configure mock to return success
                mock_notify.return_value = AsyncMock()
                mock_notify.return_value.success = True
                mock_notify.return_value.error_message = None
                mock_notify.ainvoke = AsyncMock()
                mock_notify.ainvoke.return_value = AsyncMock()
                mock_notify.ainvoke.return_value.success = True
                mock_notify.ainvoke.return_value.error_message = None
                
                # First scheduled execution - should process and notify
                await execute_scheduled_tracking(test_channel_auto.channel_id)
                
                # Verify notification was sent
                assert mock_notify.ainvoke.call_count == 1, "First scheduled check should send notification"
                
                # Verify video is in database with notification_sent = True
                async for session in get_session():
                    video_record = await DatabaseUtils.get_video_by_id(session, test_video_new.video_id)
                    assert video_record is not None, "Video should be saved to database"
                    assert video_record.notification_sent, "Video should be marked as notified"
                    break
                
                # Second scheduled execution - should skip notification
                await execute_scheduled_tracking(test_channel_auto.channel_id)
                
                # Verify notification was NOT called again
                assert mock_notify.ainvoke.call_count == 1, "Second scheduled check should not send duplicate notification"
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_new.video_id)
    
    async def test_notification_sent_even_when_summarization_fails(self, test_video_new, test_channel_auto):
        """Test that notifications are sent even when summarization fails."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_new.video_id)
        
        # Mock get_channel_videos to return the test video
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[test_video_new])
            
            # Mock summarization to fail
            with patch('agents.summarizer_agent.summarize_video_content') as mock_summarize:
                mock_summarize.ainvoke = AsyncMock()
                mock_summarize.ainvoke.side_effect = Exception("API quota exceeded")
                
                # Mock notification sending to track calls
                with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                    # Configure mock to return success
                    mock_notify.return_value = AsyncMock()
                    mock_notify.return_value.success = True
                    mock_notify.return_value.error_message = None
                    mock_notify.ainvoke = AsyncMock()
                    mock_notify.ainvoke.return_value = AsyncMock()
                    mock_notify.ainvoke.return_value.success = True
                    mock_notify.ainvoke.return_value.error_message = None
                    
                    # Process video - should send notification despite summarization failure
                    result = await youtube_tracker_agent._process_video(test_video_new, test_channel_auto)
                    
                    # Verify notification was sent despite summarization failure
                    assert mock_notify.ainvoke.call_count == 1, "Notification should be sent even when summarization fails"
                    assert result.get("notification_sent", False), "Result should indicate notification was sent"
                    assert result.get("error") is not None, "Result should include summarization error"
                    
                    # Verify video is saved with notification_sent = True
                    async for session in get_session():
                        video_record = await DatabaseUtils.get_video_by_id(session, test_video_new.video_id)
                        assert video_record is not None, "Video should be saved to database"
                        assert video_record.notification_sent, "Video should be marked as notified"
                        assert video_record.summary is None, "Video should have no summary due to failure"
                        break
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_new.video_id)
    
    async def test_inactive_channel_skipped_in_scheduled_tracking(self, test_channel_auto):
        """Test that inactive channels are properly skipped in scheduled tracking."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        
        # Save inactive channel to database
        async for session in get_session():
            channel_record = Channel(
                channel_id=test_channel_auto.channel_id,
                channel_name=test_channel_auto.channel_name,
                check_interval=test_channel_auto.check_interval,
                telegram_chat_id=test_channel_auto.telegram_chat_id,
                is_active=False,  # Mark as inactive
                last_check=None,
                last_video_id=None
            )
            session.add(channel_record)
            await session.commit()
            break
        
        # Mock get_channel_videos to track if it's called (it shouldn't be for inactive channels)
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[])
            
            # Execute scheduled tracking - should skip inactive channel
            await execute_scheduled_tracking(test_channel_auto.channel_id)
            
            # Verify API was NOT called for inactive channel
            assert mock_get_videos.ainvoke.call_count == 0, "API should not be called for inactive channel"
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
    
    async def test_no_new_videos_no_notifications_in_automatic_check(self, test_channel_auto):
        """Test that automatic checks with no new videos don't send notifications."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        
        # Save active channel to database with a previous check time
        async for session in get_session():
            from datetime import timedelta
            channel_record = Channel(
                channel_id=test_channel_auto.channel_id,
                channel_name=test_channel_auto.channel_name,
                check_interval=test_channel_auto.check_interval,
                telegram_chat_id=test_channel_auto.telegram_chat_id,
                is_active=True,
                last_check=datetime.utcnow() - timedelta(hours=2),  # Last checked 2 hours ago
                last_video_id=None
            )
            session.add(channel_record)
            await session.commit()
            break
        
        # Mock get_channel_videos to return empty list (no new videos)
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[])
            
            # Mock notification to ensure it's never called
            with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                mock_notify.ainvoke = AsyncMock()
                
                # Execute scheduled tracking - should find no new videos
                await execute_scheduled_tracking(test_channel_auto.channel_id)
                
                # Verify behavior
                assert mock_get_videos.ainvoke.call_count == 1, "Should call YouTube API once"
                assert mock_notify.ainvoke.call_count == 0, "Should NOT call notification API when no new videos"
                
                # Verify the API was called with correct timestamp (last_check)
                call_args = mock_get_videos.ainvoke.call_args[0][0]
                assert "published_after" in call_args, "Should include published_after parameter"
                # The published_after should be approximately the last_check time we set
                time_diff = abs((call_args["published_after"] - (datetime.utcnow() - timedelta(hours=2))).total_seconds())
                assert time_diff < 60, "published_after should be close to the last_check time"
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
    
    async def cleanup_test_data(self, identifier: str):
        """Clean up test data from database. Handles both channel_id and video_id."""
        async for session in get_session():
            try:
                # Try to clean up as video_id first
                if len(identifier) == 11 or identifier.startswith("TEST") or identifier.startswith("AUTO"):
                    video_record = await DatabaseUtils.get_video_by_id(session, identifier)
                    if video_record:
                        await session.delete(video_record)
                        await session.commit()
                
                # Try to clean up as channel_id
                if identifier.startswith("UC"):
                    channel_record = await DatabaseUtils.get_channel_by_id(session, identifier)
                    if channel_record:
                        await session.delete(channel_record)
                        await session.commit()
                        
                    # Also clean up any videos from this channel
                    from sqlalchemy import select
                    videos_to_delete = await session.execute(
                        select(Video).where(Video.channel_id == identifier)
                    )
                    for video in videos_to_delete.scalars():
                        await session.delete(video)
                    await session.commit()
                    
            except Exception as e:
                # Ignore cleanup errors
                pass
            break


# Async test runner
if __name__ == "__main__":
    async def run_tests():
        test_class = TestAutomaticCheckDeduplication()
        
        # Create fixtures
        test_video_new = VideoMetadata(
            video_id="AUTOTEST123",  # 11 character test ID
            channel_id="UC1234567890123456789012",
            title="New Video for Auto Check Test",
            description="A new video to test automatic check deduplication",
            published_at=datetime.utcnow(),
            thumbnail_url="https://example.com/thumb.jpg",
            duration="PT3M45S",
            view_count=500,
            like_count=25,
            comment_count=5
        )
        
        test_channel_auto = ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="Auto Check Test Channel",
            telegram_chat_id="987654321",
            check_interval=3600,
            is_active=True
        )
        
        print("Running automatic check deduplication tests...")
        
        try:
            print("1. Testing no new videos double check...")
            await test_class.test_no_new_videos_double_check(test_channel_auto)
            print("PASSED: No new videos double check handled correctly")
            
            print("2. Testing new video double check only first notifies...")
            await test_class.test_new_video_double_check_only_first_notifies(test_video_new, test_channel_auto)
            print("PASSED: New video only notified on first check")
            
            print("3. Testing scheduled tracking deduplication...")
            await test_class.test_scheduled_tracking_deduplication(test_video_new, test_channel_auto)
            print("PASSED: Scheduled tracking prevents duplicate notifications")
            
            print("4. Testing notification sent even when summarization fails...")
            await test_class.test_notification_sent_even_when_summarization_fails(test_video_new, test_channel_auto)
            print("PASSED: Notifications sent even when summarization fails")
            
            print("5. Testing inactive channel skipped in scheduled tracking...")
            await test_class.test_inactive_channel_skipped_in_scheduled_tracking(test_channel_auto)
            print("PASSED: Inactive channels properly skipped")
            
            print("6. Testing no new videos results in no notifications...")
            await test_class.test_no_new_videos_no_notifications_in_automatic_check(test_channel_auto)
            print("PASSED: No new videos correctly results in no notifications")
            
            print("\nAll automatic check deduplication tests passed!")
            
        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(run_tests())