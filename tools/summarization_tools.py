"""
Video content processing and summarization tools.
"""

import logging
from typing import Optional

from langchain_core.tools import tool

from models.video import VideoMetadata, VideoSummary
from agents.summarizer_agent import summarizer_agent

# Setup logging
logger = logging.getLogger(__name__)


@tool
async def summarize_video_content(video: VideoMetadata) -> VideoSummary:
    """
    Summarize YouTube video content using configured LLM provider.
    
    Args:
        video: VideoMetadata object containing video information
        
    Returns:
        VideoSummary object with summarization results
    """
    return await summarizer_agent.summarize_video(video)


@tool
def extract_video_keywords(video: VideoMetadata) -> list[str]:
    """
    Extract keywords from video title and description.
    
    Args:
        video: VideoMetadata object
        
    Returns:
        List of extracted keywords
    """
    import re
    from collections import Counter
    
    # Combine title and description
    text = f"{video.title} {video.description or ''}"
    
    # Basic keyword extraction (can be enhanced with NLP libraries)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Filter out common stop words
    stop_words = {
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'this', 'that', 'these', 'those', 'you', 'your', 'we',
        'our', 'they', 'their', 'how', 'what', 'when', 'where', 'why', 'who',
        'will', 'can', 'should', 'would', 'could', 'may', 'might', 'must',
        'video', 'youtube', 'channel', 'subscribe', 'like', 'comment', 'share'
    }
    
    filtered_words = [word for word in words if word not in stop_words]
    
    # Get most common words as keywords
    word_counts = Counter(filtered_words)
    keywords = [word for word, count in word_counts.most_common(10)]
    
    return keywords


@tool
def categorize_video_content(video: VideoMetadata) -> str:
    """
    Categorize video content based on title and description.
    
    Args:
        video: VideoMetadata object
        
    Returns:
        Content category string
    """
    title_lower = video.title.lower()
    description_lower = (video.description or '').lower()
    
    # Define category keywords
    categories = {
        'tutorial': ['tutorial', 'how to', 'guide', 'step by step', 'learn', 'teach'],
        'review': ['review', 'unboxing', 'first look', 'hands on', 'comparison'],
        'news': ['news', 'update', 'announcement', 'breaking', 'report'],
        'entertainment': ['funny', 'comedy', 'meme', 'entertainment', 'fun'],
        'tech': ['technology', 'software', 'hardware', 'programming', 'coding'],
        'education': ['education', 'explanation', 'science', 'math', 'history'],
        'gaming': ['gaming', 'gameplay', 'game', 'player', 'stream'],
        'music': ['music', 'song', 'album', 'artist', 'concert', 'performance'],
        'lifestyle': ['lifestyle', 'vlog', 'daily', 'routine', 'personal']
    }
    
    text = f"{title_lower} {description_lower}"
    
    # Count category matches
    category_scores = {}
    for category, keywords in categories.items():
        score = sum(text.count(keyword) for keyword in keywords)
        if score > 0:
            category_scores[category] = score
    
    # Return category with highest score, or 'general' if no matches
    if category_scores:
        return max(category_scores, key=category_scores.get)
    else:
        return 'general'


@tool
def estimate_reading_time(summary: str) -> int:
    """
    Estimate reading time for summary in seconds.
    
    Args:
        summary: Summary text
        
    Returns:
        Estimated reading time in seconds
    """
    # Average reading speed: 200-250 words per minute
    words = len(summary.split())
    reading_time_minutes = words / 225  # Use 225 WPM as average
    reading_time_seconds = int(reading_time_minutes * 60)
    
    # Minimum 5 seconds, maximum 60 seconds for summaries
    return max(5, min(60, reading_time_seconds))


@tool 
def validate_summary_quality(summary: str, video: VideoMetadata) -> dict:
    """
    Validate summary quality and provide metrics.
    
    Args:
        summary: Generated summary
        video: Original video metadata
        
    Returns:
        Dictionary with quality metrics
    """
    metrics = {
        'length_appropriate': 50 <= len(summary) <= 300,
        'mentions_title_elements': False,
        'has_actionable_info': False,
        'reading_time_seconds': estimate_reading_time(summary),
        'word_count': len(summary.split()),
        'character_count': len(summary)
    }
    
    # Check if summary mentions key elements from title
    title_words = set(video.title.lower().split())
    summary_words = set(summary.lower().split())
    common_words = title_words.intersection(summary_words)
    metrics['mentions_title_elements'] = len(common_words) >= 2
    
    # Check for actionable information keywords
    actionable_keywords = ['learn', 'discover', 'find out', 'understand', 'explore', 'see how']
    metrics['has_actionable_info'] = any(keyword in summary.lower() for keyword in actionable_keywords)
    
    # Overall quality score
    quality_score = sum([
        metrics['length_appropriate'],
        metrics['mentions_title_elements'], 
        metrics['has_actionable_info']
    ]) / 3
    
    metrics['quality_score'] = quality_score
    
    return metrics