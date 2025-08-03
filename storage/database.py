"""
Database models and connection management using SQLAlchemy async.
"""

import asyncio
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, 
    create_engine, event, Index
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.pool import StaticPool

from config.settings import get_settings

Base = declarative_base()


class Channel(Base):
    """Channel table for storing YouTube channel configurations."""
    
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String(24), unique=True, index=True, nullable=False)
    channel_name = Column(String(255), nullable=False)
    check_interval = Column(Integer, default=3600, nullable=False)
    telegram_chat_id = Column(String(50), nullable=False)
    last_check = Column(DateTime, nullable=True)
    last_video_id = Column(String(11), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    videos = relationship("Video", back_populates="channel", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="channel", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Channel(channel_id={self.channel_id}, name={self.channel_name})>"


class Video(Base):
    """Video table for storing YouTube video metadata and processing state."""
    
    __tablename__ = "videos"
    
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(String(11), unique=True, index=True, nullable=False)
    channel_id = Column(String(24), ForeignKey("channels.channel_id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=False)
    thumbnail_url = Column(String(500), nullable=False)
    duration = Column(String(20), nullable=True)  # ISO 8601 format
    view_count = Column(Integer, nullable=True)
    like_count = Column(Integer, nullable=True)
    comment_count = Column(Integer, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=True)
    notification_sent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    channel = relationship("Channel", back_populates="videos")
    notifications = relationship("Notification", back_populates="video", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Video(video_id={self.video_id}, title={self.title[:50]})>"


class Notification(Base):
    """Notification table for tracking message delivery status."""
    
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(String(11), ForeignKey("videos.video_id"), nullable=False)
    channel_id = Column(String(24), ForeignKey("channels.channel_id"), nullable=False)
    chat_id = Column(String(50), nullable=False)
    notification_type = Column(String(50), default="new_video", nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    message_id = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    
    # Relationships
    video = relationship("Video", back_populates="notifications")
    channel = relationship("Channel", back_populates="notifications")
    
    def __repr__(self):
        return f"<Notification(video_id={self.video_id}, success={self.success})>"


# Indexes for performance
Index('idx_channel_videos', Video.channel_id, Video.published_at)
Index('idx_video_processing', Video.processed_at, Video.notification_sent)
Index('idx_notification_status', Notification.sent_at, Notification.success)
Index('idx_channel_active', Channel.is_active, Channel.last_check)


# Database configuration and connection management
class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self):
        self.settings = get_settings()
        self.engine = None
        self.async_session_factory = None
        
    async def init_database(self) -> None:
        """Initialize database connection and create tables."""
        # Create async engine
        self.engine = create_async_engine(
            self.settings.database_url,
            echo=self.settings.environment == "development",
            poolclass=StaticPool if "sqlite" in self.settings.database_url else None,
            connect_args={"check_same_thread": False} if "sqlite" in self.settings.database_url else {}
        )
        
        # Create session factory
        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            # Enable SQLite optimizations
            if "sqlite" in self.settings.database_url:
                from sqlalchemy import text
                await conn.execute(text("PRAGMA foreign_keys=ON"))
                await conn.execute(text("PRAGMA journal_mode=WAL"))
                await conn.execute(text("PRAGMA synchronous=NORMAL"))
                await conn.execute(text("PRAGMA cache_size=10000"))
                await conn.execute(text("PRAGMA temp_store=memory"))
    
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session."""
        if not self.async_session_factory:
            await self.init_database()
        
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()


# Global database manager instance
db_manager = DatabaseManager()


# Convenience functions
async def init_database() -> None:
    """Initialize database - convenience function."""
    await db_manager.init_database()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session - convenience function."""
    async for session in db_manager.get_session():
        yield session


async def close_database() -> None:
    """Close database connections - convenience function."""
    await db_manager.close()


# Database utilities
class DatabaseUtils:
    """Utility functions for database operations."""
    
    @staticmethod
    async def get_channel_by_id(session: AsyncSession, channel_id: str) -> Optional[Channel]:
        """Get channel by YouTube channel ID."""
        from sqlalchemy import select
        result = await session.execute(
            select(Channel).where(Channel.channel_id == channel_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_video_by_id(session: AsyncSession, video_id: str) -> Optional[Video]:
        """Get video by YouTube video ID."""
        from sqlalchemy import select
        result = await session.execute(
            select(Video).where(Video.video_id == video_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_active_channels(session: AsyncSession) -> list[Channel]:
        """Get all active channels."""
        from sqlalchemy import select
        result = await session.execute(
            select(Channel).where(Channel.is_active == True)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_unprocessed_videos(session: AsyncSession, limit: int = 10) -> list[Video]:
        """Get videos that haven't been processed yet."""
        from sqlalchemy import select
        result = await session.execute(
            select(Video)
            .where(Video.processed_at.is_(None))
            .order_by(Video.published_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_videos_needing_notification(session: AsyncSession, limit: int = 10) -> list[Video]:
        """Get videos that need notifications sent."""
        from sqlalchemy import select
        result = await session.execute(
            select(Video)
            .where(
                Video.processed_at.isnot(None),
                Video.notification_sent == False,
                Video.summary.isnot(None)
            )
            .order_by(Video.published_at.desc())
            .limit(limit)
        )
        return result.scalars().all()