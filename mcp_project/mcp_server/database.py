from typing import Dict, List
import uuid
from .models import Project, Task, TaskStatus # Make sure TaskStatus is imported
from datetime import datetime

# In-memory storage for MVP
db_projects: Dict[uuid.UUID, Project] = {}
db_tasks: Dict[uuid.UUID, Task] = {} # For quick task lookup

def get_project(project_id: uuid.UUID) -> Project | None:
    return db_projects.get(project_id)

def create_project_in_db(project: Project) -> Project:
    if project.id in db_projects:
        raise ValueError(f"Project with id {project.id} already exists")
    db_projects[project.id] = project

    # Helper to recursively add tasks to db_tasks for quick lookup
    def _add_tasks_to_cache(tasks: List[Task]):
        for task_item in tasks:
            if task_item.id in db_tasks:
                # This could happen if task IDs are not globally unique across different imports
                # or if a task is somehow processed twice. For MVP, we assume unique IDs.
                print(f"Warning: Task with ID {task_item.id} already in db_tasks cache.")
            db_tasks[task_item.id] = task_item
            if task_item.sub_tasks:
                _add_tasks_to_cache(task_item.sub_tasks)
    
    _add_tasks_to_cache(project.tasks)
    return project

def get_task(task_id: uuid.UUID) -> Task | None:
    # Primary way to get a task is through the flat db_tasks dictionary
    task = db_tasks.get(task_id)
    if task:
        return task

    # Fallback: If not in db_tasks, iterate through projects (should be rare if create_project_in_db is used consistently)
    # This indicates that db_tasks might not be perfectly in sync or a task was added outside create_project_in_db
    for project in db_projects.values():
        def find_task_in_list(tasks: List[Task], t_id: uuid.UUID) -> Task | None:
            for t in tasks:
                if t.id == t_id:
                    db_tasks[t.id] = t # Cache it if found this way
                    return t
                if t.sub_tasks:
                    found_in_sub = find_task_in_list(t.sub_tasks, t_id)
                    if found_in_sub:
                        db_tasks[found_in_sub.id] = found_in_sub # Cache it
                        return found_in_sub
            return None
        
        found = find_task_in_list(project.tasks, task_id)
        if found:
            return found
    return None

def update_task_status_in_db(task_id: uuid.UUID, new_status: TaskStatus) -> Task | None:
    task_to_update = get_task(task_id)
    if task_to_update:
        task_to_update.status = new_status
        task_to_update.updated_at = datetime.utcnow()
        # Ensure the change is reflected in the db_tasks cache as well, if it wasn't already the same object
        db_tasks[task_id] = task_to_update 
        return task_to_update
    return None

# To clear the DB for testing or restarts (since it's in-memory)
def clear_db():
    db_projects.clear()
    db_tasks.clear()
