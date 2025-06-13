
import uuid
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Table, Text, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID # Using PostgreSQL UUID for compatibility, works with SQLite
import datetime

# Using Pydantic models for Enum definitions to ensure consistency
from .models import TaskStatus, TaskComplexity

DATABASE_URL = "sqlite+aiosqlite:///./mcp_database.db"

Base = declarative_base()

# Association table for Task dependencies (many-to-many)
task_dependencies_association = Table(
    'task_dependencies_association',
    Base.metadata,
    Column('task_id', PG_UUID(as_uuid=True), ForeignKey('tasks.id'), primary_key=True),
    Column('dependency_id', PG_UUID(as_uuid=True), ForeignKey('tasks.id'), primary_key=True)
)

class DBProject(Base):
    __tablename__ = "projects"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, index=True)
    original_prompt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    tasks = relationship("DBTask", back_populates="project", cascade="all, delete-orphan")

class DBTask(Base):
    __tablename__ = "tasks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    parent_id = Column(PG_UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True) # For sub-tasks

    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    status = Column(SQLAlchemyEnum(TaskStatus), default=TaskStatus.PENDING)
    complexity = Column(SQLAlchemyEnum(TaskComplexity), nullable=True)
    estimated_time = Column(String, nullable=True) # Store as string as per Pydantic model

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("DBProject", back_populates="tasks")
    sub_tasks = relationship("DBTask", back_populates="parent_task", remote_side=[id], cascade="all, delete-orphan")
    parent_task = relationship("DBTask", back_populates="sub_tasks", remote_side=[parent_id])

    # Many-to-many relationship for dependencies
    dependencies = relationship(
        "DBTask",
        secondary=task_dependencies_association,
        primaryjoin=id == task_dependencies_association.c.task_id,
        secondaryjoin=id == task_dependencies_association.c.dependency_id,
        backref="dependent_on"
    )

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}) # check_same_thread for SQLite
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True) # future=True for 2.0 style

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    async with engine.connect() as conn: # Use async connect for async engine
        # await conn.run_sync(Base.metadata.drop_all) # Optional: drop tables for a clean slate
        await conn.run_sync(Base.metadata.create_all)
    # For non-async engine, it would be:
    # Base.metadata.create_all(bind=engine)

# Note: For a truly async setup with aiosqlite, the engine should be an AsyncEngine
# from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
# AsyncEngine = create_async_engine(DATABASE_URL)
# AsyncSessionLocal = sessionmaker(AsyncEngine, class_=AsyncSession, expire_on_commit=False)

# Re-evaluating the engine setup for aiosqlite and FastAPI
# The current engine setup is for synchronous SQLAlchemy with a driver that can be async.
# For full async operations with SQLAlchemy 2.0 style, we need create_async_engine.

# Corrected Engine and Session Setup for full async:
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./mcp_database.db" # Ensure this path is correct

async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False) # echo=True for debugging SQL
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def init_db_async():
    async with async_engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Uncomment to clear DB on start
        await conn.run_sync(Base.metadata.create_all)

async def get_async_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

