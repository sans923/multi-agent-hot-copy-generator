import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createTask } from "../api/tasks";
import { listHotlist } from "../api/hotlist";
import type { HotlistItem, TaskPlatform } from "../types/api";
import { PLATFORM_LABELS } from "../types/api";
import { ApiError } from "../api/client";

const PLATFORMS = Object.keys(PLATFORM_LABELS) as TaskPlatform[];

export function CreateTask() {
  const navigate = useNavigate();
  const [requirement, setRequirement] = useState(
    "帮我写一篇关于最新AI技术突破的微博，风格幽默，要蹭热点"
  );
  const [platform, setPlatform] = useState<TaskPlatform>("weibo");
  const [hotlistId, setHotlistId] = useState<number | null>(null);
  const [hotlist, setHotlist] = useState<HotlistItem[]>([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listHotlist(1, 15)
      .then((res) => setHotlist(res.data?.items ?? []))
      .catch(() => setHotlist([]));
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const res = await createTask({
        raw_requirement: requirement,
        platform,
        hotlist_id: hotlistId,
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
            三个 AI Agent 将依次理解需求、创作初稿并审核优化
          </p>
        </div>
      </div>

      <form className="form-card" onSubmit={handleSubmit}>
        <label>
          文案需求
          <textarea
            value={requirement}
            onChange={(e) => setRequirement(e.target.value)}
            rows={5}
            required
            minLength={5}
            maxLength={1000}
            placeholder="描述主题、风格、字数、是否要蹭热点…"
          />
        </label>

        <label>
          目标平台
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value as TaskPlatform)}
          >
            {PLATFORMS.map((p) => (
              <option key={p} value={p}>
                {PLATFORM_LABELS[p]}
              </option>
            ))}
          </select>
        </label>

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

        <button type="submit" className="btn-primary btn-lg" disabled={submitting}>
          {submitting ? "提交中…" : "开始生成"}
        </button>
      </form>
    </div>
  );
}
