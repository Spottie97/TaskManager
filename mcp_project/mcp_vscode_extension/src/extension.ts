import * as vscode from 'vscode';
import axios, { AxiosError } from 'axios';

let outputChannel: vscode.OutputChannel;

enum TaskStatus {
    Pending = "pending",
    InProgress = "in-progress",
    Completed = "completed",
    Blocked = "blocked",
}

enum TaskComplexity {
    Simple = "simple",
    Medium = "medium",
    Complex = "complex",
}

interface ServerTask {
    id: string;
    title: string;
    description?: string;
    status: TaskStatus;
    complexity?: TaskComplexity;
    estimated_time?: string;
    project_id: string;
    parent_id?: string;
    dependencies: string[];
    sub_tasks: ServerTask[];
    created_at: string;
    updated_at: string;
}

interface ServerProject {
    id: string;
    name: string;
    original_prompt: string;
    tasks: ServerTask[];
    created_at: string;
    updated_at: string;
}

class TaskTreeItem extends vscode.TreeItem {
    constructor(
        public readonly task: ServerTask,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(task.title, collapsibleState);
        this.tooltip = `[${this.task.status.toUpperCase()}] ${this.task.title}`;
        this.description = this.task.status;
        this.id = task.id;
        this.contextValue = 'taskItem';

        switch (task.status) {
            case TaskStatus.Completed:
                this.iconPath = new vscode.ThemeIcon('check');
                break;
            case TaskStatus.InProgress:
                this.iconPath = new vscode.ThemeIcon('sync~spin');
                break;
            case TaskStatus.Blocked:
                this.iconPath = new vscode.ThemeIcon('error');
                break;
            case TaskStatus.Pending:
            default:
                this.iconPath = new vscode.ThemeIcon('circle-large-outline');
                break;
        }
    }
}

class TaskTreeDataProvider implements vscode.TreeDataProvider<TaskTreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<TaskTreeItem | undefined | null | void> = new vscode.EventEmitter<TaskTreeItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<TaskTreeItem | undefined | null | void> = this._onDidChangeTreeData.event;

    private projectTasks: ServerTask[] = [];

    constructor() { }

    getTreeItem(element: TaskTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: TaskTreeItem): vscode.ProviderResult<TaskTreeItem[]> {
        if (element) {
            return Promise.resolve(
                element.task.sub_tasks.map(subtask => new TaskTreeItem(
                    subtask,
                    subtask.sub_tasks && subtask.sub_tasks.length > 0
                        ? vscode.TreeItemCollapsibleState.Collapsed
                        : vscode.TreeItemCollapsibleState.None
                ))
            );
        } else {
            return Promise.resolve(
                this.projectTasks.map(task => new TaskTreeItem(
                    task,
                    task.sub_tasks && task.sub_tasks.length > 0
                        ? vscode.TreeItemCollapsibleState.Collapsed
                        : vscode.TreeItemCollapsibleState.None
                ))
            );
        }
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    loadProject(project: ServerProject | null): void {
        if (project && project.tasks) {
            this.projectTasks = project.tasks;
        } else {
            this.projectTasks = [];
        }
        this.refresh();
    }

    findTask(taskId: string, tasks: ServerTask[] = this.projectTasks): ServerTask | null {
        for (const task of tasks) {
            if (task.id === taskId) {
                return task;
            }
            if (task.sub_tasks && task.sub_tasks.length > 0) {
                const foundInSub = this.findTask(taskId, task.sub_tasks);
                if (foundInSub) {
                    return foundInSub;
                }
            }
        }
        return null;
    }
}

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel("MCP Task Manager Log");
    outputChannel.appendLine('MCP Task Manager extension is now active!');

    const taskTreeDataProvider = new TaskTreeDataProvider();
    vscode.window.registerTreeDataProvider('mcpTaskView', taskTreeDataProvider);

    const generateCmd = vscode.commands.registerCommand('mcp-vscode-extension.generateProjectPlan', async () => {
        const prompt = await vscode.window.showInputBox({
            prompt: 'Enter your project prompt',
            placeHolder: 'e.g., Create a Flask weather application'
        });

        if (prompt) {
            vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: "Generating Project Plan...",
                cancellable: false
            }, async (progress: vscode.Progress<{ message?: string; increment?: number }>) => {
                try {
                    outputChannel.appendLine(`Generating project plan for prompt: "${prompt}"`);
                    progress.report({ increment: 0, message: "Sending prompt to server..." });
                    const response = await axios.post<ServerProject>(
                        'http://localhost:8000/projects/generate',
                        { prompt },
                        { headers: { 'Content-Type': 'application/json' } }
                    );
                    progress.report({ increment: 50, message: "Processing plan..." });

                    if (response.data && response.data.tasks) {
                        taskTreeDataProvider.loadProject(response.data);
                        vscode.window.showInformationMessage('Project plan generated and loaded!');
                        vscode.commands.executeCommand('workbench.view.extension.mcpTaskViewContainer');
                    } else {
                        taskTreeDataProvider.loadProject(null);
                        vscode.window.showWarningMessage('Project plan generated, but no tasks were found.');
                    }
                    progress.report({ increment: 100, message: "Done." });

                } catch (error) {
                    taskTreeDataProvider.loadProject(null);
                    if (axios.isAxiosError(error)) {
                        const axiosError = error as AxiosError<any>;
                        const errorMessage = axiosError.response?.data?.detail || axiosError.message;
                        const fullError = JSON.stringify(axiosError.toJSON(), null, 2);
                        outputChannel.appendLine(`[ERROR] API Error generating project plan: ${errorMessage}\n${fullError}`);
                        vscode.window.showErrorMessage(`API Error: ${errorMessage}. Check MCP Task Manager Log for details.`);
                    } else if (error instanceof Error) {
                        outputChannel.appendLine(`[ERROR] Failed to generate project plan: ${error.message}\n${error.stack}`);
                        vscode.window.showErrorMessage(`Failed to generate project plan: ${error.message}. Check MCP Task Manager Log for details.`);
                    } else {
                        outputChannel.appendLine(`[ERROR] Failed to generate project plan. An unexpected error occurred: ${JSON.stringify(error)}`);
                        vscode.window.showErrorMessage('Failed to generate project plan. An unexpected error occurred. Check MCP Task Manager Log for details.');
                    }
                }
            });
        }
    });
    context.subscriptions.push(generateCmd);

    const markTaskCompleteCmd = vscode.commands.registerCommand('mcp-vscode-extension.markTaskAsComplete', async (taskItem: TaskTreeItem) => {
        if (!taskItem || !taskItem.task) {
            vscode.window.showErrorMessage('No task selected.');
            return;
        }
        await updateTaskStatus(taskItem, TaskStatus.Completed, "complete", taskTreeDataProvider);
    });
    context.subscriptions.push(markTaskCompleteCmd);

    const markTaskPendingCmd = vscode.commands.registerCommand('mcp-vscode-extension.markTaskAsPending', async (taskItem: TaskTreeItem) => {
        if (!taskItem || !taskItem.task) {
            vscode.window.showErrorMessage('No task selected.');
            return;
        }
        await updateTaskStatus(taskItem, TaskStatus.Pending, "pending", taskTreeDataProvider);
    });
    context.subscriptions.push(markTaskPendingCmd);

    const markTaskInProgressCmd = vscode.commands.registerCommand('mcp-vscode-extension.markTaskAsInProgress', async (taskItem: TaskTreeItem) => {
        if (!taskItem || !taskItem.task) {
            vscode.window.showErrorMessage('No task selected.');
            return;
        }
        await updateTaskStatus(taskItem, TaskStatus.InProgress, "in-progress", taskTreeDataProvider);
    });
    context.subscriptions.push(markTaskInProgressCmd);

    const markTaskBlockedCmd = vscode.commands.registerCommand('mcp-vscode-extension.markTaskAsBlocked', async (taskItem: TaskTreeItem) => {
        if (!taskItem || !taskItem.task) {
            vscode.window.showErrorMessage('No task selected.');
            return;
        }
        await updateTaskStatus(taskItem, TaskStatus.Blocked, "blocked", taskTreeDataProvider);
    });
    context.subscriptions.push(markTaskBlockedCmd);
}

async function updateTaskStatus(
    taskItem: TaskTreeItem,
    newStatus: TaskStatus,
    statusText: string,
    taskTreeDataProvider: TaskTreeDataProvider
): Promise<void> {
    if (!taskItem.task) {
        outputChannel.appendLine('[ERROR] updateTaskStatus called with invalid task item.');
        vscode.window.showErrorMessage('Invalid task item for status update.');
        return;
    }

    const taskId = taskItem.task.id;
    const originalStatus = taskItem.task.status;

    if (originalStatus === newStatus) {
        vscode.window.showInformationMessage(`Task "${taskItem.task.title}" is already ${statusText}.`);
        return;
    }

    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `Updating Task: ${taskItem.task.title}`,
        cancellable: false
    }, async (progress) => {
        progress.report({ increment: 0, message: "Sending update to server..." });
        try {
            const response = await axios.put<ServerTask>(
                `http://localhost:8000/tasks/${taskId}`,
                { status: newStatus },
                { headers: { 'Content-Type': 'application/json' } }
            );

            progress.report({ increment: 50, message: "Processing server response..." });

            if (response.data && response.data.id === taskId) {
                const updatedTask = taskTreeDataProvider.findTask(taskId);
                if (updatedTask) {
                    updatedTask.status = newStatus;
                    updatedTask.updated_at = response.data.updated_at;
                }
                taskTreeDataProvider.refresh();
                vscode.window.showInformationMessage(`Task "${taskItem.task.title}" marked as ${statusText}.`);
            } else {
                vscode.window.showWarningMessage('Task status updated on server, but local refresh might be incomplete.');
            }
            progress.report({ increment: 100, message: "Done." });
        } catch (error) {
            taskTreeDataProvider.refresh(); 
            if (axios.isAxiosError(error)) {
                const axiosError = error as AxiosError<any>; 
                const errorMessage = axiosError.response?.data?.detail || axiosError.message;
                const fullError = JSON.stringify(axiosError.toJSON(), null, 2);
                outputChannel.appendLine(`[ERROR] API Error updating task to ${statusText}: ${errorMessage}\n${fullError}`);
                vscode.window.showErrorMessage(`API Error updating task to ${statusText}: ${errorMessage}. Check MCP Task Manager Log for details.`);
            } else if (error instanceof Error) {
                outputChannel.appendLine(`[ERROR] Error updating task to ${statusText}: ${error.message}\n${error.stack}`);
                vscode.window.showErrorMessage(`Error updating task to ${statusText}: ${error.message}. Check MCP Task Manager Log for details.`);
            } else {
                outputChannel.appendLine(`[ERROR] An unexpected error occurred while updating the task to ${statusText}: ${JSON.stringify(error)}`);
                vscode.window.showErrorMessage(`An unexpected error occurred while updating the task to ${statusText}. Check MCP Task Manager Log for details.`);
            }
        }
    });
}

export function deactivate() {
    if (outputChannel) {
        outputChannel.appendLine('MCP Task Manager extension is now deactivated.');
        outputChannel.dispose();
    }
}
