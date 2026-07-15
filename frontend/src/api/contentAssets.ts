import { request } from "./client";
import type { Pagination, StyleCard, ToutiaoReference } from "../types/api";

export function listReferences(page = 1, pageSize = 20, q = "") {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q.trim()) params.set("q", q.trim());
  return request<Pagination<ToutiaoReference>>(`/api/v1/content-assets/references?${params}`);
}

export function importReference(payload: {
  url: string;
  keyword: string;
  like_count?: number;
  read_count?: number;
  comment_count?: number;
}) {
  return request<ToutiaoReference>("/api/v1/content-assets/references", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function reindexReference(id: number) {
  return request<ToutiaoReference>(`/api/v1/content-assets/references/${id}/reindex`, {
    method: "POST",
  });
}

export function deleteReference(id: number) {
  return request<never>(`/api/v1/content-assets/references/${id}`, { method: "DELETE" });
}

export function listStyleCards() {
  return request<StyleCard[]>("/api/v1/content-assets/style-cards");
}

export function buildStyleCard(payload: { topic_cluster: string; reference_ids: number[] }) {
  return request<StyleCard>("/api/v1/content-assets/style-cards", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteStyleCard(id: number) {
  return request<never>(`/api/v1/content-assets/style-cards/${id}`, { method: "DELETE" });
}
