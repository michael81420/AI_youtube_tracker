"""
Test to verify that notifications are sent even when summarization fails.
This test focuses on the specific issue reported by the user.
"""

import pytest
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from unittest.mock import AsyncMock, patch
from models.video import VideoMetadata
from models.channel import ChannelConfig
from models.notification import NotificationStatus
from storage.database import Video, Channel, get_session, DatabaseUtils
from agents.youtube_tracker import youtube_tracker_agent
from chains.tracking_chain import tracking_chain
from schedulers.channel_scheduler import execute_scheduled_tracking


class TestNotificationFix:
    """Test notification fix for summarization failures."""
    
    @pytest.fixture
    async def test_video_notification(self):
        """Create a test video for notification testing."""
        return VideoMetadata(
            video_id="NOTIFYTEST1",  # 11 character test ID
            channel_id="UC1234567890123456789012",
            title="Test Video for Notification Fix",
            description="A test video to verify notifications work when summarization fails",
            published_at=datetime.utcnow(),
            thumbnail_url="https://example.com/thumb.jpg",
            duration="PT4M20S",
            view_count=750,
            like_count=35,
            comment_count=8,
            url="https://www.youtube.com/watch?v=NOTIFYTEST1"
        )
    
    @pytest.fixture
    async def test_channel_notification(self):
        """Create a test channel config for notification testing."""
        return ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="Notification Test Channel",
            telegram_chat_id="123456789",
            check_interval=3600,
            is_active=True
        )
    
    async def test_notification_sent_despite_summarization_failure(self, test_video_notification, test_channel_notification):
        """Test that notifications are sent even when summarization fails."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_notification.video_id)
        
        # Mock summarization to fail
        with patch('agents.summarizer_agent.summarize_video_content') as mock_summarize:
            mock_summarize.ainvoke = AsyncMock()
            mock_summarize.ainvoke.side_effect = Exception("API quota exceeded - summarization failed")
            
            # Mock notification sending to track calls
            with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                # Configure mock to return success
                mock_notify.ainvoke = AsyncMock()
                mock_notify.ainvoke.return_value = NotificationStatus(
                    video_id=test_video_notification.video_id,
                    chat_id=test_channel_notification.telegram_chat_id,
                    success=True,
                    message_id=123
                )
                
                # Process video - should send notification despite summarization failure
                result = await youtube_tracker_agent._process_video(test_video_notification, test_channel_notification)
                
                # Verify notification was called with None summary
                assert mock_notify.ainvoke.call_count == 1, "Notification should be sent even when summarization fails"
                call_args = mock_notify.ainvoke.call_args[0][0]  # First positional argument (dict)
                assert call_args["video"] == test_video_notification
                assert call_args["summary"] is None, "Summary should be None when summarization fails"
                assert call_args["chat_id"] == test_channel_notification.telegram_chat_id
                
                # Verify result indicates notification was sent
                assert result.get("notification_sent", False), "Result should indicate notification was sent"
                assert result.get("error") is not None, "Result should include summarization error"
                
                # Verify video is saved with notification_sent = True
                async for session in get_session():
                    video_record = await DatabaseUtils.get_video_by_id(session, test_video_notification.video_id)
                    assert video_record is not None, "Video should be saved to database"
                    assert video_record.notification_sent, "Video should be marked as notified"
                    assert video_record.summary is None, "Video should have no summary due to failure"
                    break
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_notification.video_id)
    
    async def test_scheduled_tracking_notification_with_summarization_failure(self, test_video_notification, test_channel_notification):
        """Test that scheduled tracking sends notifications even when summarization fails."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_notification.video_id)
        
        # First, save the channel to database so scheduled tracking can find it
        async for session in get_session():
            channel_record = Channel(
                channel_id=test_channel_notification.channel_id,
                channel_name=test_channel_notification.channel_name,
                check_interval=test_channel_notification.check_interval,
                telegram_chat_id=test_channel_notification.telegram_chat_id,
                is_active=test_channel_notification.is_active,
                last_check=None,
                last_video_id=None
            )
            session.add(channel_record)
            await session.commit()
            break
        
        # Mock get_channel_videos to return the test video
        with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
            mock_get_videos.ainvoke = AsyncMock(return_value=[test_video_notification])
            
            # Mock summarization to fail
            with patch('agents.summarizer_agent.summarize_video_content') as mock_summarize:
                mock_summarize.ainvoke = AsyncMock()
                mock_summarize.ainvoke.side_effect = Exception("API quota exceeded")
                
                # Mock notification sending to track calls
                with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                    # Configure mock to return success
                    mock_notify.ainvoke = AsyncMock()
                    mock_notify.ainvoke.return_value = NotificationStatus(
                        video_id=test_video_notification.video_id,
                        chat_id=test_channel_notification.telegram_chat_id,
                        success=True,
                        message_id=456
                    )
                    
                    # Execute scheduled tracking
                    await execute_scheduled_tracking(test_channel_notification.channel_id)
                    
                    # Verify notification was sent despite summarization failure
                    assert mock_notify.ainvoke.call_count == 1, "Scheduled tracking should send notification even when summarization fails"
                    
                    # Verify call was made with None summary
                    call_args = mock_notify.ainvoke.call_args[0][0]
                    assert call_args["summary"] is None, "Summary should be None when summarization fails in scheduled tracking"
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_notification.video_id)
    
    async def test_notification_with_successful_summarization(self, test_video_notification, test_channel_notification):
        """Test that notifications work correctly when summarization succeeds."""
        # Clean up first
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_notification.video_id)
        
        test_summary = "This is a test video summary that was successfully generated."
        
        # Mock summarization to succeed
        with patch('agents.summarizer_agent.summarize_video_content') as mock_summarize:
            mock_summarize.ainvoke = AsyncMock()
            mock_summary_result = AsyncMock()
            mock_summary_result.summary = test_summary
            mock_summarize.ainvoke.return_value = mock_summary_result
            
            # Mock notification sending to track calls
            with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                # Configure mock to return success
                mock_notify.ainvoke = AsyncMock()
                mock_notify.ainvoke.return_value = NotificationStatus(
                    video_id=test_video_notification.video_id,
                    chat_id=test_channel_notification.telegram_chat_id,
                    success=True,
                    message_id=789
                )
                
                # Process video - should send notification with summary
                result = await youtube_tracker_agent._process_video(test_video_notification, test_channel_notification)
                
                # Verify notification was called with summary
                assert mock_notify.ainvoke.call_count == 1, "Notification should be sent when summarization succeeds"
                call_args = mock_notify.ainvoke.call_args[0][0]
                assert call_args["video"] == test_video_notification
                assert call_args["summary"] == test_summary, "Summary should be included when summarization succeeds"
                assert call_args["chat_id"] == test_channel_notification.telegram_chat_id
                
                # Verify result indicates success
                assert result.get("notification_sent", False), "Result should indicate notification was sent"
                assert result.get("summary_generated", False), "Result should indicate summary was generated"
                assert result.get("error") is None, "Result should not include error when everything succeeds"
        
        # Clean up
        await self.cleanup_test_data("UC1234567890123456789012")
        await self.cleanup_test_data(test_video_notification.video_id)
    
    async def cleanup_test_data(self, identifier: str):
        """Clean up test data from database. Handles both channel_id and video_id."""
        async for session in get_session():
            try:
                # Try to clean up as video_id first
                if len(identifier) == 11 or identifier.startswith("NOTIFY"):
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
        test_class = TestNotificationFix()
        
        # Create fixtures
        test_video_notification = VideoMetadata(
            video_id="NOTIFYTEST1",  # 11 character test ID
            channel_id="UC1234567890123456789012",
            title="Test Video for Notification Fix",
            description="A test video to verify notifications work when summarization fails",
            published_at=datetime.utcnow(),
            thumbnail_url="https://example.com/thumb.jpg",
            duration="PT4M20S",
            view_count=750,
            like_count=35,
            comment_count=8,
            url="https://www.youtube.com/watch?v=NOTIFYTEST1"
        )
        
        test_channel_notification = ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="Notification Test Channel",
            telegram_chat_id="123456789",
            check_interval=3600,
            is_active=True
        )
        
        print("Running notification fix tests...")
        
        try:
            print("1. Testing notification sent despite summarization failure...")
            await test_class.test_notification_sent_despite_summarization_failure(test_video_notification, test_channel_notification)
            print("PASSED: Notification sent despite summarization failure")
            
            print("2. Testing scheduled tracking notification with summarization failure...")
            await test_class.test_scheduled_tracking_notification_with_summarization_failure(test_video_notification, test_channel_notification)
            print("PASSED: Scheduled tracking sends notification despite summarization failure")
            
            print("3. Testing notification with successful summarization...")
            await test_class.test_notification_with_successful_summarization(test_video_notification, test_channel_notification)
            print("PASSED: Notification works correctly with successful summarization")
            
            print("\nAll notification fix tests passed!")
            
        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(run_tests())