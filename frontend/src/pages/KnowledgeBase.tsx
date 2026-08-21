import { FormEvent, useCallback, useEffect, useState } from "react";
import { createKnowledgeSource, listKnowledgeSources, searchKnowledge } from "../api/knowledge";
import { getMemoryInsights } from "../api/memory";
import { ApiError } from "../api/client";
import { useToast } from "../contexts/ToastContext";
import type { KnowledgeSearchItem, KnowledgeSource, KnowledgeType, MemoryInsights } from "../types/api";

const TYPE_LABELS: Record<KnowledgeType, string> = {
  brand_fact: "品牌事实", product_fact: "产品事实", campaign_material: "活动素材",
  platform_rule: "平台规则", external_reference: "外部参考",
};

export function KnowledgeBase() {
  const toast = useToast();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [insights, setInsights] = useState<MemoryInsights | null>(null);
  const [type, setType] = useState<KnowledgeType>("product_fact");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [sourceUri, setSourceUri] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KnowledgeSearchItem[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [sourceResponse, insightResponse] = await Promise.all([listKnowledgeSources(), getMemoryInsights()]);
      setSources(sourceResponse.data ?? []);
      setInsights(insightResponse.data);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "知识与记忆加载失败");
    }
  }, [toast]);

  useEffect(() => { void load(); }, [load]);

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await createKnowledgeSource({ knowledge_type: type, title: title.trim(), content: content.trim(), source_uri: sourceUri.trim() || undefined });
      setTitle(""); setContent(""); setSourceUri("");
      toast.success("知识来源已保存，正在异步建立向量索引");
      await load();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "知识保存失败");
    } finally { setBusy(false); }
  };

  const handleSearch = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const response = await searchKnowledge(query.trim());
      setResults(response.data?.items ?? []);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "知识检索失败");
    }
  };

  return (
    <div className="page knowledge-page">
      <div className="page-header"><div><h1>知识与记忆</h1><p className="page-desc">管理可引用事实，查看系统从真实采用行为中学到了什么。</p></div></div>
      {insights && <section className="knowledge-metrics">
        <div><strong>{insights.feedback.total}</strong><span>有效反馈</span></div>
        <div><strong>{Math.round(insights.feedback.adoption_rate * 100)}%</strong><span>采用率</span></div>
        <div><strong>{insights.publication.total}</strong><span>发布记录</span></div>
        <div><strong>{insights.memory.active_inferred_preferences}</strong><span>已晋升偏好</span></div>
      </section>}
      <div className="knowledge-layout">
        <form className="form-card" onSubmit={handleCreate}>
          <h2>新增可信来源</h2>
          <label>类型<select value={type} onChange={(event) => setType(event.target.value as KnowledgeType)}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>标题<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
          <label>来源地址（可选）<input value={sourceUri} onChange={(event) => setSourceUri(event.target.value)} placeholder="internal://product/v2" /></label>
          <label>事实正文<textarea required value={content} onChange={(event) => setContent(event.target.value)} /></label>
          <button className="btn-primary" disabled={busy}>{busy ? "保存中…" : "保存并索引"}</button>
        </form>
        <section className="knowledge-source-list">
          <h2>版本化来源</h2>
          {sources.length === 0 ? <p className="page-desc">暂无知识来源。</p> : sources.map((source) => <article key={source.id}>
            <span>{TYPE_LABELS[source.knowledge_type]} · v{source.version}</span><h3>{source.title}</h3><small>{source.status} / 索引 {source.index_status}</small>
          </article>)}
        </section>
      </div>
      <section className="knowledge-search-panel">
        <form onSubmit={handleSearch}><input required value={query} onChange={(event) => setQuery(event.target.value)} placeholder="验证 AI 能检索到哪些事实" /><button className="btn-secondary">检索知识</button></form>
        {results.map((item) => <article key={item.chunk_id}><strong>{item.citation.title} · v{item.citation.version}</strong><span>相关度 {Math.round(item.score * 100)}%</span><p>{item.content}</p></article>)}
      </section>
    </div>
  );
}
