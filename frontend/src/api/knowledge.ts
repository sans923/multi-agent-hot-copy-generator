import { request } from "./client";
import type { KnowledgeSearchItem, KnowledgeSource, KnowledgeType } from "../types/api";

export function listKnowledgeSources() {
  return request<KnowledgeSource[]>("/api/v1/knowledge/sources");
}

export function createKnowledgeSource(payload: {
  knowledge_type: KnowledgeType;
  title: string;
  content: string;
  source_uri?: string;
  valid_to?: string;
}) {
  return request<KnowledgeSource>("/api/v1/knowledge/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function searchKnowledge(query: string) {
  return request<{ items: KnowledgeSearchItem[]; citations: Array<Record<string, unknown>> }>(
    "/api/v1/knowledge/search",
    { method: "POST", body: JSON.stringify({ query, knowledge_types: [], limit: 8 }) },
  );
}
