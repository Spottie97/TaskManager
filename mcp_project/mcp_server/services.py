import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional # Added Optional

from sqlalchemy.ext.asyncio import AsyncSession # New import

from .models import Project, ProjectCreate, Task, TaskCreate, TaskStatus, TaskComplexity, TaskUpdate # Added TaskUpdate
# Updated database imports to reflect new async functions and their expected arguments
from .database import (
    create_project_in_db,
    get_project_from_db,
    get_task_from_db,
    update_task_status_in_db,
    update_task_details_in_db, # Added update_task_details_in_db
    add_task_to_project_in_db, # Added add_task_to_project_in_db
    delete_task_from_db # Added delete_task_from_db
)

# --- Prompt Processing and Planning Service ---

# _convert_simulated_llm_task_to_model remains largely the same as it prepares Pydantic models
# which are then passed to the database layer. It doesn't directly interact with DB.
def _convert_simulated_llm_task_to_model(task_data: Dict[str, Any], project_id: uuid.UUID, parent_id: Optional[uuid.UUID] = None) -> Task:
    """Helper to convert a single task dictionary (from simulated LLM) to a Task model."""
    complexity_str = task_data.get("complexity")
    task_complexity_obj = TaskComplexity(complexity=complexity_str) if complexity_str else TaskComplexity()

    # Generate new ID for each task. This is crucial as database layer expects Pydantic models with IDs.
    task_id = uuid.uuid4()

    # Prepare sub_tasks first to ensure their IDs are generated before being referenced as dependencies (if that were the case)
    # Though current dependency model is by ID, and LLM simulation doesn't create cross-task dependencies yet.
    pydantic_sub_tasks = []
    if "sub_tasks" in task_data and task_data["sub_tasks"]:
        for sub_task_data in task_data["sub_tasks"]:
            # project_id is passed down, parent_id is the current task's ID
            sub_task_model = _convert_simulated_llm_task_to_model(sub_task_data, project_id, parent_id=task_id)
            pydantic_sub_tasks.append(sub_task_model)

    # Handle dependencies - these are expected to be UUIDs of other tasks
    # In the current simulation, these would be manually defined if any.
    # The LLM would need to be aware of generated task IDs to create valid dependency links.
    dependencies_ids = []
    raw_dependencies = task_data.get("dependencies", [])
    for dep in raw_dependencies:
        try:
            dependencies_ids.append(uuid.UUID(dep))
        except ValueError:
            print(f"Warning: Invalid UUID format for dependency '{dep}' in task '{task_data.get('title')}'. Skipping.")

    task = Task(
        id=task_id,
        project_id=project_id,
        parent_id=parent_id,
        title=task_data["title"],
        description=task_data.get("description"),
        status=TaskStatus.PENDING, # Default status
        complexity=task_complexity_obj,
        estimated_time=task_data.get("estimatedTime"),
        dependencies=dependencies_ids,
        created_at=datetime.utcnow(), # Pydantic model still tracks this for creation logic
        updated_at=datetime.utcnow(), # Pydantic model still tracks this for creation logic
        sub_tasks=pydantic_sub_tasks
    )
    return task

async def process_prompt_to_plan(db: AsyncSession, prompt: str) -> Project:
    """
    Simulates calling an LLM to break down the prompt into a project plan.
    Now an async function that uses the database session.
    """
    print(f"Processing prompt: {prompt[:50]}...")

    project_name = "Flask Weather App (from Prompt)"
    if "flask weather app" in prompt.lower():
        simulated_llm_tasks_data = [
            {
                "title": "Set up project environment", "complexity": "simple",
                "sub_tasks": [
                    {"title": "Create project directory", "complexity": "simple"},
                    {"title": "Initialize virtual environment", "complexity": "simple"},
                    {"title": "Install Flask & requests", "complexity": "simple"},
                ]
            },
            {
                "title": "Develop backend server", "complexity": "medium",
                "sub_tasks": [
                    {"title": "Create main app.py", "complexity": "simple"},
                    {"title": "Implement Flask app structure", "complexity": "medium"},
                    {"title": "Create API route for city weather", "complexity": "medium"},
                ]
            },
            {
                "title": "Integrate OpenWeatherMap API", "complexity": "medium",
                "sub_tasks": [
                    {"title": "Function to fetch weather data", "complexity": "medium"},
                    {"title": "Secure API key handling", "complexity": "simple"},
                    {"title": "Parse API JSON response", "complexity": "medium"},
                ]
            }
        ]
    else:
        project_name = "Generic Project (from Prompt)"
        simulated_llm_tasks_data = [
            {"title": "Understand Requirements", "complexity": "simple"},
            {"title": "Design Solution", "complexity": "medium"},
            {"title": "Implement Feature X", "complexity": "complex", "sub_tasks": [
                {"title": "Sub-task X.1"},
                {"title": "Sub-task X.2"}
            ]},
            {"title": "Test Feature X", "complexity": "medium"}
        ]

    project_id = uuid.uuid4() # Generate project ID here
    project_create_pydantic = ProjectCreate(name=project_name, original_prompt=prompt)

    # Convert LLM tasks to Pydantic Task models
    pydantic_tasks_list = []
    for task_data in simulated_llm_tasks_data:
        # parent_id is None for top-level tasks
        task_model = _convert_simulated_llm_task_to_model(task_data, project_id, parent_id=None)
        pydantic_tasks_list.append(task_model)

    # Create Pydantic Project model - this is what create_project_in_db expects
    project_pydantic = Project(
        **project_create_pydantic.dict(),
        id=project_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        tasks=pydantic_tasks_list
    )

    # Save to DB using the new async DB function
    created_project = await create_project_in_db(db, project_pydantic)
    return created_project

# --- Task Management Services (now async and use db session) ---

async def get_project_service(db: AsyncSession, project_id: uuid.UUID) -> Optional[Project]:
    return await get_project_from_db(db, project_id)

async def get_task_service(db: AsyncSession, task_id: uuid.UUID) -> Optional[Task]:
    return await get_task_from_db(db, task_id)

async def update_task_status_service(db: AsyncSession, task_id: uuid.UUID, status_update: TaskStatus) -> Optional[Task]:
    """Updates the status of a task. Now async and uses db session."""
    # The database function `update_task_status_in_db` will handle if task not found by returning None.
    # The API layer in main.py is responsible for raising HTTPException if result is None.
    return await update_task_status_in_db(db, task_id, status_update)

async def update_task_details_service(
    db: AsyncSession,
    task_id: uuid.UUID,
    task_update_data: TaskUpdate
) -> Optional[Task]:
    """Updates the details of a task. Now async and uses db session."""
    return await update_task_details_in_db(db, task_id, task_update_data)


async def add_task_to_project_service(
    db: AsyncSession,
    project_id: uuid.UUID,
    task_create_data: TaskCreate
) -> Optional[Task]: # Returns the created task or None if project not found
    """Adds a new task to a specific project."""
    # First, verify the project exists to provide a clear error if not.
    # get_project_from_db returns a PydanticProject or None.
    project = await get_project_from_db(db, project_id)
    if not project:
        return None # Signal that project wasn't found

    # If project exists, proceed to add the task
    # The add_task_to_project_in_db function handles parent_id validation internally
    try:
        new_task = await add_task_to_project_in_db(db, task_create_data, project_id)
        return new_task
    except ValueError as e:
        # This could catch errors from add_task_to_project_in_db like invalid parent_id
        print(f"Error adding task to project {project_id}: {e}") # Log for server admin
        # Depending on desired behavior, could re-raise a specific service-level exception
        # or let the API layer handle the None return by raising an appropriate HTTP error.
        return None

async def delete_task_service(db: AsyncSession, task_id: uuid.UUID) -> bool:
    """Deletes a task by its ID. Returns True if deletion was successful, False otherwise."""
    # The database function `delete_task_from_db` will handle if task not found
    # by returning False, or if deletion fails for other reasons.
    success = await delete_task_from_db(db, task_id)
    return success
