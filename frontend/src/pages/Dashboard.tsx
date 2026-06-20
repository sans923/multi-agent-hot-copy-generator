import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listTasks } from "../api/tasks";
import type { Task, TaskStatus, TaskPlatform } from "../types/api";
import { PLATFORM_LABELS, STATUS_LABELS } from "../types/api";
import { ApiError } from "../api/client";

export function Dashboard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listTasks(1, 10)
      .then((res) => setTasks(res.data?.items ?? []))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "加载失败")
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>工作台</h1>
          <p className="page-desc">查看最近的文案生成任务</p>
        </div>
        <Link to="/create" className="btn-primary">
          + 新建任务
        </Link>
      </div>

      {loading && <p className="muted">加载中…</p>}
      {error && <p className="form-error">{error}</p>}

      {!loading && tasks.length === 0 && (
        <div className="empty-card">
          <p>还没有任务，去生成第一篇爆款文案吧</p>
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
    </div>
  );
}
