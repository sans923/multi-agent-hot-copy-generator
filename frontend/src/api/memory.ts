import { request } from "./client";
import type { FeedbackAction, FeedbackResponse, MemoryInsights } from "../types/api";

export interface FeedbackPayload {
  task_id: number;
  copy_id: number;
  action: FeedbackAction;
  rating: -1 | 0 | 1;
  comment?: string;
  metrics?: Record<string, unknown>;
  idempotency_key: string;
  edited_title?: string;
  edited_content?: string;
}

export function submitFeedback(payload: FeedbackPayload) {
  return request<FeedbackResponse>("/api/v1/memory/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMemoryInsights() {
  return request<MemoryInsights>("/api/v1/memory/insights");
}
