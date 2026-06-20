import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getTask } from "../api/tasks";
import type { TaskDetail as TaskDetailType, TaskStatus } from "../types/api";
import { PLATFORM_LABELS, STATUS_LABELS } from "../types/api";
import { ApiError } from "../api/client";

const POLL_INTERVAL = 3000;
const TERMINAL: TaskStatus[] = ["completed", "failed"];

export function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const id = Number(taskId);
  const [task, setTask] = useState<TaskDetailType | null>(null);
  const [error, setError] = useState("");
  const [polling, setPolling] = useState(false);

  const load = useCallback(async () => {
    if (!id || Number.isNaN(id)) return;
    try {
      const res = await getTask(id);
      setTask(res.data);
      setError("");
      return res.data;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载失败");
      return null;
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!task || TERMINAL.includes(task.status)) {
      setPolling(false);
      return;
    }
    setPolling(true);
    const timer = setInterval(async () => {
      const data = await load();
      if (data && TERMINAL.includes(data.status)) {
        clearInterval(timer);
        setPolling(false);
      }
    }, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [task?.status, load]);

  if (!task && !error) {
    return (
      <div className="page-center">
        <div className="spinner" />
        <p>加载任务…</p>
      </div>
    );
  }

  const finalCopy =
    task?.copies?.find((c) => c.is_final) ??
    task?.copies?.[task.copies.length - 1];

  return (
    <div className="page">
      <Link to="/" className="back-link">
        ← 返回工作台
      </Link>

      {error && <p className="form-error">{error}</p>}

      {task && (
        <>
          <div className="page-header">
            <div>
              <h1>任务 #{task.id}</h1>
              <p className="page-desc">{task.raw_requirement}</p>
            </div>
            <span className={`status-pill status-${task.status} status-lg`}>
              {STATUS_LABELS[task.status]}
              {polling && " · 刷新中"}
            </span>
          </div>

          <div className="meta-row">
            <span>
              平台：{PLATFORM_LABELS[task.platform as keyof typeof PLATFORM_LABELS] ?? task.platform}
            </span>
            <span>
              创建：{new Date(task.created_at).toLocaleString("zh-CN")}
            </span>
          </div>

          {task.status === "failed" && task.error_message && (
            <div className="alert alert-error">{task.error_message}</div>
          )}

          {(task.status === "pending" || task.status === "processing") && (
            <div className="alert alert-info">
              <div className="spinner spinner-sm" />
              三个 Agent 正在协作生成文案，通常需要 30–90 秒…
            </div>
          )}

          {finalCopy && (
            <article className="copy-result">
              <header className="copy-result-header">
                <h2>{finalCopy.title || "生成文案"}</h2>
                {finalCopy.review_score != null && (
                  <span className="score-badge">
                    评分 {finalCopy.review_score}
                  </span>
                )}
                {finalCopy.is_final && (
                  <span className="badge-final">终稿</span>
                )}
              </header>
              <pre className="copy-content">{finalCopy.content}</pre>
              {finalCopy.hashtags && finalCopy.hashtags.length > 0 && (
                <p className="copy-tags">
                  {finalCopy.hashtags.map((t) => `#${t}`).join(" ")}
                </p>
              )}
              <button
                type="button"
                className="btn-secondary"
                onClick={() =>
                  navigator.clipboard.writeText(finalCopy.content)
                }
              >
                复制文案
              </button>
            </article>
          )}

          {task.copies && task.copies.length > 1 && (
            <section className="versions-section">
              <h3>所有版本 ({task.copies.length})</h3>
              <ul className="version-list">
                {task.copies.map((c) => (
                  <li key={c.id}>
                    <span>v{c.version}</span>
                    {c.is_final && <span className="badge-final">终稿</span>}
                    {c.review_score != null && (
                      <span>评分 {c.review_score}</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
