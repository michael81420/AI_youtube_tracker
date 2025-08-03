### 🔄 Project Awareness & Context
- **Always read `PLANNING.md`** at the start of a new conversation to understand the project's architecture, goals, style, and constraints.
- **Check `TASK.md`** before starting a new task. If the task isn't listed, add it with a brief description and today's date.
- **Use consistent naming conventions, file structure, and architecture patterns** as described in `PLANNING.md`.
- **Use venv** (the virtual environment) whenever executing Python commands, including for unit tests.

### 🤖 LangChain Agent Architecture
- **Use LangChain for agent orchestration** - leverage chains, tools, and memory for the YouTube tracking agent.
- **Implement modular agent design**:
  - `youtube_tracker.py` - Main YouTube tracking agent with scheduling logic
  - `summarizer_agent.py` - Video summarization agent using LLM
  - `telegram_agent.py` - Telegram notification agent
  - `tools.py` - Custom tools for YouTube API, video processing, and Telegram API
  - `chains.py` - LangChain chains for orchestrating the workflow
- **Use LangGraph for complex agent workflows** with streaming and human-in-the-loop support.
- **Implement proper agent memory** for tracking processed videos and channel states.

### 🧱 Code Structure & Modularity
- **Never create a file longer than 500 lines of code.** If a file approaches this limit, refactor by splitting it into modules or helper files.
- **Organize code into clearly separated modules**, grouped by feature or responsibility.
  For the YouTube tracker this looks like:
    - `agents/` - All agent definitions and execution logic
    - `tools/` - LangChain tool functions (YouTube API, Telegram API, video processing)
    - `chains/` - LangChain chain definitions for workflow orchestration
    - `schedulers/` - Cron-like scheduling logic for hourly checks
    - `config/` - Configuration management and environment variables
    - `models/` - Pydantic models for data validation
- **Use clear, consistent imports** (prefer relative imports within packages).
- **Use python_dotenv and load_dotenv()** for environment variables.

### 🎥 YouTube Integration
- **Use YouTube Data API v3** for channel monitoring and video metadata retrieval.
- **Implement efficient polling strategy** - store last check timestamps to avoid redundant API calls.
- **Handle API rate limits** with proper retry logic and exponential backoff.
- **Store channel configurations** in a structured format (JSON/database) for easy management.
- **Prohibit sending duplicate videos to users**

### 📱 Telegram Integration
- **Use python-telegram-bot library** for Telegram API integration.
- **Implement async message sending** to handle multiple notifications efficiently.
- **Support rich message formatting** with video thumbnails, titles, and summaries.
- **Handle Telegram API errors gracefully** with retry mechanisms.

### ⏰ Scheduling & Persistence
- **Use APScheduler or similar** for hourly channel monitoring.
- **Implement persistent storage** for tracking processed videos (SQLite/PostgreSQL).
- **Store agent states and memory** to survive application restarts.
- **Log all operations** for monitoring and debugging.

### 🧪 Testing & Reliability
- **Always create Pytest unit tests for new features** (agents, tools, chains, schedulers).
- **After updating any logic**, check whether existing unit tests need to be updated. If so, do it.
- **Tests should live in a `/tests` folder** mirroring the main app structure.
  - Include at least:
    - 1 test for expected use (successful video tracking and notification)
    - 1 edge case (API failures, network issues)
    - 1 failure case (invalid configurations, missing credentials)
- **Mock external APIs** (YouTube, Telegram) in tests to ensure reliability.

### ✅ Task Completion
- **Mark completed tasks in `TASK.md`** immediately after finishing them.
- Add new sub-tasks or TODOs discovered during development to `TASK.md` under a "Discovered During Work" section.

### 📎 Style & Conventions
- **Use Python 3.9+** as the primary language.
- **Follow PEP8**, use type hints, and format with `black`.
- **Use `pydantic` for data validation** - especially for API responses and configuration models.
- **Use `asyncio` for asynchronous operations** when dealing with multiple channels or API calls.
- Write **docstrings for every function** using the Google style:
  ```python
  def example():
      """
      Brief summary.

      Args:
          param1 (type): Description.

      Returns:
          type: Description.
      """
  ```

### 🔒 Security & Configuration
- **Never commit API keys or tokens** - use environment variables exclusively.
- **Validate all external inputs** using Pydantic models.
- **Implement proper error handling** for all external API calls.
- **Use secure storage** for sensitive data like channel configurations.

### 📚 Documentation & Explainability
- **Update `README.md`** when new features are added, dependencies change, or setup steps are modified.
- **Comment non-obvious code** especially LangChain chain configurations and agent logic.
- When writing complex workflows, **add an inline `# Reason:` comment** explaining the why, not just the what.
- **Document all required environment variables** and their purposes.

### 🧠 AI Behavior Rules
- **Never assume missing context. Ask questions if uncertain.**
- **Never hallucinate libraries or functions** – only use known, verified Python packages compatible with LangChain.
- **Always confirm API endpoints and authentication methods** exist before referencing them in code.
- **Never delete or overwrite existing code** unless explicitly instructed to or if part of a task from `TASK.md`.
- **Test LangChain integrations thoroughly** as agent behaviors can be unpredictable.