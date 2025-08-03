"""
Video summarization agent using LLM providers with retry logic.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from config.settings import get_settings
from models.video import VideoMetadata, VideoSummary
from utils import safe_log_text

# Setup logging
logger = logging.getLogger(__name__)

# Custom exceptions
class SummarizationError(Exception):
    """Base summarization error."""
    pass

class LLMProviderError(SummarizationError):
    """LLM provider error."""
    pass

class RateLimitError(SummarizationError):
    """Rate limit exceeded error."""
    pass


class SummarizerAgent:
    """Agent for summarizing YouTube video content using LLM providers."""
    
    def __init__(self):
        self.settings = get_settings()
        self.llm = self._initialize_llm()
        self.request_count = 0
        self.last_request_time = None
    
    def _initialize_llm(self):
        """Initialize LLM based on provider setting."""
        try:
            if self.settings.llm_provider == "openai":
                if not self.settings.openai_api_key:
                    raise ValueError("OpenAI API key not provided")
                
                return ChatOpenAI(
                    api_key=self.settings.openai_api_key,
                    model=self.settings.llm_model,
                    temperature=0.1,  # Consistent summaries
                    max_tokens=500,   # Controlled output length
                    timeout=30.0
                )
            
            elif self.settings.llm_provider == "anthropic":
                # Import here to avoid dependency issues if not using Anthropic
                try:
                    from langchain_anthropic import ChatAnthropic
                except ImportError:
                    raise ImportError("langchain-anthropic not installed. Run: pip install langchain-anthropic")
                
                if not self.settings.anthropic_api_key:
                    raise ValueError("Anthropic API key not provided")
                
                return ChatAnthropic(
                    api_key=self.settings.anthropic_api_key,
                    model="claude-3-haiku-20240307",  # Fast and cost-effective
                    temperature=0.1,
                    max_tokens=500,
                    timeout=30.0
                )
            
            elif self.settings.llm_provider == "gemini":
                # Import here to avoid dependency issues if not using Gemini
                try:
                    from langchain_google_genai import ChatGoogleGenerativeAI
                except ImportError:
                    raise ImportError("langchain-google-genai not installed. Run: pip install langchain-google-genai")
                
                if not self.settings.gemini_api_key:
                    raise ValueError("Gemini API key not provided")
                
                return ChatGoogleGenerativeAI(
                    google_api_key=self.settings.gemini_api_key,
                    model="gemini-2.5-pro",  # Use flash model for better quota efficiency
                    temperature=0,
                    max_tokens=None,
                    timeout=None,
                    max_retries=2,
                )
            
            else:
                raise ValueError(f"Unsupported LLM provider: {self.settings.llm_provider}")
                
        except Exception as e:
            logger.error(f"Failed to initialize LLM provider {self.settings.llm_provider}: {e}")
            raise LLMProviderError(f"LLM initialization failed: {e}")
    
    async def _rate_limit_check(self):
        """Check and enforce rate limits."""
        current_time = datetime.utcnow()
        
        if self.last_request_time:
            time_since_last = (current_time - self.last_request_time).total_seconds()
            min_interval = 60 / self.settings.llm_requests_per_minute
            
            if time_since_last < min_interval:
                sleep_time = min_interval - time_since_last
                logger.info(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
                await asyncio.sleep(sleep_time)
        
        self.last_request_time = current_time
        self.request_count += 1
    
    def _create_video_url_messages(self, video: VideoMetadata) -> list:
        """Create messages for video URL analysis using Gemini multimodal capabilities."""
        
        # Calculate duration in human-readable format
        duration_text = "Unknown duration"
        if video.duration_seconds:
            minutes = video.duration_seconds // 60
            seconds = video.duration_seconds % 60
            duration_text = f"{minutes}:{seconds:02d}"
        
        # Create YouTube URL
        video_url = f"https://www.youtube.com/watch?v={video.video_id}"
        
        messages = [
            SystemMessage(
                content="You are a professional content analyst specializing in YouTube video summarization."
            ),
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": f"""請分析以下YouTube影片並提供完整的中文總結：

影片標題：{video.title}
影片時長：{duration_text}
發布日期：{video.published_at.strftime('%Y-%m-%d')}
影片連結：{video_url}

要求：
- 提供3-5句的影片內容總結，重點關注主要論點和核心價值
- 如果有重要的時間點或關鍵信息，請標注時間戳記
- 專注於教育性或信息性內容
- 使用吸引人但專業的語調
- 總結長度控制在500字以內

請直接提供中文總結："""
                    },
                    {
                        "type": "media",
                        "mime_type": "video/mp4",
                        "file_uri": video_url
                    }
                ]
            )
        ]
        
        return messages
    
    def _create_fallback_prompt(self, video: VideoMetadata) -> str:
        """Create fallback text-based prompt when video analysis fails."""
        
        # Calculate duration in human-readable format
        duration_text = "Unknown duration"
        if video.duration_seconds:
            minutes = video.duration_seconds // 60
            seconds = video.duration_seconds % 60
            duration_text = f"{minutes}:{seconds:02d}"
        
        # Truncate description if too long
        description = video.description[:800] if video.description else "No description available"
        if len(video.description or "") > 800:
            description += "..."
        
        prompt = f"""Summarize this YouTube video in 2-3 sentences focusing on key insights and main value:

Title: {video.title}
Duration: {duration_text}
Description: {description}
Published: {video.published_at.strftime('%Y-%m-%d')}

Requirements:
- Provide a concise summary highlighting main topics and key takeaways
- Focus on educational or informational value if present
- Keep response under 500 characters for notifications
- Write in an engaging, informative style
- Do not include promotional language

Summary:"""
        
        return prompt
    
    async def summarize_video(self, video: VideoMetadata) -> VideoSummary:
        """
        Summarize a YouTube video using LLM.
        
        Args:
            video: VideoMetadata object containing video information
            
        Returns:
            VideoSummary object with summarization results
        """
        start_time = datetime.utcnow()
        
        try:
            # Use ASCII-safe logging to avoid encoding issues
            logger.info(f"Starting summarization for video {video.video_id}: {safe_log_text(video.title)}")
            
            # Check rate limits
            await self._rate_limit_check()
            
            # Try video URL analysis first (for Gemini), then fallback to text-based
            summary_text = None
            method_used = "text_based"  # Default
            
            if self.settings.llm_provider == "gemini":
                try:
                    logger.info(f"Attempting video URL analysis for {video.video_id}")
                    summary_text = await self._summarize_with_video_url(video)
                    logger.info(f"Successfully analyzed video content for {video.video_id}")
                    method_used = "video_url_analysis"
                except Exception as e:
                    logger.warning(f"Video URL analysis failed for {video.video_id}: {e}")
                    logger.info("Falling back to text-based summarization")
            
            # Fallback to text-based summarization if video analysis failed or not Gemini
            if summary_text is None:
                prompt = self._create_fallback_prompt(video)
                summary_text = await self._summarize_with_text_fallback(prompt)
                method_used = "text_based"
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Create VideoSummary object
            summary = VideoSummary(
                video_id=video.video_id,
                summary=summary_text,
                summary_length=len(summary_text),
                model_used=f"{self.settings.llm_provider}-{method_used}",
                processing_time_seconds=processing_time
            )
            
            logger.info(f"Successfully summarized video {video.video_id} in {processing_time:.2f}s")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to summarize video {video.video_id}: {e}")
            raise SummarizationError(f"Summarization failed: {e}")
    
    async def _summarize_with_video_url(self, video: VideoMetadata, max_retries: int = 2) -> str:
        """
        Perform video URL-based summarization with Gemini multimodal capabilities.
        
        Args:
            video: VideoMetadata object containing video information
            max_retries: Maximum number of retry attempts
            
        Returns:
            Summary text
        """
        # Only use video URL analysis for Gemini
        if self.settings.llm_provider != "gemini":
            raise SummarizationError("Video URL analysis only supported with Gemini provider")
        
        for attempt in range(max_retries):
            try:
                # Create multimodal messages with video URL
                messages = self._create_video_url_messages(video)
                
                # Invoke LLM with video content
                response = await self.llm.ainvoke(messages)
                
                # Extract and validate response
                summary_text = response.content.strip()
                
                if not summary_text:
                    raise SummarizationError("Empty response from LLM")
                
                # Quality checks
                if len(summary_text) < 50:
                    logger.warning(f"Video summary too short ({len(summary_text)} chars), may be low quality")
                
                if len(summary_text) > 2000:
                    logger.warning(f"Video summary too long ({len(summary_text)} chars), truncating")
                    summary_text = summary_text[:1997] + "..."
                
                return summary_text
                
            except Exception as e:
                attempt_num = attempt + 1
                logger.warning(f"Video URL summarization attempt {attempt_num}/{max_retries} failed: {e}")
                
                if attempt_num == max_retries:
                    raise SummarizationError(f"Video URL analysis failed after {max_retries} attempts: {e}")
                
                # Exponential backoff
                delay = 2 ** attempt
                logger.info(f"Retrying video analysis in {delay} seconds...")
                await asyncio.sleep(delay)
        
        raise SummarizationError("Unexpected end of video URL retry loop")
    
    async def _summarize_with_text_fallback(self, prompt: str, max_retries: int = 3) -> str:
        """
        Perform summarization with exponential backoff retry logic.
        
        Args:
            prompt: Formatted prompt for summarization
            max_retries: Maximum number of retry attempts
            
        Returns:
            Summary text
        """
        for attempt in range(max_retries):
            try:
                # Create message and invoke LLM
                message = HumanMessage(content=prompt)
                response = await self.llm.ainvoke([message])
                
                # Extract and validate response
                summary_text = response.content.strip()
                
                if not summary_text:
                    raise SummarizationError("Empty response from LLM")
                
                # Basic quality checks
                if len(summary_text) < 20:
                    logger.warning(f"Summary too short ({len(summary_text)} chars), may be low quality")
                
                if len(summary_text) > 500:
                    logger.warning(f"Summary too long ({len(summary_text)} chars), truncating")
                    summary_text = summary_text[:497] + "..."
                
                return summary_text
                
            except Exception as e:
                attempt_num = attempt + 1
                logger.warning(f"Summarization attempt {attempt_num}/{max_retries} failed: {e}")
                
                if attempt_num == max_retries:
                    raise SummarizationError(f"Failed after {max_retries} attempts: {e}")
                
                # Exponential backoff with jitter
                base_delay = 2 ** attempt
                jitter = 0.1 * base_delay  # 10% jitter
                delay = base_delay + jitter
                
                logger.info(f"Retrying in {delay:.2f} seconds...")
                await asyncio.sleep(delay)
        
        raise SummarizationError("Unexpected end of retry loop")


# Global summarizer instance
summarizer_agent = SummarizerAgent()


@tool
async def summarize_video_content(video: VideoMetadata) -> VideoSummary:
    """
    Summarize YouTube video content using LLM.
    
    Args:
        video: VideoMetadata object containing video information
        
    Returns:
        VideoSummary object with summarization results
    """
    return await summarizer_agent.summarize_video(video)


@tool 
async def batch_summarize_videos(videos: list[VideoMetadata]) -> list[VideoSummary]:
    """
    Summarize multiple videos with rate limiting.
    
    Args:
        videos: List of VideoMetadata objects
        
    Returns:
        List of VideoSummary objects
    """
    summaries = []
    
    for i, video in enumerate(videos):
        try:
            logger.info(f"Processing video {i+1}/{len(videos)}: {video.video_id}")
            summary = await summarizer_agent.summarize_video(video)
            summaries.append(summary)
            
        except Exception as e:
            logger.error(f"Failed to summarize video {video.video_id}: {e}")
            # Continue with other videos even if one fails
            continue
    
    logger.info(f"Successfully summarized {len(summaries)}/{len(videos)} videos")
    return summaries


def get_summarizer_stats() -> dict:
    """Get summarizer statistics."""
    return {
        "provider": summarizer_agent.settings.llm_provider,
        "model": summarizer_agent.settings.llm_model,
        "requests_made": summarizer_agent.request_count,
        "rate_limit_per_minute": summarizer_agent.settings.llm_requests_per_minute
    }