import { request, setToken } from "./client";
import type { TokenData, User } from "../types/api";

export async function login(email: string, password: string) {
  const res = await request<TokenData>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (res.data?.access_token) {
    setToken(res.data.access_token);
  }
  return res;
}

export async function register(payload: {
  username: string;
  email: string;
  password: string;
  nickname?: string;
}) {
  return request<User>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchMe() {
  return request<User>("/api/v1/auth/me");
}

export function logout() {
  setToken(null);
}
