import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getTask, preparePublication, resumeTask } from "../api/tasks";
import { AgentPipeline } from "../components/AgentPipeline";
import { AuditTimeline } from "../components/AuditTimeline";
import { useToast } from "../contexts/ToastContext";
import type {
  CopySummary,
  PublishMediaType,
  TaskDetail as TaskDetailType,
  TaskStatus,
} from "../types/api";
import { PLATFORM_LABELS, STATUS_LABELS } from "../types/api";
import { ApiError } from "../api/client";
import { openExternalApp } from "../utils/externalNavigation";

const POLL_INTERVAL = 3000;
const TERMINAL: TaskStatus[] = ["completed", "failed"];

async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(textarea);
    if (!copied) throw new Error("clipboard unavailable");
  }
}

interface LongformBrief {
  target_reader?: string;
  content_goal?: string;
  primary_keyword?: string;
  secondary_keywords?: string[];
  reader_questions?: string[];
  article_angle?: string;
  tone?: string;
  target_word_count?: number;
}

interface LongformOutline {
  selected_title?: string;
  opening_strategy?: string;
  sections?: Array<{
    id: string;
    heading: string;
    goal: string;
    target_words?: number;
  }>;
}

interface LongformQuality {
  total_score?: number;
  grade?: string;
  dimensions?: Array<{ name: string; score: number }>;
  strengths?: string[];
  suggestions?: string[];
  failed_sections?: Array<{
    section_id: string;
    score: number;
    reason: string;
    rewrite_instruction: string;
  }>;
}

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
  const [preparingPlatform, setPreparingPlatform] = useState<
    "toutiao" | "douyin" | null
  >(null);
  const [douyinMediaUrl, setDouyinMediaUrl] = useState("");
  const [douyinMediaType, setDouyinMediaType] =
    useState<PublishMediaType>("image");
  const [publishBlockers, setPublishBlockers] = useState<string[]>([]);
  const [fallbackCreatorUrl, setFallbackCreatorUrl] = useState<string | null>(null);

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
      await copyToClipboard(text);
      toast.success("已复制到剪贴板");
    } catch {
      toast.error("复制失败，请手动选择文本");
    }
  };

  const handleToutiaoPublish = async () => {
    if (!id || Number.isNaN(id) || !displayCopy?.is_final) return;
    const creatorWindow = window.open("about:blank", "_blank");
    if (creatorWindow) creatorWindow.opener = null;
    setPreparingPlatform("toutiao");
    setPublishBlockers([]);
    setFallbackCreatorUrl(null);
    try {
      const response = await preparePublication(id, {
        platform: "toutiao",
        copy_id: displayCopy.id,
      });
      setAuditRefresh((n) => n + 1);
      const preparation = response.data;
      if (!preparation?.ready || !preparation.creator_url) {
        creatorWindow?.close();
        setPublishBlockers(preparation?.blockers ?? ["头条发布包暂不可用"]);
        return;
      }
      await copyToClipboard(preparation.package_text);
      if (creatorWindow) {
        creatorWindow.location.href = preparation.creator_url;
        toast.success("发布包已复制，请在头条创作页确认排版并发布");
      } else {
        setFallbackCreatorUrl(preparation.creator_url);
        setPublishBlockers(["浏览器拦截了新窗口，请点击下方安全链接打开头条创作页"]);
        toast.info("发布包已复制，但浏览器拦截了新窗口");
      }
    } catch (e) {
      creatorWindow?.close();
      toast.error(e instanceof ApiError ? e.message : "头条发布准备失败");
    } finally {
      setPreparingPlatform(null);
    }
  };

  const handleDouyinPublish = async () => {
    if (!id || Number.isNaN(id) || !displayCopy?.is_final) return;
    if (!douyinMediaUrl.trim()) {
      setPublishBlockers(["请先填写一个公网 HTTPS 图片或视频地址"]);
      return;
    }
    setPreparingPlatform("douyin");
    setPublishBlockers([]);
    setFallbackCreatorUrl(null);
    try {
      const response = await preparePublication(id, {
        platform: "douyin",
        copy_id: displayCopy.id,
        media_url: douyinMediaUrl.trim(),
        media_type: douyinMediaType,
      });
      setAuditRefresh((n) => n + 1);
      const preparation = response.data;
      if (!preparation?.ready || !preparation.launch_url) {
        setPublishBlockers(preparation?.blockers ?? ["抖音投稿能力暂不可用"]);
        return;
      }
      await copyToClipboard(preparation.package_text);
      toast.info("正在拉起抖音发布器；仍需由你本人确认发布");
      openExternalApp(preparation.launch_url);
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "抖音投稿准备失败";
      setPublishBlockers([message]);
      toast.error(message);
    } finally {
      setPreparingPlatform(null);
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
  const contentBrief = parsed?.content_brief as LongformBrief | undefined;
  const articleOutline = parsed?.article_outline as LongformOutline | undefined;
  const longformMeta = parsed?.longform_mvp as
    | { rewrite_count?: number; quality_report?: LongformQuality }
    | undefined;
  const qualityReport = longformMeta?.quality_report;
  const qualityGate = orch?.quality_gate;
  const decisionLog = orch?.decision_log ?? [];

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
                {orch.execution_mode && (
                  <div>
                    <dt>执行模式</dt>
                    <dd>{orch.execution_mode === "plan" ? "Plan · 动态编排" : "Fast · 固定流水线"}</dd>
                  </div>
                )}
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
              {qualityGate && Object.keys(qualityGate).length > 0 && (
                <div className={`gate-summary ${qualityGate.passed ? "passed" : "blocked"}`}>
                  <strong>
                    最终质量门控：{qualityGate.passed ? "已通过" : "未通过"}
                  </strong>
                  <span>
                    决策 {qualityGate.action}
                    {(qualityGate.failed_checks ?? []).length > 0
                      ? ` · 未通过项：${qualityGate.failed_checks?.join("、")}`
                      : ""}
                  </span>
                </div>
              )}
              {decisionLog.length > 0 && (
                <details className="decision-log">
                  <summary>查看 Lead 决策记录（{decisionLog.length}）</summary>
                  <ol>
                    {decisionLog.map((item, index) => (
                      <li key={index}>
                        {String(item.type ?? "decision")}
                        {item.reason ? `：${String(item.reason)}` : ""}
                      </li>
                    ))}
                  </ol>
                </details>
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

          {contentBrief && articleOutline && (
            <section className="longform-panel">
              <div className="longform-panel-header">
                <div>
                  <span className="longform-kicker">Content Brief</span>
                  <h3>{articleOutline.selected_title || String(parsed?.topic || "长文规划")}</h3>
                </div>
                <span className="score-badge">
                  目标 {contentBrief.target_word_count ?? "—"} 字
                </span>
              </div>

              <dl className="longform-brief-grid">
                <div>
                  <dt>目标读者</dt>
                  <dd>{contentBrief.target_reader}</dd>
                </div>
                <div>
                  <dt>内容目标</dt>
                  <dd>{contentBrief.content_goal}</dd>
                </div>
                <div>
                  <dt>核心关键词</dt>
                  <dd>
                    {[contentBrief.primary_keyword, ...(contentBrief.secondary_keywords ?? [])]
                      .filter(Boolean)
                      .join("、")}
                  </dd>
                </div>
                <div>
                  <dt>写作角度</dt>
                  <dd>{contentBrief.article_angle}</dd>
                </div>
              </dl>

              <div className="outline-list">
                {(articleOutline.sections ?? []).map((section, index) => (
                  <div className="outline-item" key={section.id}>
                    <span className="outline-index">{index + 1}</span>
                    <div>
                      <strong>{section.heading}</strong>
                      <p>{section.goal}</p>
                    </div>
                    {section.target_words != null && (
                      <span className="outline-words">约 {section.target_words} 字</span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {qualityReport && (
            <section className="longform-panel">
              <div className="longform-panel-header">
                <div>
                  <span className="longform-kicker">Quality Gate</span>
                  <h3>长文质量报告</h3>
                </div>
                <span className="score-badge">
                  {qualityReport.total_score ?? 0} 分 · 重写 {longformMeta?.rewrite_count ?? 0}/1
                </span>
              </div>

              <div className="quality-grid">
                {(qualityReport.dimensions ?? []).map((dimension) => (
                  <div className="quality-item" key={dimension.name}>
                    <div>
                      <span>{dimension.name}</span>
                      <strong>{dimension.score}</strong>
                    </div>
                    <div className="quality-track">
                      <span style={{ width: `${Math.max(0, Math.min(100, dimension.score))}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              {(qualityReport.failed_sections ?? []).length > 0 && (
                <div className="rewrite-list">
                  <strong>定向重写记录</strong>
                  {(qualityReport.failed_sections ?? []).map((section) => (
                    <p key={section.section_id}>
                      <span>{section.section_id} · {section.score}分</span>
                      {section.reason}；{section.rewrite_instruction}
                    </p>
                  ))}
                </div>
              )}
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
            <>
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

            {displayCopy.is_final && (
              <section
                className="publish-panel"
                aria-labelledby="publish-heading"
              >
                <header className="publish-panel-header">
                  <div>
                    <span>Publish handoff</span>
                    <h2 id="publish-heading">把终稿交给平台</h2>
                  </div>
                  <p>系统只负责准备与拉起；最终发布必须由账号本人确认。</p>
                </header>

                {publishBlockers.length > 0 && (
                  <div className="publish-blockers" role="alert">
                    <strong>当前还不能继续</strong>
                    <ul>
                      {publishBlockers.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                    {fallbackCreatorUrl && (
                      <a
                        className="btn-secondary"
                        href={fallbackCreatorUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        手动打开头条创作页
                      </a>
                    )}
                  </div>
                )}

                <div className="publish-options">
                  <article className="publish-option toutiao-option">
                    <span className="publish-option-index">01</span>
                    <div>
                      <h3>今日头条长文</h3>
                      <p>复制标题、正文和标签，并打开头条图文创作页。</p>
                    </div>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={preparingPlatform !== null}
                      onClick={handleToutiaoPublish}
                    >
                      {preparingPlatform === "toutiao" ? "准备中…" : "复制并打开头条"}
                    </button>
                  </article>

                  <article className="publish-option douyin-option">
                    <span className="publish-option-index">02</span>
                    <div>
                      <h3>抖音用户确认投稿</h3>
                      <p>使用公网素材生成安全 H5 投稿链接，并在手机端拉起抖音发布器。</p>
                    </div>
                    <div className="publish-media-fields">
                      <label>
                        素材类型
                        <select
                          value={douyinMediaType}
                          onChange={(event) =>
                            setDouyinMediaType(
                              event.target.value as PublishMediaType
                            )
                          }
                        >
                          <option value="image">图片</option>
                          <option value="video">视频</option>
                        </select>
                      </label>
                      <label>
                        公网 HTTPS 素材地址
                        <input
                          type="url"
                          inputMode="url"
                          placeholder="https://cdn.example.com/content.jpg"
                          value={douyinMediaUrl}
                          onChange={(event) => setDouyinMediaUrl(event.target.value)}
                        />
                      </label>
                    </div>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={preparingPlatform !== null}
                      onClick={handleDouyinPublish}
                    >
                      {preparingPlatform === "douyin" ? "生成投稿链接…" : "拉起抖音发布器"}
                    </button>
                    <small>
                      需先获批 h5.share、open.get.ticket 和
                      aweme.share；拉起不等于发布成功。
                    </small>
                  </article>
                </div>
              </section>
            )}
            </>
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
