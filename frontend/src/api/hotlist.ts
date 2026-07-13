import { request } from "./client";
import type { HotlistItem, HotlistSearchResult, Pagination } from "../types/api";

export async function listHotlist(page = 1, pageSize = 20) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return request<Pagination<HotlistItem>>(`/api/v1/hotlist/?${params}`);
}

export async function searchHotlist(query: string, nResults = 8) {
  const params = new URLSearchParams({
    query,
    n_results: String(nResults),
  });
  return request<HotlistSearchResult[]>(`/api/v1/hotlist/search?${params}`);
}

export async function triggerHotlistSync() {
  return request<{ triggered_by: string }>("/api/v1/hotlist/sync", {
    method: "POST",
  });
}

export async function getHotlistStats() {
  return request<{
    active_by_platform: Record<string, number>;
    pending_embedding: number;
    latest_sync_time: string | null;
    total_historical_records: number;
  }>("/api/v1/hotlist/stats");
}
