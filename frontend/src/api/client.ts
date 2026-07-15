import type { ApiResponse } from "../types/api";

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(message: string, status: number, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function getToken(): string | null {
  return localStorage.getItem("access_token");
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem("access_token", token);
  } else {
    localStorage.removeItem("access_token");
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 204) {
    return { success: true, message: "操作成功", data: null };
  }

  let body: ApiResponse<T> | { detail?: string | unknown };
  try {
    body = await res.json();
  } catch {
    throw new ApiError("服务器响应异常", res.status);
  }

  if (res.status === 401 && !path.includes("/auth/login")) {
    setToken(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`;
    }
  }

  if (!res.ok) {
    const detail =
      typeof (body as { detail?: unknown }).detail === "string"
        ? (body as { detail: string }).detail
        : Array.isArray((body as { detail?: unknown }).detail)
          ? JSON.stringify((body as { detail: unknown[] }).detail)
          : (body as ApiResponse<T>).message;
    throw new ApiError(
      detail || `请求失败 (${res.status})`,
      res.status,
      typeof detail === "string" ? detail : undefined
    );
  }

  const apiBody = body as ApiResponse<T>;
  if (!apiBody.success && apiBody.message) {
    throw new ApiError(apiBody.message, res.status);
  }

  return apiBody;
}
