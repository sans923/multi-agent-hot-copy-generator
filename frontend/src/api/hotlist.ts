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
