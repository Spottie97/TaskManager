import uuid
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

# Enum for Task Status
class TaskStatus(str, BaseModel):
    status: Literal['pending', 'in-progress', 'completed', 'blocked'] = 'pending'

# Enum for Task Complexity
class TaskComplexity(str, BaseModel):
    complexity: Literal['simple', 'medium', 'complex', None] = None

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: TaskStatus = Field(default_factory=TaskStatus)
    complexity: TaskComplexity = Field(default_factory=TaskComplexity)
    estimated_time: Optional[str] = Field(default=None, alias="estimatedTime") # e.g., '2h', '1d'

class TaskCreate(TaskBase):
    pass

class Task(TaskBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    project_id: uuid.UUID = Field(alias="projectId")
    parent_id: Optional[uuid.UUID] = Field(default=None, alias="parentId")
    dependencies: List[uuid.UUID] = Field(default_factory=list)
    sub_tasks: List['Task'] = Field(default_factory=list, alias="subTasks") # Forward reference for self-nesting
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

Task.update_forward_refs() # Resolve forward reference for Task.sub_tasks

class ProjectBase(BaseModel):
    name: str
    original_prompt: str = Field(alias="originalPrompt")

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tasks: List[Task] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
