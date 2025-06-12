from fastapi import FastAPI, HTTPException, Body
import uuid
from typing import List

from .models import Project, Task, TaskStatus, ProjectCreate # Ensure ProjectCreate is imported
from .services import (
    process_prompt_to_plan,
    get_project_service,
    get_task_service,
    update_task_status_service
)
from .database import clear_db # For potential testing/reset endpoint

app = FastAPI(
    title="MCP - Master Control Program Server",
    description="AI-powered Task Management Server for decomposing development goals into actionable plans.",
    version="0.1.0 (MVP)"
)

# --- API Endpoints ---

@app.post("/projects/generate", response_model=Project, status_code=201)
async def generate_project_and_task_plan(prompt_body: Dict[str, str] = Body(...)):
    """
    Submits the user's high-level prompt to generate a new project and its initial task plan.
    Request Body: {"prompt": "Your high-level goal..."}
    """
    prompt = prompt_body.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required in the request body.")
    
    try:
        project = process_prompt_to_plan(prompt)
        return project
    except Exception as e:
        # Log the exception e
        raise HTTPException(status_code=500, detail=f"Failed to process prompt: {str(e)}")

@app.get("/projects/{project_id}/tasks", response_model=Project) # Or a custom model for just tasks
async def get_project_task_list(project_id: uuid.UUID):
    """
    Retrieves the current state of all tasks for a given project.
    Returns the full project object which includes the tasks.
    """
    project = get_project_service(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project with id {project_id} not found.")
    return project

@app.get("/tasks/{task_id}", response_model=Task) # For fetching a single task directly
async def get_task_details(task_id: uuid.UUID):
    """
    Retrieves details for a specific task by its ID.
    """
    task = get_task_service(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found.")
    return task

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task_status(task_id: uuid.UUID, status_update: TaskStatus):
    """
    Updates the status of a specific task (e.g., 'pending', 'completed').
    Request Body: {"status": "completed"}
    """
    updated_task = update_task_status_service(task_id, status_update)
    if not updated_task:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found or update failed.")
    return updated_task

# Optional: Endpoint to clear the in-memory database for testing
@app.post("/debug/clear_db", status_code=204)
async def debug_clear_database():
    """
    Clears all data from the in-memory database. Use with caution.
    """
    clear_db()
    return None

# To run the server (for local development):
# uvicorn mcp_project.mcp_server.main:app --reload
