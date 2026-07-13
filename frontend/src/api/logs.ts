import { request } from "./client";
import type { AuditTrailResponse } from "../types/api";

export async function getAuditTrail(taskId: number, stepType?: string) {
  const params = new URLSearchParams({ task_id: String(taskId) });
  if (stepType) params.set("step_type", stepType);
  return request<AuditTrailResponse>(`/api/v1/logs/audit?${params}`);
}

export async function getAgentLogs(
  taskId: number,
  page = 1,
  pageSize = 50
) {
  const params = new URLSearchParams({
    task_id: String(taskId),
    page: String(page),
    page_size: String(pageSize),
  });
  return request<{
    items: unknown[];
    total: number;
  }>(`/api/v1/logs/agent?${params}`);
}
