export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T | null;
}

export interface Pagination<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface User {
  id: number;
  username: string;
  email: string;
  nickname: string | null;
  avatar_url: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface TokenData {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export type TaskStatus =
  | "pending"
  | "processing"
  | "awaiting_human"
  | "completed"
  | "failed";
export type TaskPlatform =
  | "toutiao"
  | "weibo"
  | "wechat"
  | "douyin"
  | "xiaohongshu"
  | "zhihu";
export type ExecutionMode = "fast" | "plan";

export interface QualityGateMeta {
  passed?: boolean;
  action?: "finalize" | "rewrite" | "awaiting_human";
  failed_checks?: string[];
  reason?: string;
}

export interface OrchestrationMeta {
  execution_mode?: ExecutionMode;
  resolved_mode?: "fixed" | "agentic";
  task_mode?: string;
  plan_source?: string;
  plan_reasoning?: string;
  plan_steps?: Array<{
    step_id?: string;
    stage?: string;
    description?: string;
    can_skip?: boolean;
  }>;
  current_step?: number;
  step_count?: number;
  failure_level?: string;
  classify_reasons?: string[];
  verification?: Record<string, unknown>;
  awaiting_human?: boolean;
  human_prompt?: string;
  human_action?: string;
  quality_gate?: QualityGateMeta;
  decision_log?: Array<Record<string, unknown>>;
  skipped_steps?: Array<Record<string, unknown>>;
  selected_style_card_id?: number | null;
}

export interface ToutiaoReference {
  id: number;
  article_id: string;
  title: string;
  author_name: string | null;
  keyword: string | null;
  source_url: string | null;
  like_count: number;
  read_count: number;
  comment_count: number;
  embedding_status: string;
  chunk_count: number;
  content_length: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface StyleCard {
  id: number;
  topic_cluster: string;
  platform: string;
  pattern_json: Record<string, unknown>;
  avg_like_count: number;
  source_article_ids: string[];
  confidence: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface AuditLogItem {
  id: number;
  task_id: number;
  sequence_no: number;
  step_type: string;
  step_name: string;
  agent_name: string | null;
  input_summary: Record<string, unknown> | null;
  output_summary: Record<string, unknown> | null;
  status: string;
  failure_level: string | null;
  duration_ms: number | null;
  error_message: string | null;
  created_at: string | null;
}

export interface AuditTrailResponse {
  task_id: number;
  total: number;
  type_statistics: Record<string, number>;
  items: AuditLogItem[];
}

export interface Task {
  id: number;
  user_id: number;
  raw_requirement: string;
  platform: string;
  status: TaskStatus;
  parsed_requirement?: Record<string, unknown> | null;
  orchestration_meta?: OrchestrationMeta | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CopySummary {
  id: number;
  version: number;
  title: string | null;
  content: string;
  hashtags: string[] | null;
  review_score: number | null;
  is_final: boolean;
}

export interface TaskDetail extends Task {
  copies: CopySummary[];
}

export interface Copy {
  id: number;
  task_id: number;
  version: number;
  title: string | null;
  content: string;
  hashtags: string[] | null;
  platform: string | null;
  review_score: number | null;
  review_comment: string | null;
  is_final: boolean;
  tone: string | null;
  tokens_used: number;
  created_at: string;
}

export interface HotlistItem {
  id: number;
  source_platform: string;
  rank: number | null;
  title: string;
  description: string | null;
  hot_value: string | null;
  url: string | null;
  image_url: string | null;
  embedding_status: string;
  fetched_at: string;
}

export interface HotlistSearchResult {
  title: string;
  platform: string;
  rank: number;
  hot_value: string;
  similarity: number;
  distance: number;
}

export const PLATFORM_LABELS: Record<TaskPlatform, string> = {
  toutiao: "今日头条长文",
  weibo: "微博",
  wechat: "微信公众号",
  douyin: "抖音",
  xiaohongshu: "小红书",
  zhihu: "知乎",
};

export const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: "等待中",
  processing: "生成中",
  awaiting_human: "待人工处理",
  completed: "已完成",
  failed: "失败",
};
