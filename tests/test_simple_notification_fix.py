"""
Simple test to verify that the notification fix is working.
This test demonstrates that notifications are attempted even when summarization fails.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from unittest.mock import patch, AsyncMock
from datetime import datetime
from models.video import VideoMetadata
from models.channel import ChannelConfig
from models.notification import NotificationStatus
from agents.youtube_tracker import youtube_tracker_agent

# Configure logging to show the test output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_notification_fix():
    """Test that demonstrates the notification fix is working."""
    print("="*60)
    print("Testing Notification Fix")
    print("="*60)
    
    # Create test data
    test_video = VideoMetadata(
        video_id="FIXTEST1234",  # 11 characters
        channel_id="UC1234567890123456789012",
        title="Fix Test Video",
        description="A test video to verify notification fix",
        published_at=datetime.utcnow(),
        thumbnail_url="https://example.com/thumb.jpg",
        duration="PT2M30S",
        view_count=100,
        like_count=5,
        comment_count=2,
        url="https://www.youtube.com/watch?v=FIXTEST1234"
    )
    
    test_channel = ChannelConfig(
        channel_id="UC1234567890123456789012",
        channel_name="Fix Test Channel",
        telegram_chat_id="987654321",
        check_interval=3600,
        is_active=True
    )
    
    print("\n1. Testing with summarization failure...")
    
    # Mock summarization to fail
    with patch('agents.summarizer_agent.summarize_video_content') as mock_summarize:
        mock_summarize.ainvoke = AsyncMock()
        mock_summarize.ainvoke.side_effect = Exception("Mocked summarization failure")
        
        # Mock the entire notification tool to avoid actual API calls
        with patch('agents.telegram_agent.notify_new_video') as mock_notify_tool:
            mock_notify_tool.ainvoke = AsyncMock()
            mock_notify_tool.ainvoke.return_value = NotificationStatus(
                video_id=test_video.video_id,
                chat_id=test_channel.telegram_chat_id,
                success=True,
                message_id=123
            )
            
            # Mock database operations to avoid foreign key constraints
            with patch('agents.youtube_tracker.youtube_tracker_agent._save_video_to_database') as mock_save:
                mock_save.return_value = None
                
                # Process the video
                print("   Processing video with summarization failure...")
                result = await youtube_tracker_agent._process_video(test_video, test_channel)
                
                # Verify the behavior
                print(f"   Summarization failed: {result.get('error') is not None}")
                print(f"   Notification attempted: {mock_notify_tool.ainvoke.called}")
                print(f"   Notification sent: {result.get('notification_sent', False)}")
                
                if mock_notify_tool.ainvoke.called:
                    call_args = mock_notify_tool.ainvoke.call_args[0][0]  # First positional argument (dict)
                    print(f"   Summary passed to notification: {call_args.get('summary')}")
                    
                    # Verify the fix is working
                    assert mock_notify_tool.ainvoke.called, "❌ Notification should be attempted even when summarization fails"
                    assert call_args.get('summary') is None, "❌ Summary should be None when summarization fails"
                    assert result.get('notification_sent', False), "❌ Result should indicate notification was sent"
                    print("   ✅ Fix verified: Notification attempted with None summary")
                else:
                    print("   ❌ Notification was not attempted")
                    return False
    
    print("\n2. Testing with successful summarization...")
    
    # Mock summarization to succeed
    with patch('agents.summarizer_agent.summarize_video_content') as mock_summarize:
        mock_summarize_result = AsyncMock()
        mock_summarize_result.summary = "Test summary"
        mock_summarize.ainvoke = AsyncMock(return_value=mock_summarize_result)
        
        # Mock the notification tool
        with patch('agents.telegram_agent.notify_new_video') as mock_notify_tool:
            mock_notify_tool.ainvoke = AsyncMock()
            mock_notify_tool.ainvoke.return_value = NotificationStatus(
                video_id=test_video.video_id,
                chat_id=test_channel.telegram_chat_id,
                success=True,
                message_id=456
            )
            
            # Mock database operations
            with patch('agents.youtube_tracker.youtube_tracker_agent._save_video_to_database') as mock_save:
                mock_save.return_value = None
                
                # Process video
                print("   Processing video with successful summarization...")
                result = await youtube_tracker_agent._process_video(test_video, test_channel)
                
                # Verify behavior
                print(f"   Summarization succeeded: {result.get('summary_generated', False)}")
                print(f"   Notification attempted: {mock_notify_tool.ainvoke.called}")
                print(f"   Notification sent: {result.get('notification_sent', False)}")
                
                if mock_notify_tool.ainvoke.called:
                    call_args = mock_notify_tool.ainvoke.call_args[0][0]
                    print(f"   Summary passed to notification: '{call_args.get('summary')}'")
                    
                    # Verify normal flow still works
                    assert mock_notify_tool.ainvoke.called, "❌ Notification should be attempted when summarization succeeds"
                    assert call_args.get('summary') == "Test summary", "❌ Summary should be passed when summarization succeeds"
                    assert result.get('notification_sent', False), "❌ Result should indicate notification was sent"
                    print("   ✅ Normal flow verified: Notification attempted with summary")
                else:
                    print("   ❌ Notification was not attempted")
                    return False
    
    print("\n" + "="*60)
    print("🎉 NOTIFICATION FIX VERIFIED!")
    print("✅ Notifications are sent even when summarization fails")
    print("✅ Normal flow still works when summarization succeeds")
    print("="*60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_notification_fix())
    if success:
        print("\n✅ All tests passed!")
        exit(0)
    else:
        print("\n❌ Tests failed!")
        exit(1)