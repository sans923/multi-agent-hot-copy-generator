import { request } from "./client";
import type { Pagination, User } from "../types/api";

export async function getMyProfile() {
  return request<User>("/api/v1/users/me");
}

export async function updateMyProfile(payload: {
  nickname?: string;
  password?: string;
}) {
  return request<User>("/api/v1/users/me", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function listUsers(page = 1, pageSize = 20) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return request<Pagination<User>>(`/api/v1/users/?${params}`);
}
