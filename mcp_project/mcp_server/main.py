from fastapi import FastAPI, HTTPException, Body, Depends
import uuid
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Project, Task, TaskStatus, TaskUpdate, TaskCreate # Added TaskCreate
from .services import (
    process_prompt_to_plan,
    get_project_service,
    get_task_service,
    update_task_status_service,
    update_task_details_service,
    add_task_to_project_service, # Added add_task_to_project_service
    delete_task_service # Added delete_task_service
)
from .db_models import init_db_async, get_async_db

app = FastAPI(
    title="MCP - Master Control Program Server",
    description="AI-powered Task Management Server for decomposing development goals into actionable plans.",
    version="0.2.2 (Task Delete Endpoint)" # Version updated
)

@app.on_event("startup")
async def on_startup():
    """Initialize the database when the application starts."""
    await init_db_async()

# --- API Endpoints ---

@app.post("/projects/generate", response_model=Project, status_code=201)
async def generate_project_and_task_plan(
    prompt_body: Dict[str, str] = Body(...),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Submits the user's high-level prompt to generate a new project and its initial task plan.
    Request Body: {"prompt": "Your high-level goal..."}
    """
    prompt = prompt_body.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required in the request body.")
    
    try:
        project = await process_prompt_to_plan(db, prompt)
        return project
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process prompt: {str(e)}")

@app.get("/projects/{project_id}/tasks", response_model=Project) # This actually returns a Project model
async def get_project_task_list(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves the current state of all tasks for a given project.
    Returns the full project object which includes the tasks.
    """
    project = await get_project_service(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with id {project_id} not found.")
    return project

@app.post("/projects/{project_id}/tasks", response_model=Task, status_code=201)
async def create_task_for_project(
    project_id: uuid.UUID,
    task_create_data: TaskCreate, # Request body with task creation details
    db: AsyncSession = Depends(get_async_db)
):
    """
    Creates a new task and adds it to the specified project.
    Allows specifying parent_id for sub-tasks.
    Request Body: TaskCreate model (e.g., {"title": "New Task", "description": "...", "parent_id": "..."})
    """
    try:
        new_task = await add_task_to_project_service(db, project_id, task_create_data)
        if not new_task:
            # This case implies project_id was not found by the service
            raise HTTPException(status_code=404, detail=f"Project with id {project_id} not found.")
        return new_task
    except ValueError as e:
        # This can be raised by the service/db layer for invalid data (e.g., parent_id not found)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Catch-all for other unexpected errors
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")

@app.get("/tasks/{task_id}", response_model=Task)
async def get_task_details(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves details for a specific task by its ID.
    """
    task = await get_task_service(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found.")
    return task

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task_status(
    task_id: uuid.UUID,
    status_update: TaskStatus, # FastAPI will parse the request body to this enum
    db: AsyncSession = Depends(get_async_db)
):
    """
    Updates the status of a specific task (e.g., 'pending', 'completed').
    The request body should be the raw string value of the status, e.g., "completed".
    FastAPI handles the conversion to the TaskStatus enum.
    """
    updated_task = await update_task_status_service(db, task_id, status_update)
    if not updated_task:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found or update failed.")
    return updated_task

@app.patch("/tasks/{task_id}", response_model=Task)
async def update_task_details(
    task_id: uuid.UUID,
    task_update_data: TaskUpdate, # Request body with fields to update
    db: AsyncSession = Depends(get_async_db)
):
    """
    Partially updates the details of a specific task.
    Allows updating fields like title, description, complexity, estimated_time, and dependencies.
    Request Body: TaskUpdate model (e.g., {"title": "New Title", "description": "New Desc"})
    """
    updated_task = await update_task_details_service(db, task_id, task_update_data)
    if not updated_task:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found or update failed.")
    return updated_task

@app.delete("/tasks/{task_id}", status_code=204) # 204 No Content is typical for successful DELETE
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Deletes a specific task by its ID.
    Returns 204 No Content on successful deletion.
    Returns 404 Not Found if the task does not exist.
    """
    success = await delete_task_service(db, task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found or could not be deleted.")
    # No body should be returned for 204 response
    return

# To run the server (for local development):
# uvicorn mcp_project.mcp_server.main:app --reload
