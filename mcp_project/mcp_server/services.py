import uuid
from datetime import datetime
from typing import List, Dict, Any

from .models import Project, ProjectCreate, Task, TaskCreate, TaskStatus, TaskComplexity
from .database import (create_project_in_db, get_project as get_project_from_db, 
                     get_task as get_task_from_db, update_task_status_in_db)

# --- Prompt Processing and Planning Service ---

def _convert_simulated_llm_task_to_model(task_data: Dict[str, Any], project_id: uuid.UUID, parent_id: uuid.UUID | None = None) -> Task:
    """Helper to convert a single task dictionary (from simulated LLM) to a Task model."""
    # Ensure complexity is correctly mapped or defaulted
    complexity_value = task_data.get("complexity", None)
    if isinstance(complexity_value, str):
        task_complexity = TaskComplexity(complexity=complexity_value)
    else:
        task_complexity = TaskComplexity() # Defaults to None

    # Create the task model
    task = Task(
        id=uuid.uuid4(), # Generate new ID for each task
        project_id=project_id,
        parent_id=parent_id,
        title=task_data["title"],
        description=task_data.get("description"),
        status=TaskStatus(status='pending'), # Default status
        complexity=task_complexity,
        estimated_time=task_data.get("estimatedTime"),
        dependencies=[uuid.UUID(dep) for dep in task_data.get("dependencies", [])], # Handle dependencies if provided
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        sub_tasks=[] # Initialize sub_tasks list
    )

    # Recursively convert and add sub-tasks
    if "sub_tasks" in task_data and task_data["sub_tasks"]:
        for sub_task_data in task_data["sub_tasks"]:
            sub_task_model = _convert_simulated_llm_task_to_model(sub_task_data, project_id, parent_id=task.id)
            task.sub_tasks.append(sub_task_model)
    
    return task

def process_prompt_to_plan(prompt: str) -> Project:
    """
    Simulates calling an LLM to break down the prompt into a project plan.
    For MVP, this returns a hardcoded plan based on a known prompt.
    """
    print(f"Processing prompt: {prompt[:50]}...") # Log a bit of the prompt

    # Simulate LLM response (hardcoded for MVP)
    # Using the example: "Create a Python Flask web application with a single page that displays 
    # the current weather for a given city using the OpenWeatherMap API"
    
    project_name = "Flask Weather App (from Prompt)"
    if "flask weather app" in prompt.lower():
        simulated_llm_tasks_data = [
            {
                "title": "Set up the project environment",
                "complexity": "simple",
                "sub_tasks": [
                    {"title": "Create a project directory", "complexity": "simple"},
                    {"title": "Initialize a virtual environment", "complexity": "simple"},
                    {"title": "Install necessary libraries (Flask, requests)", "complexity": "simple"},
                ]
            },
            {
                "title": "Develop the backend server",
                "complexity": "medium",
                "sub_tasks": [
                    {"title": "Create the main app.py file", "complexity": "simple"},
                    {"title": "Implement the basic Flask app structure", "complexity": "medium"},
                    {"title": "Create an API route that accepts a city name", "complexity": "medium"},
                ]
            },
            {
                "title": "Integrate with the OpenWeatherMap API",
                "complexity": "medium",
                # Dependencies will be more robustly handled in a later phase
                # For MVP, we can imagine the LLM might provide placeholder IDs or descriptions
                # "dependencies": ["ID_of_task_Create_API_route"], 
                "sub_tasks": [
                    {"title": "Write a function to fetch weather data", "complexity": "medium"},
                    {"title": "Handle API keys securely (do not hardcode)", "complexity": "simple"},
                    {"title": "Parse the JSON response from the API", "complexity": "medium"},
                ]
            }
        ]
    else:
        # Generic fallback if the prompt doesn't match the specific example
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

    # Create Project object
    project_id = uuid.uuid4()
    project_create = ProjectCreate(name=project_name, original_prompt=prompt)
    project = Project(
        **project_create.dict(), 
        id=project_id, 
        created_at=datetime.utcnow(), 
        updated_at=datetime.utcnow(),
        tasks=[]
    )

    # Convert simulated LLM tasks to Task models and add to project
    for task_data in simulated_llm_tasks_data:
        task_model = _convert_simulated_llm_task_to_model(task_data, project_id)
        project.tasks.append(task_model)

    # Save to DB
    created_project = create_project_in_db(project)
    return created_project

# --- Task Management Services ---

def get_project_service(project_id: uuid.UUID) -> Project | None:
    return get_project_from_db(project_id)

def get_task_service(task_id: uuid.UUID) -> Task | None:
    return get_task_from_db(task_id)

def update_task_status_service(task_id: uuid.UUID, status_update: TaskStatus) -> Task | None:
    """Updates the status of a task."""
    # Validate if the task exists first (optional, as DB function might handle it)
    task = get_task_from_db(task_id)
    if not task:
        return None # Or raise HTTPException(status_code=404, detail="Task not found") in API layer
    
    # The database function now takes TaskStatus directly
    return update_task_status_in_db(task_id, status_update)
