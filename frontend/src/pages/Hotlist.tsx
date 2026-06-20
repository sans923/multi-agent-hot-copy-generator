import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listHotlist, searchHotlist } from "../api/hotlist";
import type { HotlistItem, HotlistSearchResult } from "../types/api";
import { ApiError } from "../api/client";

export function Hotlist() {
  const [items, setItems] = useState<HotlistItem[]>([]);
  const [searchResults, setSearchResults] = useState<HotlistSearchResult[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listHotlist(1, 30)
      .then((res) => setItems(res.data?.items ?? []))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "加载失败")
      )
      .finally(() => setLoading(false));
  }, []);

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    setError("");
    try {
      const res = await searchHotlist(query.trim(), 10);
      setSearchResults(res.data ?? []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "搜索失败");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>热榜</h1>
          <p className="page-desc">浏览当前热点，或语义搜索相关话题</p>
        </div>
        <Link to="/create" className="btn-primary">
          用热点生成文案
        </Link>
      </div>

      <form className="search-bar" onSubmit={handleSearch}>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="语义搜索，如：美妆护肤、AI科技…"
        />
        <button type="submit" className="btn-secondary" disabled={searching}>
          {searching ? "搜索中…" : "搜索"}
        </button>
      </form>

      {error && <p className="form-error">{error}</p>}

      {searchResults.length > 0 && (
        <section className="hotlist-section">
          <h2>搜索结果</h2>
          <ul className="hotlist-list">
            {searchResults.map((item, i) => (
              <li key={`${item.title}-${i}`} className="hotlist-item">
                <span className="hot-rank">#{item.rank}</span>
                <div>
                  <strong>{item.title}</strong>
                  <span className="hot-meta">
                    相似度 {(item.similarity * 100).toFixed(0)}%
                    {item.hot_value && ` · 热度 ${item.hot_value}`}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="hotlist-section">
        <h2>最新热榜</h2>
        {loading && <p className="muted">加载中…</p>}
        {!loading && items.length === 0 && (
          <p className="muted">暂无热榜数据，请确认后端已同步热榜</p>
        )}
        <ul className="hotlist-list">
          {items.map((item) => (
            <li key={item.id} className="hotlist-item">
              <span className="hot-rank">#{item.rank}</span>
              <div>
                <strong>{item.title}</strong>
                {item.description && (
                  <p className="hot-desc">{item.description}</p>
                )}
                <span className="hot-meta">
                  {item.hot_value && `热度 ${item.hot_value}`}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
