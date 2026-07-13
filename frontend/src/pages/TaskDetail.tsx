import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getTask, resumeTask } from "../api/tasks";
import { AgentPipeline } from "../components/AgentPipeline";
import { AuditTimeline } from "../components/AuditTimeline";
import { useToast } from "../contexts/ToastContext";
import type { CopySummary, TaskDetail as TaskDetailType, TaskStatus } from "../types/api";
import { PLATFORM_LABELS, STATUS_LABELS } from "../types/api";
import { ApiError } from "../api/client";

const POLL_INTERVAL = 3000;
const TERMINAL: TaskStatus[] = ["completed", "failed"];

export function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const id = Number(taskId);
  const toast = useToast();
  const [task, setTask] = useState<TaskDetailType | null>(null);
  const [error, setError] = useState("");
  const [polling, setPolling] = useState(false);
  const [selectedCopyId, setSelectedCopyId] = useState<number | null>(null);
  const [resuming, setResuming] = useState(false);
  const [auditRefresh, setAuditRefresh] = useState(0);

  const load = useCallback(async () => {
    if (!id || Number.isNaN(id)) return;
    try {
      const res = await getTask(id);
      setTask(res.data);
      setAuditRefresh((n) => n + 1);
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
    if (task.status === "awaiting_human") {
      setPolling(false);
      return;
    }
    setPolling(true);
    const timer = setInterval(async () => {
      const data = await load();
      if (data && TERMINAL.includes(data.status)) {
        clearInterval(timer);
        setPolling(false);
        if (data.status === "completed") {
          toast.success("文案生成完成");
        }
      }
    }, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [task?.status, load, toast]);

  const handleResume = async (action: "retry" | "accept_draft" | "cancel") => {
    if (!id || Number.isNaN(id)) return;
    setResuming(true);
    try {
      await resumeTask(id, action);
      if (action === "cancel") {
        toast.info("任务已取消");
      } else if (action === "accept_draft") {
        toast.success("已接受初稿为终稿");
      } else {
        toast.info("任务已重新执行");
      }
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "操作失败");
    } finally {
      setResuming(false);
    }
  };

  const copyList = task?.copies ?? [];
  const finalCopy =
    copyList.find((c) => c.is_final) ?? copyList[copyList.length - 1];
  const displayCopy: CopySummary | undefined =
    copyList.find((c) => c.id === selectedCopyId) ?? finalCopy;

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("已复制到剪贴板");
    } catch {
      toast.error("复制失败，请手动选择文本");
    }
  };

  if (!task && !error) {
    return (
      <div className="page-center">
        <div className="spinner" />
        <p>加载任务…</p>
      </div>
    );
  }

  const parsed = task?.parsed_requirement as Record<string, unknown> | null;
  const orch = task?.orchestration_meta;

  const TASK_MODE_LABELS: Record<string, string> = {
    simple: "简单（固定流水线）",
    complex: "复杂（Plan&Execute）",
  };

  const FAILURE_LABELS: Record<string, string> = {
    retry: "自动重试中",
    local: "局部反思回退",
    human: "需人工介入",
    global: "全局失败",
  };

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
              平台：
              {PLATFORM_LABELS[
                task.platform as keyof typeof PLATFORM_LABELS
              ] ?? task.platform}
            </span>
            <span>
              创建：{new Date(task.created_at).toLocaleString("zh-CN")}
            </span>
          </div>

          {!TERMINAL.includes(task.status) && (
            <AgentPipeline status={task.status} />
          )}

          {orch && Object.keys(orch).length > 0 && (
            <section className="orchestration-box">
              <h3>编排信息（Agentic）</h3>
              <dl className="orchestration-grid">
                {orch.task_mode && (
                  <div>
                    <dt>任务分级</dt>
                    <dd>{TASK_MODE_LABELS[orch.task_mode] ?? orch.task_mode}</dd>
                  </div>
                )}
                {orch.plan_source && (
                  <div>
                    <dt>计划来源</dt>
                    <dd>{orch.plan_source}</dd>
                  </div>
                )}
                {orch.failure_level && (
                  <div>
                    <dt>失败级别</dt>
                    <dd>{FAILURE_LABELS[orch.failure_level] ?? orch.failure_level}</dd>
                  </div>
                )}
                {orch.step_count != null && (
                  <div>
                    <dt>已执行步数</dt>
                    <dd>{orch.step_count}</dd>
                  </div>
                )}
              </dl>
              {Array.isArray(orch.classify_reasons) &&
                orch.classify_reasons.length > 0 && (
                  <p className="page-desc" style={{ marginTop: "0.5rem" }}>
                    分级原因：{orch.classify_reasons.join("；")}
                  </p>
                )}
              {Array.isArray(orch.plan_steps) && orch.plan_steps.length > 0 && (
                <ol className="plan-steps-list">
                  {orch.plan_steps.map((s, i) => (
                    <li key={s.step_id ?? i}>
                      {s.stage}: {s.description || s.step_id}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          )}

          {task.status === "awaiting_human" && (
            <div className="alert alert-info">
              <strong>需要你的决定</strong>
              <p>{task.error_message || orch?.human_prompt || "验证未通过，请选择下一步操作。"}</p>
              <div className="human-actions">
                <button
                  type="button"
                  className="btn-primary"
                  disabled={resuming}
                  onClick={() => handleResume("retry")}
                >
                  重新执行
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={resuming}
                  onClick={() => handleResume("accept_draft")}
                >
                  接受当前初稿
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={resuming}
                  onClick={() => handleResume("cancel")}
                >
                  取消任务
                </button>
              </div>
            </div>
          )}

          {parsed && Object.keys(parsed).length > 0 && (
            <section className="parsed-box">
              <h3>需求解析结果</h3>
              <dl className="parsed-grid">
                {parsed.topic != null && (
                  <div>
                    <dt>主题</dt>
                    <dd>{String(parsed.topic)}</dd>
                  </div>
                )}
                {parsed.style != null && (
                  <div>
                    <dt>风格</dt>
                    <dd>{String(parsed.style)}</dd>
                  </div>
                )}
                {parsed.word_count != null && (
                  <div>
                    <dt>字数</dt>
                    <dd>{String(parsed.word_count)}</dd>
                  </div>
                )}
                {Array.isArray(parsed.keywords) && parsed.keywords.length > 0 && (
                  <div>
                    <dt>关键词</dt>
                    <dd>{(parsed.keywords as string[]).join("、")}</dd>
                  </div>
                )}
              </dl>
            </section>
          )}

          {task.status === "failed" && task.error_message && (
            <div className="alert alert-error">{task.error_message}</div>
          )}

          {(task.status === "pending" || task.status === "processing") && (
            <div className="alert alert-info">
              <div className="spinner spinner-sm" />
              三个 Agent 正在协作生成文案，通常需要 30–90 秒…
            </div>
          )}

          <AuditTimeline taskId={task.id} refreshKey={auditRefresh} />

          {displayCopy && (
            <article className="copy-result">
              <header className="copy-result-header">
                <h2>{displayCopy.title || "生成文案"}</h2>
                {displayCopy.review_score != null && (
                  <span className="score-badge">
                    评分 {displayCopy.review_score}
                  </span>
                )}
                {displayCopy.is_final && (
                  <span className="badge-final">终稿</span>
                )}
              </header>
              <pre className="copy-content">{displayCopy.content}</pre>
              {displayCopy.hashtags && displayCopy.hashtags.length > 0 && (
                <p className="copy-tags">
                  {displayCopy.hashtags.map((t) => `#${t}`).join(" ")}
                </p>
              )}
              <div className="copy-actions">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => handleCopy(displayCopy.content)}
                >
                  复制文案
                </button>
                <Link to="/create" className="btn-secondary">
                  再写一篇
                </Link>
              </div>
            </article>
          )}

          {copyList.length > 1 && (
            <section className="versions-section">
              <h3>所有版本 ({copyList.length})</h3>
              <ul className="version-list version-list-clickable">
                {copyList.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className={`version-btn ${selectedCopyId === c.id || (!selectedCopyId && c.id === finalCopy?.id) ? "active" : ""}`}
                      onClick={() => setSelectedCopyId(c.id)}
                    >
                      <span>v{c.version}</span>
                      {c.is_final && <span className="badge-final">终稿</span>}
                      {c.review_score != null && (
                        <span>评分 {c.review_score}</span>
                      )}
                      <span className="version-preview">
                        {c.content.slice(0, 40)}…
                      </span>
                    </button>
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
