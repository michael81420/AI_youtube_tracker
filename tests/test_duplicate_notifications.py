"""
Test cases for preventing duplicate notification sending.
"""

import pytest
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from models.video import VideoMetadata
from models.channel import ChannelConfig
from storage.database import Video, get_session, DatabaseUtils
from agents.youtube_tracker import youtube_tracker_agent
from chains.tracking_chain import tracking_chain


class TestDuplicateNotificationPrevention:
    """Test cases for duplicate notification prevention."""
    
    @pytest.fixture
    async def test_video(self):
        """Create a test video."""
        return VideoMetadata(
            video_id="TEST0123456",  # 11 character test ID
            channel_id="UC1234567890123456789012",
            title="Test Video for Duplicate Prevention",
            description="A test video to verify duplicate notification prevention",
            published_at=datetime.utcnow(),
            thumbnail_url="https://example.com/thumb.jpg",
            duration="PT5M30S",
            view_count=1000,
            like_count=50,
            comment_count=10
        )
    
    @pytest.fixture
    async def test_channel(self):
        """Create a test channel config."""
        return ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="Test Channel",
            telegram_chat_id="123456789",
            check_interval=3600
        )
    
    async def test_notification_sent_once_only(self, test_video, test_channel):
        """Test that notification is sent only once for same video."""
        # Clean up any existing test data
        await self.cleanup_test_data(test_video.video_id)
        
        # First processing - should process and send notification
        result1 = await youtube_tracker_agent._process_video(test_video, test_channel)
        
        # Verify first processing
        assert not result1.get("already_processed", False), "First processing should not be marked as already processed"
        
        # Check database state after first processing
        async for session in get_session():
            video_record = await DatabaseUtils.get_video_by_id(session, test_video.video_id)
            assert video_record is not None, "Video should be saved to database"
            assert video_record.processed_at is not None, "Video should have processed_at timestamp"
            break
        
        # Second processing - should skip notification
        result2 = await youtube_tracker_agent._process_video(test_video, test_channel)
        
        # Verify second processing
        assert result2.get("already_processed", False), "Second processing should be marked as already processed"
        assert result2.get("notification_sent", False), "Second processing should indicate notification was already sent"
        
        # Clean up
        await self.cleanup_test_data(test_video.video_id)
    
    async def test_tracking_chain_deduplication(self, test_video, test_channel):
        """Test that tracking chain prevents duplicate notifications."""
        # Clean up any existing test data
        await self.cleanup_test_data(test_video.video_id)
        
        # Mock the video fetching to return our test video
        original_check = tracking_chain._check_for_videos
        
        async def mock_check_for_videos(channel_config, force_check):
            return {
                "success": True,
                "videos": [test_video],
                "count": 1
            }
        
        tracking_chain._check_for_videos = mock_check_for_videos
        
        try:
            # First execution - should process and send notification
            result1 = await tracking_chain.execute_tracking_workflow(
                channel_config=test_channel,
                force_check=False
            )
            
            # Verify first execution
            assert result1["success"], f"First execution should succeed: {result1.get('errors', [])}"
            assert result1["videos_processed"] > 0, "First execution should process videos"
            
            # Second execution - should skip already processed video
            result2 = await tracking_chain.execute_tracking_workflow(
                channel_config=test_channel,
                force_check=False
            )
            
            # Verify second execution
            assert result2["success"], f"Second execution should succeed: {result2.get('errors', [])}"
            assert result2["videos_processed"] == 0, "Second execution should not process already processed videos"
            
        finally:
            # Restore original method
            tracking_chain._check_for_videos = original_check
            # Clean up
            await self.cleanup_test_data(test_video.video_id)
    
    async def test_force_check_with_deduplication(self, test_video, test_channel):
        """Test that force check still respects notification deduplication."""
        # Clean up any existing test data
        await self.cleanup_test_data(test_video.video_id)
        
        # First processing - should process and send notification
        result1 = await youtube_tracker_agent._process_video(test_video, test_channel)
        assert not result1.get("already_processed", False)
        
        # Mock the video fetching for force check
        original_check = tracking_chain._check_for_videos
        
        async def mock_check_for_videos(channel_config, force_check):
            return {
                "success": True,
                "videos": [test_video],
                "count": 1
            }
        
        tracking_chain._check_for_videos = mock_check_for_videos
        
        try:
            # Force check - should still respect notification deduplication
            result2 = await tracking_chain.execute_tracking_workflow(
                channel_config=test_channel,
                force_check=True  # Force check should still not duplicate notifications
            )
            
            # Verify force check behavior
            assert result2["success"], f"Force check should succeed: {result2.get('errors', [])}"
            assert result2["videos_processed"] == 0, "Force check should not re-process videos with notifications already sent"
            
        finally:
            # Restore original method
            tracking_chain._check_for_videos = original_check
            # Clean up
            await self.cleanup_test_data(test_video.video_id)
    
    async def test_processed_but_not_notified_video(self, test_video, test_channel):
        """Test that videos processed but not notified get notifications sent."""
        # Clean up any existing test data
        await self.cleanup_test_data(test_video.video_id)
        
        # Manually create a video record that's processed but not notified
        async for session in get_session():
            video_record = Video(
                video_id=test_video.video_id,
                channel_id=test_video.channel_id,
                title=test_video.title,
                description=test_video.description,
                published_at=test_video.published_at,
                thumbnail_url=test_video.thumbnail_url,
                duration=test_video.duration,
                view_count=test_video.view_count,
                like_count=test_video.like_count,
                comment_count=test_video.comment_count,
                processed_at=datetime.utcnow(),
                summary="Test summary",
                notification_sent=False  # Processed but not notified
            )
            session.add(video_record)
            await session.commit()
            break
        
        # Process the video - should send notification for already processed video
        result = await youtube_tracker_agent._process_video(test_video, test_channel)
        
        # Verify behavior
        assert result.get("already_processed", False), "Should be marked as already processed"
        assert result.get("summary_generated", False), "Should reuse existing summary"
        
        # Verify database state
        async for session in get_session():
            video_record = await DatabaseUtils.get_video_by_id(session, test_video.video_id)
            assert video_record.notification_sent, "Video should now be marked as notified"
            break
        
        # Clean up
        await self.cleanup_test_data(test_video.video_id)
    
    async def cleanup_test_data(self, video_id: str):
        """Clean up test data from database."""
        async for session in get_session():
            # Clean up video record
            video_record = await DatabaseUtils.get_video_by_id(session, video_id)
            if video_record:
                await session.delete(video_record)
                await session.commit()
            break


# Async test runner
if __name__ == "__main__":
    async def run_tests():
        test_class = TestDuplicateNotificationPrevention()
        
        # Create fixtures
        test_video = VideoMetadata(
            video_id="TEST0123456",  # 11 character test ID
            channel_id="UC1234567890123456789012",
            title="Test Video for Duplicate Prevention",
            description="A test video to verify duplicate notification prevention",
            published_at=datetime.utcnow(),
            thumbnail_url="https://example.com/thumb.jpg",
            duration="PT5M30S",
            view_count=1000,
            like_count=50,
            comment_count=10
        )
        
        test_channel = ChannelConfig(
            channel_id="UC1234567890123456789012",
            channel_name="Test Channel",
            telegram_chat_id="123456789",
            check_interval=3600
        )
        
        print("Running duplicate notification prevention tests...")
        
        try:
            print("1. Testing notification sent once only...")
            await test_class.test_notification_sent_once_only(test_video, test_channel)
            print("✅ PASSED: Notification sent once only")
            
            print("2. Testing processed but not notified video...")
            await test_class.test_processed_but_not_notified_video(test_video, test_channel)
            print("✅ PASSED: Processed but not notified video gets notification")
            
            print("\n🎉 All tests passed!")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(run_tests())