import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  buildStyleCard,
  deleteReference,
  deleteStyleCard,
  importReference,
  listReferences,
  listStyleCards,
  reindexReference,
} from "../api/contentAssets";
import { ApiError } from "../api/client";
import { useToast } from "../contexts/ToastContext";
import type { StyleCard, ToutiaoReference } from "../types/api";

const statusLabel: Record<string, string> = {
  pending: "待向量化",
  processing: "处理中",
  completed: "可检索",
  failed: "处理失败",
};

function patternSummary(pattern: Record<string, unknown>) {
  const title = pattern.title_formula as { pattern?: string } | undefined;
  const hook = pattern.hook as { type?: string } | undefined;
  const rhythm = pattern.rhythm as { paragraph_length?: string } | undefined;
  return [title?.pattern, hook?.type, rhythm?.paragraph_length].filter(Boolean) as string[];
}

export function ContentAssets() {
  const toast = useToast();
  const [references, setReferences] = useState<ToutiaoReference[]>([]);
  const [cards, setCards] = useState<StyleCard[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");
  const [keyword, setKeyword] = useState("");
  const [likeCount, setLikeCount] = useState(0);
  const [cardTopic, setCardTopic] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [referenceRes, cardRes] = await Promise.all([
        listReferences(1, 50, query),
        listStyleCards(),
      ]);
      setReferences(referenceRes.data?.items ?? []);
      setCards(cardRes.data ?? []);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "内容资产加载失败");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const completedCount = useMemo(
    () => references.filter((item) => item.embedding_status === "completed").length,
    [references]
  );

  const handleImport = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("import");
    try {
      await importReference({ url, keyword, like_count: likeCount });
      toast.success("参考文章已导入并完成向量化");
      setUrl("");
      setLikeCount(0);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "导入失败");
    } finally {
      setBusy("");
    }
  };

  const handleBuildCard = async () => {
    if (!cardTopic.trim() || selected.length === 0) return;
    setBusy("card");
    try {
      await buildStyleCard({ topic_cluster: cardTopic.trim(), reference_ids: selected });
      toast.success("风格卡已生成，可在创作任务中直接选择");
      setSelected([]);
      setCardTopic("");
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "风格卡生成失败");
    } finally {
      setBusy("");
    }
  };

  const handleReindex = async (id: number) => {
    setBusy(`reindex-${id}`);
    try {
      await reindexReference(id);
      toast.success("重新向量化完成");
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "重新向量化失败");
    } finally {
      setBusy("");
    }
  };

  const handleDeleteReference = async (item: ToutiaoReference) => {
    if (!window.confirm(`确定删除参考文章「${item.title}」及其向量数据吗？`)) return;
    setBusy(`delete-${item.id}`);
    try {
      await deleteReference(item.id);
      setSelected((ids) => ids.filter((id) => id !== item.id));
      toast.success("参考文章已删除");
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "删除失败");
    } finally {
      setBusy("");
    }
  };

  const handleDeleteCard = async (card: StyleCard) => {
    if (!window.confirm(`确定删除风格卡「${card.topic_cluster}」吗？`)) return;
    try {
      await deleteStyleCard(card.id);
      toast.success("风格卡已删除");
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "删除失败");
    }
  };

  const toggleSelected = (id: number) => {
    setSelected((ids) =>
      ids.includes(id) ? ids.filter((value) => value !== id) : ids.length < 3 ? [...ids, id] : ids
    );
  };

  return (
    <div className="page asset-page">
      <section className="asset-hero">
        <div>
          <span className="asset-eyebrow">Editorial Intelligence Library</span>
          <h1>内容资产库</h1>
          <p>把爆款文章沉淀为可检索证据，再提炼成不复制原文的结构化风格卡。</p>
        </div>
        <div className="asset-metrics">
          <div><strong>{references.length}</strong><span>参考长文</span></div>
          <div><strong>{completedCount}</strong><span>已向量化</span></div>
          <div><strong>{cards.length}</strong><span>风格卡</span></div>
        </div>
      </section>

      <section className="asset-import-panel">
        <div className="asset-panel-heading">
          <div><span>01 / INGEST</span><h2>导入头条参考文章</h2></div>
          <p>抓取正文后自动切块并写入 Chroma，供长文 Agent 检索。</p>
        </div>
        <form className="asset-import-form" onSubmit={handleImport}>
          <label className="asset-url-field">文章 URL<input type="url" value={url} onChange={(e) => setUrl(e.target.value)} required placeholder="https://www.toutiao.com/article/.../" /></label>
          <label>关键词<input value={keyword} onChange={(e) => setKeyword(e.target.value)} required placeholder="如 AI就业" /></label>
          <label>点赞数<input type="number" min="0" value={likeCount} onChange={(e) => setLikeCount(Number(e.target.value))} /></label>
          <button className="btn-primary" disabled={busy === "import"}>{busy === "import" ? "抓取与向量化中…" : "导入资产"}</button>
        </form>
      </section>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="asset-workspace">
        <section className="asset-library-panel">
          <div className="asset-toolbar">
            <div><span>02 / SELECT</span><h2>参考文章</h2></div>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索标题或关键词" />
          </div>
          {loading ? <div className="asset-empty"><div className="spinner" />正在读取资产…</div> : references.length === 0 ? (
            <div className="asset-empty"><strong>还没有参考文章</strong><span>从上方粘贴一篇今日头条文章链接开始。</span></div>
          ) : (
            <div className="asset-reference-list">
              {references.map((item) => (
                <article className={`asset-reference ${selected.includes(item.id) ? "selected" : ""}`} key={item.id}>
                  <button className="asset-check" type="button" onClick={() => toggleSelected(item.id)} aria-label="选择文章">{selected.includes(item.id) ? "✓" : ""}</button>
                  <div className="asset-reference-main">
                    <div className="asset-reference-meta"><span className={`asset-status status-${item.embedding_status}`}>{statusLabel[item.embedding_status] ?? item.embedding_status}</span><span>{item.keyword || "未分类"}</span><span>{item.content_length.toLocaleString()} 字</span></div>
                    <h3>{item.title}</h3>
                    <div className="asset-reference-stats"><span>赞 {item.like_count.toLocaleString()}</span><span>块 {item.chunk_count}</span><span>{item.author_name || "未知作者"}</span></div>
                  </div>
                  <div className="asset-row-actions">
                    {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">原文</a>}
                    <button type="button" onClick={() => handleReindex(item.id)} disabled={busy === `reindex-${item.id}`}>重索引</button>
                    <button className="danger" type="button" onClick={() => handleDeleteReference(item)} disabled={busy === `delete-${item.id}`}>删除</button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <aside className="asset-card-builder">
          <div><span>03 / DISTILL</span><h2>生成风格卡</h2><p>选择 1–3 篇文章，只提取标题公式、钩子、结构、节奏与 CTA。</p></div>
          <div className="asset-selection-count"><strong>{selected.length}</strong><span>/ 3 篇已选择</span></div>
          <label>话题簇<input value={cardTopic} onChange={(e) => setCardTopic(e.target.value)} placeholder="如 职业转型" /></label>
          <button className="btn-primary" type="button" disabled={!cardTopic.trim() || selected.length === 0 || busy === "card"} onClick={handleBuildCard}>{busy === "card" ? "DeepSeek 提炼中…" : "生成风格卡"}</button>
          <small>生成过程会调用当前 Pattern 模型，并进行连续文本重叠检查。</small>
        </aside>
      </div>

      <section className="asset-cards-section">
        <div className="asset-panel-heading"><div><span>04 / REUSE</span><h2>可复用风格卡</h2></div><p>创建今日头条任务时可指定使用。</p></div>
        {cards.length === 0 ? <div className="asset-empty compact">尚未生成风格卡</div> : (
          <div className="style-card-grid">
            {cards.map((card) => (
              <article className="style-card-tile" key={card.id}>
                <header><div><span>TOUTIAO / {Math.round(card.confidence * 100)}%</span><h3>{card.topic_cluster}</h3></div><button type="button" onClick={() => handleDeleteCard(card)}>删除</button></header>
                <div className="style-card-tags">{patternSummary(card.pattern_json).map((item) => <span key={item}>{item}</span>)}</div>
                <dl><div><dt>来源文章</dt><dd>{card.source_article_ids.length}</dd></div><div><dt>平均点赞</dt><dd>{card.avg_like_count.toLocaleString()}</dd></div></dl>
                <details><summary>查看完整结构规则</summary><pre>{JSON.stringify(card.pattern_json, null, 2)}</pre></details>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
