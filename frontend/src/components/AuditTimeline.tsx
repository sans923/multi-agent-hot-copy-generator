import { useCallback, useEffect, useState } from "react";
import { getAuditTrail } from "../api/logs";
import type { AuditLogItem } from "../types/api";
import { ApiError } from "../api/client";

const STEP_TYPE_LABELS: Record<string, string> = {
  orchestration: "编排",
  stage: "流水线阶段",
  skill: "Skill",
  llm: "LLM",
  verify: "规则验证",
  judge: "Judge",
  human: "人工介入",
  system: "系统",
};

const STATUS_CLASS: Record<string, string> = {
  success: "audit-status-ok",
  failed: "audit-status-fail",
  retry: "audit-status-retry",
  skipped: "audit-status-skip",
};

interface AuditTimelineProps {
  taskId: number;
  refreshKey?: string | number;
}

export function AuditTimeline({ taskId, refreshKey }: AuditTimelineProps) {
  const [items, setItems] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const res = await getAuditTrail(taskId);
      setItems(res.data?.items ?? []);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载审计日志失败");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  if (loading) {
    return (
      <section className="audit-timeline">
        <h3>执行轨迹</h3>
        <p className="page-desc">加载审计日志…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="audit-timeline">
        <h3>执行轨迹</h3>
        <p className="form-error">{error}</p>
      </section>
    );
  }

  if (items.length === 0) {
    return (
      <section className="audit-timeline">
        <h3>执行轨迹</h3>
        <p className="page-desc">暂无审计记录（任务开始执行后会出现）。</p>
      </section>
    );
  }

  return (
    <section className="audit-timeline">
      <h3>执行轨迹（{items.length} 步）</h3>
      <ol className="audit-list">
        {items.map((item) => (
          <li key={item.id} className="audit-item">
            <div className="audit-item-header">
              <span className="audit-seq">#{item.sequence_no}</span>
              <span className="audit-type">
                {STEP_TYPE_LABELS[item.step_type] ?? item.step_type}
              </span>
              <strong className="audit-name">{item.step_name}</strong>
              <span
                className={`audit-status ${STATUS_CLASS[item.status] ?? ""}`}
              >
                {item.status}
              </span>
              {item.duration_ms != null && (
                <span className="audit-duration">{item.duration_ms}ms</span>
              )}
            </div>
            {item.agent_name && (
              <div className="audit-meta">Agent: {item.agent_name}</div>
            )}
            {item.failure_level && (
              <div className="audit-meta">失败级别: {item.failure_level}</div>
            )}
            {item.error_message && (
              <div className="audit-error">{item.error_message}</div>
            )}
            {item.output_summary && (
              <details className="audit-details">
                <summary>输出摘要</summary>
                <pre>{JSON.stringify(item.output_summary, null, 2)}</pre>
              </details>
            )}
            <time className="audit-time">
              {item.created_at
                ? new Date(item.created_at).toLocaleString("zh-CN")
                : ""}
            </time>
          </li>
        ))}
      </ol>
    </section>
  );
}
