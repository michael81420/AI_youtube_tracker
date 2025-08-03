## FEATURE:

- LangChain-powered YouTube channel tracking bot that monitors specified channels hourly
- Automatic video summarization using LLM agents when new videos are detected
- Telegram integration for sending video summaries to specified chat rooms
- Persistent storage for tracking processed videos and channel states
- Configurable scheduling system for flexible monitoring intervals
- Multi-channel support with individual configuration per channel

## EXAMPLES:

In the `examples/` folder, you will find reference implementations to guide development:

- `examples/youtube_tracker/` - Complete YouTube tracking agent implementation
  - `main_tracker.py` - Primary tracking agent with LangChain integration
  - `summarizer_agent.py` - Video content summarization agent
  - `telegram_notifier.py` - Telegram message sender with rich formatting
  - `scheduler.py` - Hourly monitoring scheduler implementation

- `examples/tools/` - Custom LangChain tools for external integrations
  - `youtube_tools.py` - YouTube Data API v3 integration tools
  - `telegram_tools.py` - Telegram Bot API integration tools
  - `summarization_tools.py` - Video content processing and summarization tools

- `examples/chains/` - LangChain chain configurations
  - `tracking_chain.py` - Main workflow chain orchestrating the tracking process
  - `notification_chain.py` - Notification delivery chain with error handling

Don't copy these examples directly - they serve as templates and best practice references for your specific implementation.

## DOCUMENTATION:

Core dependencies and references:
- LangChain documentation: https://python.langchain.com/docs/introduction/
- YouTube Data API v3: https://developers.google.com/youtube/v3
- Python Telegram Bot: https://python-telegram-bot.readthedocs.io/
- APScheduler: https://apscheduler.readthedocs.io/
- Pydantic: https://docs.pydantic.dev/

## OTHER CONSIDERATIONS:

### Environment Setup
- Include a `.env.example` with all required environment variables:
  - `YOUTUBE_API_KEY` - YouTube Data API v3 key
  - `TELEGRAM_BOT_TOKEN` - Telegram bot token
  - `TELEGRAM_CHAT_ID` - Target chat room ID
  - `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - For video summarization
  - `DATABASE_URL` - For persistent storage (SQLite by default)

### Project Structure
- Organize code following the modular architecture specified in `CLAUDE.md`
- Use `agents/` for all LangChain agent definitions
- Use `tools/` for custom LangChain tools
- Use `chains/` for workflow orchestration
- Use `models/` for Pydantic data models
- Use `config/` for configuration management

### Key Implementation Notes
- **Rate Limiting**: Implement proper rate limiting for YouTube API (quota: 10,000 units/day)
- **Error Handling**: Robust error handling for network failures, API errors, and agent failures
- **Logging**: Comprehensive logging for monitoring and debugging
- **Database Schema**: Design efficient schema for tracking channels, videos, and processing states
- **Async Operations**: Use asyncio for concurrent channel monitoring and notification sending
- **Memory Management**: Implement LangChain memory for agent context and conversation history

### Required Dependencies
Virtual environment should include:
```
langchain
langchain-community
langchain-openai  # or langchain-anthropic
google-api-python-client
python-telegram-bot
apscheduler
pydantic
sqlalchemy
aiosqlite
python-dotenv
pytest
black
```

### Security Considerations
- Never log API keys or sensitive tokens
- Validate all external inputs using Pydantic models
- Implement secure credential storage
- Use environment variables for all configuration
- Rate limit Telegram notifications to avoid spam

### Testing Strategy
- Mock all external APIs (YouTube, Telegram, LLM providers)
- Test agent workflows end-to-end with simulated data
- Include integration tests for database operations
- Test scheduling and error recovery scenarios