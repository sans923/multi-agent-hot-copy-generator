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

export type TaskStatus = "pending" | "processing" | "completed" | "failed";
export type TaskPlatform =
  | "weibo"
  | "wechat"
  | "douyin"
  | "xiaohongshu"
  | "zhihu";

export interface Task {
  id: number;
  user_id: number;
  raw_requirement: string;
  platform: string;
  status: TaskStatus;
  parsed_requirement?: Record<string, unknown> | null;
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
  weibo: "微博",
  wechat: "微信公众号",
  douyin: "抖音",
  xiaohongshu: "小红书",
  zhihu: "知乎",
};

export const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: "等待中",
  processing: "生成中",
  completed: "已完成",
  failed: "失败",
};
