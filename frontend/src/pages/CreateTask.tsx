import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { createTask } from "../api/tasks";
import { listHotlist } from "../api/hotlist";
import type { ExecutionMode, HotlistItem, TaskPlatform } from "../types/api";
import { PLATFORM_LABELS } from "../types/api";
import { ApiError } from "../api/client";
import { listStyleCards } from "../api/contentAssets";
import type { StyleCard } from "../types/api";

const PLATFORMS = Object.keys(PLATFORM_LABELS) as TaskPlatform[];

export function CreateTask() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const hotlistFromUrl = searchParams.get("hotlist_id");
  const titleFromUrl = searchParams.get("title");

  const [requirement, setRequirement] = useState(
    titleFromUrl
      ? `围绕热点「${decodeURIComponent(titleFromUrl)}」写一篇爆款文案，风格口语化，要蹭热度`
      : "围绕35岁程序员职业转型，写一篇约2000字的今日头条深度长文，理性、有共情，并给出可执行建议"
  );
  const [platform, setPlatform] = useState<TaskPlatform>("toutiao");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("plan");
  const [styleCardId, setStyleCardId] = useState<number | null>(null);
  const [styleCards, setStyleCards] = useState<StyleCard[]>([]);
  const [hotlistId, setHotlistId] = useState<number | null>(
    hotlistFromUrl ? Number(hotlistFromUrl) : null
  );
  const [hotlist, setHotlist] = useState<HotlistItem[]>([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listHotlist(1, 30)
      .then((res) => setHotlist(res.data?.items ?? []))
      .catch(() => setHotlist([]));
  }, []);

  useEffect(() => {
    listStyleCards()
      .then((res) => setStyleCards(res.data ?? []))
      .catch(() => setStyleCards([]));
  }, []);

  useEffect(() => {
    if (hotlistFromUrl) {
      setHotlistId(Number(hotlistFromUrl));
    }
  }, [hotlistFromUrl]);

  const selectedHot = hotlist.find((h) => h.id === hotlistId);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const res = await createTask({
        raw_requirement: requirement,
        platform,
        hotlist_id: hotlistId,
        execution_mode: executionMode,
        style_card_id: platform === "toutiao" ? styleCardId : null,
      });
      if (res.data?.id) {
        navigate(`/tasks/${res.data.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page page-narrow">
      <div className="page-header">
        <div>
          <h1>生成文案</h1>
          <p className="page-desc">
            AI 流水线将依次完成需求分析、长文规划、分节创作与质量审核
          </p>
        </div>
      </div>

      {selectedHot && (
        <div className="alert alert-info hot-picked">
          已关联热点：<strong>{selectedHot.title}</strong>
          <button
            type="button"
            className="btn-ghost btn-sm"
            onClick={() => setHotlistId(null)}
          >
            取消关联
          </button>
        </div>
      )}

      <form className="form-card" onSubmit={handleSubmit}>
        <label>
          文案需求
          <textarea
            value={requirement}
            onChange={(e) => setRequirement(e.target.value)}
            rows={6}
            required
            minLength={5}
            maxLength={1000}
            placeholder="描述主题、风格、字数、是否要蹭热点…"
          />
          <span className="char-count">{requirement.length} / 1000</span>
        </label>

        <div className="platform-picker">
          <span className="picker-label">目标平台</span>
          <div className="platform-options">
            {PLATFORMS.map((p) => (
              <button
                key={p}
                type="button"
                className={`platform-option ${platform === p ? "active" : ""}`}
                onClick={() => setPlatform(p)}
              >
                {PLATFORM_LABELS[p]}
              </button>
            ))}
          </div>
        </div>

        <div className="mode-picker">
          <span className="picker-label">执行模式</span>
          <div className="mode-options">
            <button
              type="button"
              className={`mode-option ${executionMode === "fast" ? "active" : ""}`}
              onClick={() => setExecutionMode("fast")}
            >
              <strong>Fast</strong>
              <span>固定流水线，速度快、成本低</span>
            </button>
            <button
              type="button"
              className={`mode-option ${executionMode === "plan" ? "active" : ""}`}
              onClick={() => setExecutionMode("plan")}
            >
              <strong>Plan</strong>
              <span>动态规划、受控重试、最终质量门控</span>
            </button>
          </div>
        </div>

        {platform === "toutiao" && (
          <label>
            指定风格卡（可选）
            <select
              value={styleCardId ?? ""}
              onChange={(e) => setStyleCardId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">由 Agent 按话题自动匹配</option>
              {styleCards.map((card) => (
                <option key={card.id} value={card.id}>
                  {card.topic_cluster} · 置信度 {Math.round(card.confidence * 100)}%
                </option>
              ))}
            </select>
            <span className="field-help">
              指定后，Copywriter 将优先使用该卡片的标题公式、结构与节奏规则。
            </span>
          </label>
        )}

        <label>
          关联热榜（可选）
          <select
            value={hotlistId ?? ""}
            onChange={(e) =>
              setHotlistId(e.target.value ? Number(e.target.value) : null)
            }
          >
            <option value="">不指定，由 AI 自动匹配热点</option>
            {hotlist.map((item) => (
              <option key={item.id} value={item.id}>
                #{item.rank} {item.title}
                {item.hot_value ? ` (${item.hot_value})` : ""}
              </option>
            ))}
          </select>
        </label>

        {error && <p className="form-error">{error}</p>}

        <button
          type="submit"
          className="btn-primary btn-lg"
          disabled={submitting}
        >
          {submitting ? "提交中…" : "开始生成"}
        </button>
      </form>

      <p className="form-hint">
        没有合适的热点？去{" "}
        <Link to="/hotlist">热榜页</Link> 浏览或语义搜索
      </p>
    </div>
  );
}
