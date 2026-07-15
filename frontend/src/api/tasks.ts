import { request } from "./client";
import type {
  Copy,
  Pagination,
  Task,
  TaskDetail,
  TaskPlatform,
  ExecutionMode,
} from "../types/api";

export async function createTask(payload: {
  raw_requirement: string;
  platform: TaskPlatform;
  hotlist_id?: number | null;
  execution_mode?: ExecutionMode;
  style_card_id?: number | null;
}) {
  return request<Task>("/api/v1/tasks/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listTasks(page = 1, pageSize = 20, statusFilter?: string) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (statusFilter) params.set("status_filter", statusFilter);
  return request<Pagination<Task>>(`/api/v1/tasks/?${params}`);
}

export async function getTask(taskId: number) {
  return request<TaskDetail>(`/api/v1/tasks/${taskId}`);
}

export async function getTaskCopies(taskId: number) {
  return request<Copy[]>(`/api/v1/tasks/${taskId}/copies`);
}

export async function resumeTask(
  taskId: number,
  action: "retry" | "accept_draft" | "cancel"
) {
  return request<Task>(`/api/v1/tasks/${taskId}/resume`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}
