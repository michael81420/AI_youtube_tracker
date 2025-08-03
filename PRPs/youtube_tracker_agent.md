name: "LangChain YouTube Tracking Agent System"
description: |

## Purpose
Build a comprehensive LangChain-powered YouTube channel tracking bot that monitors specified channels hourly, automatically summarizes new videos using LLM agents, and sends notifications via Telegram with persistent storage and configurable scheduling.

## Core Principles
1. **Context is King**: Include ALL necessary documentation, examples, and caveats
2. **Validation Loops**: Provide executable tests/lints the AI can run and fix
3. **Information Dense**: Use keywords and patterns from the codebase
4. **Progressive Success**: Start simple, validate, then enhance
5. **Global rules**: Be sure to follow all rules in CLAUDE.md

---

## Goal
Create a production-ready, multi-agent YouTube tracking system where users can configure channel monitoring, receive intelligent video summaries, and get notifications via Telegram. The system should be resilient, scalable, and follow LangChain best practices for agent orchestration.

## Why
- **Business value**: Automates content monitoring and summary generation for multiple YouTube channels
- **Integration**: Demonstrates advanced LangChain agent architecture with external API integrations
- **Problems solved**: Eliminates manual monitoring of YouTube content, provides intelligent summaries, and enables real-time notifications

## What
A comprehensive system featuring:
- Hourly monitoring of configured YouTube channels for new videos
- LLM-powered video content summarization
- Telegram notifications with rich formatting
- Persistent storage for tracking processed videos and channel states
- Configurable scheduling system for flexible monitoring intervals
- Multi-channel support with individual configuration per channel

### Success Criteria
- [ ] YouTube channels are monitored hourly for new videos
- [ ] New videos are automatically summarized using LLM agents
- [ ] Summaries are sent via Telegram with proper formatting
- [ ] System persists state across restarts
- [ ] All API rate limits are respected
- [ ] Comprehensive error handling and logging
- [ ] Unit tests achieve 80%+ coverage

## All Needed Context

### Documentation & References
```yaml
# MUST READ - Include these in your context window
- url: https://python.langchain.com/docs/introduction/
  why: Core LangChain architecture patterns for agent development
  
- url: https://python.langchain.com/docs/how_to/custom_tools/
  why: Custom tool creation patterns for YouTube and Telegram APIs
  
- url: https://langchain-ai.github.io/langgraph/concepts/agentic_concepts/
  why: LangGraph agent orchestration and stateful agent patterns
  
- url: https://python.langchain.com/docs/integrations/tools/youtube/
  why: Existing YouTube integration patterns in LangChain
  
- url: https://developers.google.com/youtube/v3
  why: YouTube Data API v3 endpoints for channel and video monitoring
  
- url: https://developers.google.com/youtube/v3/determine_quota_cost
  why: Critical quota management - default 10,000 units/day limit
  
- url: https://docs.python-telegram-bot.org/
  why: Async Telegram bot patterns and message formatting
  
- url: https://apscheduler.readthedocs.io/en/3.x/userguide.html
  why: Scheduling patterns with SQLAlchemy persistence
  
- url: https://docs.pydantic.dev/
  why: Pydantic v2 data validation patterns for API responses
  
- url: https://langchain-ai.github.io/langgraph/concepts/persistence/
  why: LangGraph AsyncSqliteSaver for agent workflow persistence

- file: CLAUDE.md
  why: Project-specific architecture requirements and constraints
```

### Current Codebase tree
```bash
D:\AI_youtube_tracker\
├── CLAUDE.md                     # Project instructions and conventions
├── INITIAL.md                    # Feature specification
├── LICENSE
├── README.md
├── PRPs/                         # Project Requirements Profiles
│   ├── templates/
│   │   └── prp_base.md
│   └── EXAMPLE_multi_agent_prp.md
├── examples/                     # Reference implementations (empty)
└── use-cases/                    # Other use case examples
    ├── mcp-server/              # TypeScript MCP server example
    ├── pydantic-ai/             # Pydantic AI agent examples
    └── template-generator/      # Template generation examples
```

### Desired Codebase tree with files to be added
```bash
D:\AI_youtube_tracker\
├── agents/
│   ├── __init__.py                    # Package init with agent registration
│   ├── youtube_tracker.py            # Main YouTube tracking agent with scheduling
│   ├── summarizer_agent.py           # Video summarization agent using LLM
│   ├── telegram_agent.py             # Telegram notification agent
│   └── orchestrator.py               # Master agent coordinating workflow
├── tools/
│   ├── __init__.py                    # Package init
│   ├── youtube_tools.py              # YouTube Data API v3 integration tools
│   ├── telegram_tools.py             # Telegram Bot API integration tools
│   └── summarization_tools.py        # Video content processing tools
├── chains/
│   ├── __init__.py                    # Package init
│   ├── tracking_chain.py             # Main workflow chain orchestration
│   └── notification_chain.py         # Notification delivery chain with retry
├── schedulers/
│   ├── __init__.py                    # Package init
│   └── channel_scheduler.py          # APScheduler-based hourly monitoring
├── config/
│   ├── __init__.py                    # Package init
│   └── settings.py                   # Configuration management with Pydantic
├── models/
│   ├── __init__.py                    # Package init
│   ├── channel.py                    # Channel configuration models
│   ├── video.py                      # Video metadata models
│   └── notification.py               # Notification models
├── storage/
│   ├── __init__.py                    # Package init
│   ├── database.py                   # SQLAlchemy models and connection
│   └── migrations/                   # Database schema migrations
├── tests/
│   ├── __init__.py                    # Package init
│   ├── test_agents/                  # Agent-specific tests
│   │   ├── test_youtube_tracker.py
│   │   ├── test_summarizer_agent.py
│   │   └── test_telegram_agent.py
│   ├── test_tools/                   # Tool-specific tests
│   │   ├── test_youtube_tools.py
│   │   ├── test_telegram_tools.py
│   │   └── test_summarization_tools.py
│   ├── test_chains/                  # Chain-specific tests
│   │   └── test_tracking_chain.py
│   ├── fixtures/                     # Test data fixtures
│   │   ├── youtube_responses.json
│   │   └── telegram_messages.json
│   └── conftest.py                   # Pytest configuration
├── .env.example                      # Environment variables template
├── .gitignore                        # Git ignore patterns
├── main.py                           # CLI entry point
├── requirements.txt                  # Python dependencies
└── youtube_tracker.db               # SQLite database (created at runtime)
```

### Known Gotchas & Library Quirks
```python
# CRITICAL: YouTube API quota limits are strict - 10,000 units/day default
# - channels.list: 1 unit per request
# - search.list: 100 units per request  
# - videos.list: 1 unit per request
# - MUST implement efficient caching and pagination

# CRITICAL: LangChain requires async throughout - no sync functions in async context
# - All agent methods must be async
# - Use AsyncSqliteSaver for persistence
# - Chain components must support async execution

# CRITICAL: python-telegram-bot is fully async in v20+
# - Use telegram.ext.Application for bot setup
# - All handlers must be async functions
# - Rate limiting built-in but respect Telegram limits

# CRITICAL: APScheduler with async requires careful event loop management
# - Use AsyncIOScheduler for asyncio compatibility
# - SQLAlchemy job store for persistence
# - Avoid event loop conflicts in scheduled jobs

# CRITICAL: Pydantic v2 validation patterns
# - Use Field() for validation constraints
# - BaseModel for all data structures
# - Custom validators for API response validation

# CRITICAL: Video summarization rate limits
# - OpenAI: 3 RPM default, 10,000 TPM
# - Anthropic: 5 RPM default, 25,000 TPM
# - Implement exponential backoff for LLM calls

# CRITICAL: Database constraints
# - SQLite WAL mode for concurrent access
# - Use PRAGMA foreign_keys = ON for referential integrity
# - Index on channel_id and video_id for performance
```

## Implementation Blueprint

### Data models and structure

Create the core data models to ensure type safety and consistency.
```python
# models/channel.py - Channel configuration and state
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, timedelta

class ChannelConfig(BaseModel):
    channel_id: str = Field(..., description="YouTube channel ID")
    channel_name: str = Field(..., description="Human-readable channel name")
    check_interval: int = Field(3600, ge=300, description="Check interval in seconds")
    telegram_chat_id: str = Field(..., description="Telegram chat ID for notifications")
    last_check: Optional[datetime] = None
    last_video_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    @validator('channel_id')
    def validate_channel_id(cls, v):
        if not v.startswith('UC') or len(v) != 24:
            raise ValueError('Invalid YouTube channel ID format')
        return v

# models/video.py - Video metadata and processing state
class VideoMetadata(BaseModel):
    video_id: str = Field(..., description="YouTube video ID")
    channel_id: str = Field(..., description="YouTube channel ID")
    title: str = Field(..., description="Video title")
    description: str = Field(..., description="Video description")
    published_at: datetime = Field(..., description="Video publication timestamp")
    thumbnail_url: str = Field(..., description="Video thumbnail URL")
    duration: Optional[str] = None
    view_count: Optional[int] = None
    processed_at: Optional[datetime] = None
    summary: Optional[str] = None
    notification_sent: bool = False

# models/notification.py - Notification tracking
class NotificationStatus(BaseModel):
    video_id: str
    chat_id: str
    sent_at: datetime
    message_id: Optional[int] = None
    success: bool
    error_message: Optional[str] = None
```

### List of tasks to be completed to fulfill the PRP in order

```yaml
Task 1: Setup Project Foundation
CREATE config/settings.py:
  - PATTERN: Use pydantic-settings for environment variables
  - Load all required API keys with validation
  - Define database connection settings
  - Implement logging configuration

CREATE .env.example:
  - Include all required environment variables with descriptions
  - Follow security best practices for sensitive data

Task 2: Database Schema and Models
CREATE storage/database.py:
  - PATTERN: SQLAlchemy async models with proper relationships
  - Channel table with configuration and state
  - Video table with metadata and processing status
  - Notification table for tracking delivery status
  - Use AsyncEngine with SQLite WAL mode

Task 3: YouTube Data API Integration
CREATE tools/youtube_tools.py:
  - PATTERN: LangChain @tool decorator for async functions
  - Implement channel video listing with pagination
  - Implement video metadata retrieval
  - Handle quota limits with exponential backoff
  - Return structured Pydantic models

Task 4: Video Summarization Agent
CREATE agents/summarizer_agent.py:
  - PATTERN: LangChain Agent with LLM provider abstraction
  - Use video metadata for context-aware summarization
  - Implement retry logic for LLM API failures
  - Support multiple LLM providers (OpenAI, Anthropic)

Task 5: Telegram Integration
CREATE tools/telegram_tools.py:
  - PATTERN: Async Telegram bot integration
  - Rich message formatting with video thumbnails
  - Handle Telegram API rate limits
  - Support message threading and chat management

CREATE agents/telegram_agent.py:
  - PATTERN: Agent wrapper for Telegram operations
  - Format summaries with proper markdown
  - Handle delivery failures gracefully

Task 6: YouTube Tracking Agent
CREATE agents/youtube_tracker.py:
  - PATTERN: Main agent with tool composition
  - Monitor channels for new videos
  - Coordinate with summarizer and notification agents
  - Update database state after processing

Task 7: Workflow Orchestration
CREATE chains/tracking_chain.py:
  - PATTERN: LangChain Chain for workflow orchestration
  - Sequence: Check → Summarize → Notify → Update
  - Error handling with partial success scenarios
  - State management with LangGraph persistence

Task 8: Scheduling System
CREATE schedulers/channel_scheduler.py:
  - PATTERN: APScheduler with SQLAlchemy job store
  - Per-channel scheduling based on configuration
  - Handle scheduler failures and job recovery
  - Async job execution with proper error handling

Task 9: Master Orchestrator
CREATE agents/orchestrator.py:
  - PATTERN: Master agent coordinating all workflows
  - Manage multiple channel tracking simultaneously
  - Implement circuit breaker for failing channels
  - Coordinate scheduled vs manual operations

Task 10: CLI Interface
CREATE main.py:
  - PATTERN: Async CLI with command handling
  - Support adding/removing channels
  - Manual trigger for immediate checks
  - Status reporting and log viewing

Task 11: Comprehensive Testing
CREATE tests/:
  - PATTERN: Pytest with async support and mocking
  - Mock all external APIs (YouTube, Telegram, LLM)
  - Test happy path, edge cases, and error scenarios
  - Integration tests for full workflow
  - Achieve 80%+ test coverage

Task 12: Documentation and Deployment
UPDATE README.md:
  - PATTERN: Comprehensive setup and usage documentation
  - API key configuration steps
  - Architecture overview with diagrams
  - Troubleshooting guide
```

### Per task pseudocode

```python
# Task 3: YouTube Tools
@tool
async def get_channel_videos(
    channel_id: str, 
    published_after: Optional[datetime] = None,
    max_results: int = 10
) -> List[VideoMetadata]:
    """Get recent videos from YouTube channel with quota optimization."""
    # PATTERN: Use httpx for async HTTP calls with timeout
    async with httpx.AsyncClient(timeout=30.0) as client:
        # QUOTA: channels.list costs 1 unit
        params = {
            "part": "contentDetails",
            "id": channel_id,
            "key": settings.YOUTUBE_API_KEY
        }
        
        response = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params=params
        )
        
        # CRITICAL: Handle quota exceeded errors
        if response.status_code == 403:
            quota_data = response.json()
            if "quotaExceeded" in str(quota_data):
                raise YouTubeQuotaExceededError("Daily quota limit reached")
        
        # Get upload playlist ID for video listing
        uploads_playlist = response.json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # QUOTA: playlistItems.list costs 1 unit per request
        # Use published_after to minimize API calls
        videos = await _get_playlist_videos(uploads_playlist, published_after, max_results)
        
        # PATTERN: Return structured Pydantic models
        return [VideoMetadata(**video) for video in videos]

# Task 4: Summarizer Agent  
async def create_summarizer_agent() -> Agent:
    """Create video summarization agent with LLM provider abstraction."""
    
    # PATTERN: Multi-provider LLM setup from research
    llm = ChatOpenAI(
        model="gpt-4o-mini",  # Cost-effective for summaries
        temperature=0.1,      # Consistent summaries
        max_tokens=500       # Controlled output length
    )
    
    @tool
    async def summarize_video(video: VideoMetadata) -> str:
        """Summarize YouTube video content."""
        # PATTERN: Structured prompt for consistent output
        prompt = f"""
        Summarize this YouTube video in 2-3 sentences focusing on key insights:
        
        Title: {video.title}
        Description: {video.description[:500]}...
        Channel: {video.channel_id}
        Duration: {video.duration}
        
        Provide a concise summary highlighting main topics and value.
        """
        
        # CRITICAL: Implement retry with exponential backoff
        for attempt in range(3):
            try:
                response = await llm.ainvoke(prompt)
                return response.content
            except Exception as e:
                if attempt == 2:
                    raise SummarizationError(f"Failed after 3 attempts: {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    agent = Agent(
        model=llm,
        tools=[summarize_video],
        system_prompt="You are a video content summarizer focused on extracting key insights."
    )
    
    return agent

# Task 7: Tracking Chain
async def create_tracking_chain() -> Chain:
    """Create main tracking workflow chain."""
    
    # PATTERN: Sequential chain with error handling
    def check_new_videos(inputs):
        channel_config = inputs["channel_config"]
        return youtube_tools.get_channel_videos(
            channel_config.channel_id,
            published_after=channel_config.last_check
        )
    
    def summarize_videos(inputs):
        videos = inputs["videos"]
        summaries = []
        for video in videos:
            summary = summarizer_agent.run(f"Summarize: {video.dict()}")
            summaries.append((video, summary))
        return summaries
    
    def send_notifications(inputs):
        summaries = inputs["summaries"]
        results = []
        for video, summary in summaries:
            result = telegram_agent.run({
                "video": video,
                "summary": summary,
                "chat_id": inputs["channel_config"].telegram_chat_id
            })
            results.append(result)
        return results
    
    # PATTERN: Chain composition with error boundaries
    chain = (
        check_new_videos
        | summarize_videos
        | send_notifications
    )
    
    return chain
```

### Integration Points
```yaml
ENVIRONMENT:
  - add to: .env
  - vars: |
      # YouTube Data API v3
      YOUTUBE_API_KEY=AIza...
      
      # Telegram Bot
      TELEGRAM_BOT_TOKEN=1234567890:ABC...
      TELEGRAM_CHAT_ID=-1001234567890
      
      # LLM Provider (choose one)
      OPENAI_API_KEY=sk-...
      ANTHROPIC_API_KEY=sk-ant-...
      
      # Database
      DATABASE_URL=sqlite+aiosqlite:///./youtube_tracker.db
      
      # Scheduling
      SCHEDULER_JOBSTORE_URL=sqlite:///./scheduler_jobs.db
      
      # Logging
      LOG_LEVEL=INFO
      LOG_FILE=./logs/youtube_tracker.log

DATABASE:
  - migration: "Initial schema with channels, videos, notifications tables"
  - indexes: "CREATE INDEX idx_channel_videos ON videos(channel_id, published_at)"
  
CONFIG:
  - scheduler: "AsyncIOScheduler with SQLAlchemyJobStore"
  - persistence: "LangGraph AsyncSqliteSaver for agent state"
  
DEPENDENCIES:
  - Update requirements.txt with:
    - langchain>=0.1.0
    - langchain-community>=0.0.10
    - langchain-openai>=0.0.8  # or langchain-anthropic
    - langgraph>=0.0.26
    - google-api-python-client>=2.0.0
    - python-telegram-bot>=20.0
    - apscheduler>=3.10.0
    - sqlalchemy>=2.0.0
    - aiosqlite>=0.19.0
    - pydantic>=2.5.0
    - pydantic-settings>=2.1.0
    - httpx>=0.25.0
```

## Validation Loop

### Level 1: Syntax & Style
```bash
# Run these FIRST - fix any errors before proceeding
ruff check . --fix              # Auto-fix style issues
mypy .                          # Type checking
black .                         # Code formatting

# Expected: No errors. If errors, READ and fix.
```

### Level 2: Unit Tests
```python
# tests/test_agents/test_youtube_tracker.py
@pytest.mark.asyncio
async def test_youtube_tracker_processes_new_videos():
    """Test YouTube tracker processes new videos correctly."""
    # Mock YouTube API response
    mock_videos = [
        VideoMetadata(
            video_id="test123",
            channel_id="UC123",
            title="Test Video",
            description="Test description",
            published_at=datetime.utcnow(),
            thumbnail_url="https://example.com/thumb.jpg"
        )
    ]
    
    with patch('tools.youtube_tools.get_channel_videos', return_value=mock_videos):
        tracker = create_youtube_tracker_agent()
        result = await tracker.run("Check channel UC123 for new videos")
        
        assert result.success
        assert len(result.processed_videos) == 1
        assert result.processed_videos[0].video_id == "test123"

@pytest.mark.asyncio 
async def test_youtube_quota_exceeded_handling():
    """Test graceful handling of YouTube quota exceeded."""
    with patch('tools.youtube_tools.get_channel_videos') as mock_get:
        mock_get.side_effect = YouTubeQuotaExceededError("Quota exceeded")
        
        tracker = create_youtube_tracker_agent()
        result = await tracker.run("Check channel UC123")
        
        assert not result.success
        assert "quota" in result.error_message.lower()

# tests/test_tools/test_youtube_tools.py
@pytest.mark.asyncio
async def test_get_channel_videos_respects_rate_limits():
    """Test YouTube API tool respects rate limits."""
    with patch('httpx.AsyncClient.get') as mock_get:
        # Simulate rate limit response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        mock_get.return_value = mock_response
        
        with pytest.raises(YouTubeRateLimitError):
            await get_channel_videos("UC123")

# tests/test_chains/test_tracking_chain.py
@pytest.mark.asyncio
async def test_full_tracking_workflow():
    """Test complete tracking workflow from check to notification."""
    channel_config = ChannelConfig(
        channel_id="UC123",
        channel_name="Test Channel",
        telegram_chat_id="123456"
    )
    
    with patch('tools.youtube_tools.get_channel_videos') as mock_youtube, \
         patch('agents.summarizer_agent.run') as mock_summarizer, \
         patch('tools.telegram_tools.send_message') as mock_telegram:
        
        # Setup mocks
        mock_youtube.return_value = [mock_video]
        mock_summarizer.return_value = "Test summary"
        mock_telegram.return_value = {"message_id": 123, "success": True}
        
        chain = create_tracking_chain()
        result = await chain.ainvoke({"channel_config": channel_config})
        
        assert result["success"]
        assert len(result["notifications_sent"]) == 1
```

```bash
# Run tests iteratively until passing:
pytest tests/ -v --cov=agents --cov=tools --cov=chains --cov-report=term-missing

# Expected: 80%+ coverage, all tests passing
```

### Level 3: Integration Test
```bash
# Setup test environment
export YOUTUBE_API_KEY=test_key
export TELEGRAM_BOT_TOKEN=test_token
export DATABASE_URL=sqlite+aiosqlite:///./test.db

# Test CLI functionality
python main.py add-channel UC123 "Test Channel" 123456
python main.py check-now UC123
python main.py status

# Expected interactions:
# ✅ Channel UC123 added successfully
# 🔍 Checking Test Channel for new videos...
# ✅ Found 2 new videos, summaries sent to Telegram
# 📊 Status: 1 active channel, 2 videos processed today

# Test scheduled operation (run for 5 minutes)
python main.py start-scheduler &
sleep 300
python main.py stop-scheduler

# Check logs for scheduled operations
tail -f logs/youtube_tracker.log
```

## Final Validation Checklist
- [ ] All tests pass: `pytest tests/ -v --cov-report=term-missing`
- [ ] No linting errors: `ruff check .`
- [ ] No type errors: `mypy .`
- [ ] YouTube API integration works (quota respected)
- [ ] Video summarization produces quality output
- [ ] Telegram notifications are properly formatted
- [ ] Scheduling system runs without errors
- [ ] Database persistence survives restarts
- [ ] Error cases handled gracefully (API failures, rate limits)
- [ ] Logs are informative but not verbose
- [ ] CLI provides clear feedback and status information
- [ ] .env.example has all required variables with descriptions

---

## Anti-Patterns to Avoid
- ❌ Don't hardcode API keys - use environment variables exclusively
- ❌ Don't use sync functions in async agent/chain context
- ❌ Don't ignore YouTube API quota limits - implement caching and optimization
- ❌ Don't skip error handling for external API failures
- ❌ Don't create overly long summaries - respect token limits
- ❌ Don't spam Telegram channels - implement proper rate limiting
- ❌ Don't use blocking database operations in async code
- ❌ Don't forget to handle scheduler job failures and recovery
- ❌ Don't commit sensitive configuration files or API keys

## Confidence Score: 9/10

High confidence due to:
- Comprehensive research of all required technologies and patterns
- Clear LangChain architecture following 2025 best practices
- Well-documented external APIs with established Python libraries
- Proven patterns for async scheduling and persistence
- Detailed validation gates with specific, executable commands
- Strong error handling strategy covering all failure modes

Minor uncertainty around YouTube API quota optimization strategies in production scenarios, but the foundation provides clear paths for optimization based on usage patterns.