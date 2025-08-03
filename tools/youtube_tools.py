"""
YouTube Data API v3 integration tools with quota optimization.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import httpx
from langchain_core.tools import tool

from config.settings import get_settings
from models.video import VideoMetadata

# Setup logging
logger = logging.getLogger(__name__)

# Custom exceptions
class YouTubeAPIError(Exception):
    """Base YouTube API error."""
    pass

class YouTubeQuotaExceededError(YouTubeAPIError):
    """YouTube API quota exceeded."""
    pass

class YouTubeRateLimitError(YouTubeAPIError):
    """YouTube API rate limit exceeded."""
    pass

class YouTubeChannelNotFoundError(YouTubeAPIError):
    """YouTube channel not found."""
    pass


class YouTubeAPIClient:
    """Async YouTube Data API v3 client with quota management."""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.quota_used_today = 0
        self.last_request_time = None
        self.request_count = 0
        
    async def _make_request(
        self, 
        endpoint: str, 
        params: Dict[str, Any],
        quota_cost: int = 1
    ) -> Dict[str, Any]:
        """Make authenticated request to YouTube API with rate limiting."""
        
        # Add API key to params
        params["key"] = self.settings.youtube_api_key
        
        # Rate limiting: max 50 requests per minute (configurable)
        if self.last_request_time:
            time_since_last = datetime.utcnow() - self.last_request_time
            if time_since_last < timedelta(seconds=60 / self.settings.youtube_requests_per_minute):
                sleep_time = (60 / self.settings.youtube_requests_per_minute) - time_since_last.total_seconds()
                await asyncio.sleep(sleep_time)
        
        self.last_request_time = datetime.utcnow()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(f"{self.base_url}/{endpoint}", params=params)
                
                # Handle different HTTP status codes
                if response.status_code == 200:
                    self.quota_used_today += quota_cost
                    self.request_count += 1
                    return response.json()
                
                elif response.status_code == 403:
                    error_data = response.json()
                    error_reason = error_data.get("error", {}).get("errors", [{}])[0].get("reason", "")
                    
                    if "quotaExceeded" in error_reason:
                        logger.error(f"YouTube API quota exceeded. Used today: {self.quota_used_today}")
                        raise YouTubeQuotaExceededError("Daily quota limit reached (10,000 units)")
                    elif "rateLimitExceeded" in error_reason:
                        logger.warning("YouTube API rate limit exceeded, retrying...")
                        await asyncio.sleep(5)  # Wait 5 seconds and retry
                        return await self._make_request(endpoint, params, quota_cost)
                    else:
                        raise YouTubeAPIError(f"API access forbidden: {error_reason}")
                
                elif response.status_code == 404:
                    raise YouTubeChannelNotFoundError("Channel or video not found")
                
                elif response.status_code == 429:
                    logger.warning("Too many requests, implementing exponential backoff...")
                    await asyncio.sleep(2 ** min(5, self.request_count // 10))  # Exponential backoff
                    return await self._make_request(endpoint, params, quota_cost)
                
                else:
                    response.raise_for_status()
                    
            except httpx.RequestError as e:
                logger.error(f"HTTP request failed: {e}")
                raise YouTubeAPIError(f"Request failed: {e}")
    
    async def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get channel information."""
        params = {
            "part": "snippet,contentDetails,statistics",
            "id": channel_id
        }
        
        response = await self._make_request("channels", params, quota_cost=1)
        
        if not response.get("items"):
            raise YouTubeChannelNotFoundError(f"Channel {channel_id} not found")
        
        return response["items"][0]
    
    async def get_uploads_playlist_id(self, channel_id: str) -> str:
        """Get the uploads playlist ID for a channel."""
        channel_info = await self.get_channel_info(channel_id)
        uploads_playlist = channel_info["contentDetails"]["relatedPlaylists"]["uploads"]
        return uploads_playlist
    
    async def get_playlist_videos(
        self, 
        playlist_id: str, 
        published_after: Optional[datetime] = None,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Get videos from a playlist with optional date filtering."""
        
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(max_results, 50),  # YouTube API limit
            "order": "date"
        }
        
        if published_after:
            params["publishedAfter"] = published_after.isoformat() + "Z"
        
        response = await self._make_request("playlistItems", params, quota_cost=1)
        
        videos = []
        for item in response.get("items", []):
            video_data = {
                "video_id": item["snippet"]["resourceId"]["videoId"],
                "channel_id": item["snippet"]["channelId"],
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "published_at": datetime.fromisoformat(
                    item["snippet"]["publishedAt"].replace("Z", "+00:00")
                ),
                "thumbnail_url": item["snippet"]["thumbnails"]["high"]["url"]
            }
            videos.append(video_data)
        
        return videos
    
    async def get_video_details(self, video_ids: List[str]) -> List[Dict[str, Any]]:
        """Get detailed information for specific videos."""
        
        # YouTube API allows up to 50 video IDs per request
        video_chunks = [video_ids[i:i+50] for i in range(0, len(video_ids), 50)]
        all_videos = []
        
        for chunk in video_chunks:
            params = {
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(chunk)
            }
            
            response = await self._make_request("videos", params, quota_cost=1)
            
            for item in response.get("items", []):
                video_data = {
                    "video_id": item["id"],
                    "channel_id": item["snippet"]["channelId"],
                    "title": item["snippet"]["title"],
                    "description": item["snippet"]["description"],
                    "published_at": datetime.fromisoformat(
                        item["snippet"]["publishedAt"].replace("Z", "+00:00")
                    ),
                    "thumbnail_url": item["snippet"]["thumbnails"]["high"]["url"],
                    "duration": item["contentDetails"]["duration"],
                    "view_count": int(item["statistics"].get("viewCount", 0)),
                    "like_count": int(item["statistics"].get("likeCount", 0)),
                    "comment_count": int(item["statistics"].get("commentCount", 0))
                }
                all_videos.append(video_data)
        
        return all_videos


# Global client instance
youtube_client = YouTubeAPIClient()


# LangChain tools
@tool
async def get_channel_videos(
    channel_id: str, 
    published_after: Optional[datetime] = None,
    max_results: int = 1
) -> List[VideoMetadata]:
    """
    Get recent videos from YouTube channel with quota optimization.
    
    Args:
        channel_id: YouTube channel ID (starts with UC)
        published_after: Only get videos published after this date
        max_results: Maximum number of videos to return (default 1)
    
    Returns:
        List of VideoMetadata objects
    """
    try:
        logger.info(f"Fetching videos for channel {channel_id}, max_results={max_results}")
        
        # Get uploads playlist ID
        uploads_playlist = await youtube_client.get_uploads_playlist_id(channel_id)
        
        # Get videos from playlist
        videos_data = await youtube_client.get_playlist_videos(
            uploads_playlist, 
            published_after, 
            max_results
        )
        
        # Get detailed information for videos
        if videos_data:
            video_ids = [v["video_id"] for v in videos_data]
            detailed_videos = await youtube_client.get_video_details(video_ids)
            
            # Convert to VideoMetadata objects
            videos = []
            for video_data in detailed_videos:
                try:
                    video = VideoMetadata(**video_data)
                    videos.append(video)
                except Exception as e:
                    logger.warning(f"Failed to create VideoMetadata for {video_data.get('video_id')}: {e}")
            
            logger.info(f"Successfully fetched {len(videos)} videos for channel {channel_id}")
            return videos
        
        logger.info(f"No videos found for channel {channel_id}")
        return []
        
    except YouTubeQuotaExceededError:
        logger.error("YouTube API quota exceeded")
        raise
    except YouTubeChannelNotFoundError:
        logger.error(f"Channel {channel_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error fetching videos for channel {channel_id}: {e}")
        raise YouTubeAPIError(f"Failed to fetch videos: {e}")


@tool
async def get_video_metadata(video_id: str) -> VideoMetadata:
    """
    Get metadata for a specific YouTube video.
    
    Args:
        video_id: YouTube video ID
    
    Returns:
        VideoMetadata object
    """
    try:
        logger.info(f"Fetching metadata for video {video_id}")
        
        videos_data = await youtube_client.get_video_details([video_id])
        
        if not videos_data:
            raise YouTubeAPIError(f"Video {video_id} not found")
        
        video_data = videos_data[0]
        video = VideoMetadata(**video_data)
        
        logger.info(f"Successfully fetched metadata for video {video_id}")
        return video
        
    except Exception as e:
        logger.error(f"Error fetching metadata for video {video_id}: {e}")
        raise YouTubeAPIError(f"Failed to fetch video metadata: {e}")


@tool
async def validate_channel_id(channel_id: str) -> bool:
    """
    Validate that a YouTube channel ID exists.
    
    Args:
        channel_id: YouTube channel ID to validate
    
    Returns:
        True if channel exists, False otherwise
    """
    try:
        await youtube_client.get_channel_info(channel_id)
        return True
    except YouTubeChannelNotFoundError:
        return False
    except Exception as e:
        logger.warning(f"Error validating channel {channel_id}: {e}")
        return False


def get_quota_usage() -> Dict[str, int]:
    """Get current quota usage statistics."""
    return {
        "quota_used_today": youtube_client.quota_used_today,
        "requests_made": youtube_client.request_count,
        "quota_remaining": 10000 - youtube_client.quota_used_today
    }