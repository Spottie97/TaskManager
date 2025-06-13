import uuid
import datetime # Keep for datetime.datetime and datetime.timezone
from typing import Optional # Removed List as it's not directly used

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload # Removed joinedload as it's not used

from .db_models import DBProject, DBTask # SQLAlchemy models
from .models import ( # Pydantic models
    Project as PydanticProject,
    Task as PydanticTask,
    TaskStatus as PydanticTaskStatus,
    # PydanticProjectCreate is not used here
    TaskCreate as PydanticTaskCreate,
    TaskUpdate as PydanticTaskUpdate,
    TaskComplexity as PydanticTaskComplexity # Ensure this is imported for add_task_to_project_in_db
)

# --- Conversion Helpers ---

def _convert_db_task_to_pydantic_task(db_task: DBTask) -> PydanticTask:
    """
    Converts a DBTask SQLAlchemy model to a PydanticTask model.
    """
    pydantic_sub_tasks = []
    if db_task.sub_tasks:
        for sub_db_task in db_task.sub_tasks:
            pydantic_sub_tasks.append(_convert_db_task_to_pydantic_task(sub_db_task))

    dependency_ids = []
    if db_task.dependencies:
        for dep_db_task in db_task.dependencies:
            dependency_ids.append(dep_db_task.id)

    return PydanticTask(
        id=db_task.id,
        project_id=db_task.project_id,
        parent_id=db_task.parent_id,
        title=db_task.title,
        description=db_task.description,
        status=db_task.status,
        complexity=db_task.complexity,
        estimated_time=db_task.estimated_time,
        created_at=db_task.created_at,
        updated_at=db_task.updated_at,
        sub_tasks=pydantic_sub_tasks,
        dependencies=dependency_ids
    )

def _convert_db_project_to_pydantic_project(db_project: DBProject) -> PydanticProject:
    """
    Converts a DBProject SQLAlchemy model to a PydanticProject model.
    """
    pydantic_tasks = []
    if db_project.tasks:
        for db_task_item in db_project.tasks:
            if db_task_item.parent_id is None:
                pydantic_tasks.append(_convert_db_task_to_pydantic_task(db_task_item))
    
    return PydanticProject(
        id=db_project.id,
        name=db_project.name,
        original_prompt=db_project.original_prompt,
        created_at=db_project.created_at,
        updated_at=db_project.updated_at,
        tasks=pydantic_tasks
    )

async def _create_db_task_from_pydantic(
    db: AsyncSession,
    pydantic_task_data: PydanticTask,
    project_db_id: uuid.UUID,
    parent_db_id: Optional[uuid.UUID] = None
) -> DBTask:
    """
    Creates a DBTask SQLAlchemy model instance from PydanticTask data (recursive).
    """
    db_task = DBTask(
        id=pydantic_task_data.id,
        project_id=project_db_id,
        parent_id=parent_db_id,
        title=pydantic_task_data.title,
        description=pydantic_task_data.description,
        status=pydantic_task_data.status.status if isinstance(pydantic_task_data.status, PydanticTaskStatus) else pydantic_task_data.status,
        complexity=pydantic_task_data.complexity.complexity if isinstance(pydantic_task_data.complexity, PydanticTaskComplexity) else pydantic_task_data.complexity,
        estimated_time=pydantic_task_data.estimated_time
    )

    if pydantic_task_data.sub_tasks:
        for sub_pydantic_task in pydantic_task_data.sub_tasks:
            db_sub_task = await _create_db_task_from_pydantic(
                db, sub_pydantic_task, project_db_id, db_task.id
            )
            db_task.sub_tasks.append(db_sub_task)

    if pydantic_task_data.dependencies:
        for dep_id in pydantic_task_data.dependencies:
            dependency_db_task = await db.get(DBTask, dep_id)
            if dependency_db_task:
                db_task.dependencies.append(dependency_db_task)
            else:
                print(f"Warning: Dependency task with ID {dep_id} not found for task {db_task.id}.")
    
    return db_task

# --- Database Operations ---

async def create_project_in_db(
    db: AsyncSession,
    project_data: PydanticProject
) -> PydanticProject:
    """
    Creates a new project and its tasks in the database.
    """
    db_project = DBProject(
        id=project_data.id,
        name=project_data.name,
        original_prompt=project_data.original_prompt
    )
    db.add(db_project)

    if project_data.tasks:
        for p_task in project_data.tasks:
            if p_task.parent_id is None:
                db_task_obj = await _create_db_task_from_pydantic(db, p_task, db_project.id)
                db.add(db_task_obj)

    await db.commit()
    await db.refresh(db_project)
    
    loaded_db_project = await get_project_from_db_internal(db, db_project.id)
    if not loaded_db_project:
        raise Exception("Failed to reload project after creation.")
    return _convert_db_project_to_pydantic_project(loaded_db_project)

async def get_project_from_db_internal(db: AsyncSession, project_id: uuid.UUID) -> Optional[DBProject]:
    stmt = select(DBProject).where(DBProject.id == project_id).options(
        selectinload(DBProject.tasks)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_project_from_db(db: AsyncSession, project_id: uuid.UUID) -> Optional[PydanticProject]:
    db_project = await get_project_from_db_internal(db, project_id)
    if db_project:
        return _convert_db_project_to_pydantic_project(db_project)
    return None

async def get_task_from_db_internal(db: AsyncSession, task_id: uuid.UUID) -> Optional[DBTask]:
    stmt = select(DBTask).where(DBTask.id == task_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_task_from_db(db: AsyncSession, task_id: uuid.UUID) -> Optional[PydanticTask]:
    db_task = await get_task_from_db_internal(db, task_id)
    if db_task:
        return _convert_db_task_to_pydantic_task(db_task)
    return None

async def update_task_status_in_db(
    db: AsyncSession,
    task_id: uuid.UUID,
    new_status: PydanticTaskStatus # This is the Pydantic model instance
) -> Optional[PydanticTask]:
    db_task = await get_task_from_db_internal(db, task_id)
    if db_task:
        db_task.status = new_status.status # Assign the string value from the Pydantic model
        db_task.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await db.commit()
        await db.refresh(db_task)
        return _convert_db_task_to_pydantic_task(db_task)
    return None

async def update_task_details_in_db(
    db: AsyncSession,
    task_id: uuid.UUID,
    task_update_data: PydanticTaskUpdate
) -> Optional[PydanticTask]:
    db_task = await get_task_from_db_internal(db, task_id)
    if not db_task:
        return None

    update_data = task_update_data.dict(exclude_unset=True, by_alias=True)

    for field, value in update_data.items():
        if field == "dependencies" and value is not None:
            db_task.dependencies.clear()
            for dep_id in value:
                dep_task = await db.get(DBTask, dep_id)
                if dep_task:
                    db_task.dependencies.append(dep_task)
                else:
                    print(f"Warning: Dependency task ID {dep_id} not found for task {task_id}.")
        elif field == "status" and value is not None: # Handle TaskStatus object
            db_task.status = value.get('status', db_task.status) if isinstance(value, dict) else value.status
        elif field == "complexity" and value is not None: # Handle TaskComplexity object
            db_task.complexity = value.get('complexity', db_task.complexity) if isinstance(value, dict) else value.complexity
        elif hasattr(db_task, field):
            setattr(db_task, field, value)

    db_task.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    await db.refresh(db_task)
    return _convert_db_task_to_pydantic_task(db_task)

async def add_task_to_project_in_db(
    db: AsyncSession,
    task_create_data: PydanticTaskCreate,
    project_id: uuid.UUID,
) -> PydanticTask:
    project_db = await db.get(DBProject, project_id)
    if not project_db:
        raise ValueError(f"Project with ID {project_id} not found.")

    if task_create_data.parent_id:
        parent_db_task = await db.get(DBTask, task_create_data.parent_id)
        if not parent_db_task or parent_db_task.project_id != project_id:
            raise ValueError(f"Parent task {task_create_data.parent_id} not found or not in project {project_id}.")

    # Extract string values from Pydantic status/complexity models
    status_val = task_create_data.status.status if task_create_data.status else PydanticTaskStatus().status
    complexity_val = task_create_data.complexity.complexity if task_create_data.complexity else None # Allow None for complexity

    db_task = DBTask(
        id=uuid.uuid4(),
        project_id=project_id,
        parent_id=task_create_data.parent_id,
        title=task_create_data.title,
        description=task_create_data.description,
        status=status_val,
        complexity=complexity_val,
        estimated_time=task_create_data.estimated_time,
        created_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc)
    )

    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    return _convert_db_task_to_pydantic_task(db_task)

async def delete_task_from_db(db: AsyncSession, task_id: uuid.UUID) -> bool:
    """Deletes a task from the database by its ID."""
    db_task = await get_task_from_db_internal(db, task_id) # Uses the existing helper

    if not db_task:
        return False # Task not found

    # Cascading deletes for sub_tasks and dependencies should ideally be configured
    # in the SQLAlchemy models (DBTask relationships in db_models.py).
    # For example, sub_tasks relationship should have `cascade="all, delete-orphan"`.
    # The dependencies relationship (many-to-many via TaskDependencyLink) should ensure
    # that deleting a task also deletes its entries in the association table.
    # If these are not set, manual deletion of related entities would be required here
    # to prevent foreign key constraint violations.

    # Assuming cascades are correctly configured:
    await db.delete(db_task)
    try:
        await db.commit()
        return True
    except Exception as e:
        await db.rollback() # Rollback in case of an error during commit
        print(f"Error deleting task {task_id} from database: {e}")
        # Re-raise the exception or return False depending on desired error handling
        # For now, returning False to indicate failure.
        return False
