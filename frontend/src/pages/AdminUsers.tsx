import { useEffect, useState } from "react";
import { listUsers } from "../api/users";
import type { User } from "../types/api";
import { ApiError } from "../api/client";

export function AdminUsers() {
  const [users, setUsers] = useState<User[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    listUsers(page, 15)
      .then((res) => {
        setUsers(res.data?.items ?? []);
        setTotalPages(res.data?.total_pages ?? 1);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "加载失败")
      )
      .finally(() => setLoading(false));
  }, [page]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>用户管理</h1>
          <p className="page-desc">管理员查看系统注册用户</p>
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}
      {loading && <p className="muted">加载中…</p>}

      {!loading && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>用户名</th>
                <th>邮箱</th>
                <th>昵称</th>
                <th>角色</th>
                <th>注册时间</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.id}</td>
                  <td>{u.username}</td>
                  <td>{u.email}</td>
                  <td>{u.nickname ?? "—"}</td>
                  <td>{u.is_admin ? "管理员" : "用户"}</td>
                  <td>
                    {new Date(u.created_at).toLocaleDateString("zh-CN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="pagination">
          <button
            type="button"
            className="btn-secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页
          </button>
          <span className="muted">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="btn-secondary"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
