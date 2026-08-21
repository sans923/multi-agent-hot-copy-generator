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
export type ExecutionStatus = "queued" | "running" | "paused" | "succeeded" | "failed" | "cancelled";
export type ContentStatus = "brief_missing" | "brief_ready" | "drafting" | "in_review" | "changes_requested" | "approved";
export type PublicationStatus = "not_prepared" | "blocked" | "ready" | "submitted" | "published" | "failed";

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
  execution_status: ExecutionStatus;
  content_status: ContentStatus;
  publication_status: PublicationStatus;
  status_reason?: string | null;
  status_updated_at: string;
  content_brief?: ContentBrief | null;
  brief_completeness?: number;
  brief_missing_fields?: string[] | null;
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
  parent_copy_id?: number | null;
  user_edited?: boolean;
  applied_style_snapshot?: Record<string, unknown> | null;
  knowledge_citations?: KnowledgeCitation[] | null;
  change_summary?: Record<string, unknown> | null;
}

export interface ContentBrief {
  topic?: string;
  audience?: string;
  goal?: string;
  key_points?: string[];
  constraints?: Record<string, unknown>;
}

export interface KnowledgeCitation {
  source_id: number;
  chunk_id: number;
  title: string;
  source_uri?: string | null;
  version: number;
}

export type FeedbackAction = "accepted" | "rejected" | "edited" | "published";

export interface FeedbackResponse {
  id: number;
  task_id: number;
  copy_id: number;
  result_copy_id: number | null;
  action: FeedbackAction;
  rating: number;
  comment: string | null;
  metrics: Record<string, unknown>;
  idempotency_key: string;
  created_at: string;
}

export type KnowledgeType = "brand_fact" | "product_fact" | "campaign_material" | "platform_rule" | "external_reference";

export interface KnowledgeSource {
  id: number;
  user_id: number | null;
  knowledge_type: KnowledgeType;
  title: string;
  source_uri: string | null;
  status: string;
  version: number;
  metadata: Record<string, unknown>;
  valid_from: string | null;
  valid_to: string | null;
  index_status: string;
  created_at: string;
}

export interface KnowledgeSearchItem {
  source_id: number;
  chunk_id: number;
  knowledge_type: KnowledgeType;
  content: string;
  score: number;
  citation: KnowledgeCitation;
}

export interface MemoryInsights {
  feedback: { total: number; adoption_rate: number; edit_rate: number; rejection_rate: number };
  publication: { total: number; metrics: Record<string, number> };
  memory: { active_inferred_preferences: number };
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

export type PublishPlatform = "toutiao" | "douyin";
export type PublishMediaType = "image" | "video";

export interface PublishPreparation {
  platform: PublishPlatform;
  mode: "assisted_export" | "user_confirmed_post";
  ready: boolean;
  requires_user_confirmation: boolean;
  copy_id: number;
  title: string;
  content: string;
  hashtags: string[];
  package_text: string;
  creator_url: string | null;
  launch_url: string | null;
  media_url: string | null;
  media_type: PublishMediaType | null;
  blockers: string[];
  instructions: string[];
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
