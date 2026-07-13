import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listTasks } from "../api/tasks";
import type { Task, TaskStatus, TaskPlatform } from "../types/api";
import { PLATFORM_LABELS, STATUS_LABELS } from "../types/api";
import { ApiError } from "../api/client";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "全部" },
  { value: "pending", label: "等待中" },
  { value: "processing", label: "生成中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
];

const PAGE_SIZE = 12;

export function Dashboard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listTasks(
        page,
        PAGE_SIZE,
        statusFilter || undefined
      );
      setTasks(res.data?.items ?? []);
      setTotal(res.data?.total ?? 0);
      setTotalPages(res.data?.total_pages ?? 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const stats = {
    completed: tasks.filter((t) => t.status === "completed").length,
    running: tasks.filter(
      (t) => t.status === "pending" || t.status === "processing"
    ).length,
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>工作台</h1>
          <p className="page-desc">
            共 {total} 个任务
            {!loading && total > 0 && (
              <>
                {" "}
                · 本页 {stats.running} 个进行中
              </>
            )}
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={load}
            disabled={loading}
          >
            刷新
          </button>
          <Link to="/create" className="btn-primary">
            + 新建任务
          </Link>
        </div>
      </div>

      <div className="filter-tabs">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value || "all"}
            type="button"
            className={`filter-tab ${statusFilter === f.value ? "active" : ""}`}
            onClick={() => {
              setStatusFilter(f.value);
              setPage(1);
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="page-center page-center-sm">
          <div className="spinner" />
        </div>
      )}
      {error && <p className="form-error">{error}</p>}

      {!loading && tasks.length === 0 && (
        <div className="empty-card">
          <p>
            {statusFilter
              ? "没有符合筛选条件的任务"
              : "还没有任务，去生成第一篇爆款文案吧"}
          </p>
          <Link to="/create" className="btn-primary">
            开始生成
          </Link>
        </div>
      )}

      <div className="task-grid">
        {tasks.map((task) => (
          <Link key={task.id} to={`/tasks/${task.id}`} className="task-card">
            <div className="task-card-top">
              <span className={`status-pill status-${task.status}`}>
                {STATUS_LABELS[task.status as TaskStatus] ?? task.status}
              </span>
              <span className="platform-tag">
                {PLATFORM_LABELS[task.platform as TaskPlatform] ??
                  task.platform}
              </span>
            </div>
            <p className="task-requirement">{task.raw_requirement}</p>
            <time className="task-time">
              {new Date(task.created_at).toLocaleString("zh-CN")}
            </time>
          </Link>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button
            type="button"
            className="btn-secondary"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页
          </button>
          <span className="muted">
            第 {page} / {totalPages} 页
          </span>
          <button
            type="button"
            className="btn-secondary"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
