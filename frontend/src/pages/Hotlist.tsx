import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getHotlistStats,
  listHotlist,
  searchHotlist,
  triggerHotlistSync,
} from "../api/hotlist";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";
import type { HotlistItem, HotlistSearchResult } from "../types/api";
import { ApiError } from "../api/client";

export function Hotlist() {
  const { user } = useAuth();
  const toast = useToast();
  const [items, setItems] = useState<HotlistItem[]>([]);
  const [searchResults, setSearchResults] = useState<HotlistSearchResult[]>([]);
  const [query, setQuery] = useState("");
  const [stats, setStats] = useState<{
    active_by_platform: Record<string, number>;
    latest_sync_time: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  const loadList = () => {
    setLoading(true);
    listHotlist(1, 40)
      .then((res) => setItems(res.data?.items ?? []))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "加载失败")
      )
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadList();
    if (user?.is_admin) {
      getHotlistStats()
        .then((res) => setStats(res.data ?? null))
        .catch(() => setStats(null));
    }
  }, [user?.is_admin]);

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
      if ((res.data?.length ?? 0) === 0) {
        toast.info("未找到相关话题，试试换个描述");
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "搜索失败";
      setError(msg);
      toast.error(msg);
    } finally {
      setSearching(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      await triggerHotlistSync();
      toast.success("热榜同步已在后台启动，请稍后刷新");
      setTimeout(loadList, 5000);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "同步失败");
    } finally {
      setSyncing(false);
    }
  };

  const createLink = (item: { id?: number; title: string }) => {
    if (item.id) {
      return `/create?hotlist_id=${item.id}&title=${encodeURIComponent(item.title)}`;
    }
    return `/create?title=${encodeURIComponent(item.title)}`;
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>热榜</h1>
          <p className="page-desc">
            浏览当前热点，或语义搜索后一键生成文案
            {stats?.latest_sync_time && (
              <>
                {" "}
                · 最近同步{" "}
                {new Date(stats.latest_sync_time).toLocaleString("zh-CN")}
              </>
            )}
          </p>
        </div>
        <div className="header-actions">
          {user?.is_admin && (
            <button
              type="button"
              className="btn-secondary"
              onClick={handleSync}
              disabled={syncing}
            >
              {syncing ? "同步中…" : "同步热榜"}
            </button>
          )}
          <button type="button" className="btn-secondary" onClick={loadList}>
            刷新
          </button>
        </div>
      </div>

      <form className="search-bar" onSubmit={handleSearch}>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="语义搜索，如：美妆护肤、AI科技、新能源汽车…"
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
                <div className="hotlist-item-body">
                  <strong>{item.title}</strong>
                  <span className="hot-meta">
                    相似度 {(item.similarity * 100).toFixed(0)}%
                    {item.hot_value && ` · 热度 ${item.hot_value}`}
                  </span>
                </div>
                <Link
                  to={createLink({ title: item.title })}
                  className="btn-secondary btn-sm"
                >
                  写文案
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="hotlist-section">
        <h2>最新热榜</h2>
        {loading && <p className="muted">加载中…</p>}
        {!loading && items.length === 0 && (
          <p className="muted">
            暂无热榜数据
            {user?.is_admin
              ? "，请点击「同步热榜」拉取数据"
              : "，请联系管理员同步"}
          </p>
        )}
        <ul className="hotlist-list">
          {items.map((item) => (
            <li key={item.id} className="hotlist-item">
              <span className="hot-rank">#{item.rank}</span>
              <div className="hotlist-item-body">
                <strong>{item.title}</strong>
                {item.description && (
                  <p className="hot-desc">{item.description}</p>
                )}
                <span className="hot-meta">
                  {item.hot_value && `热度 ${item.hot_value}`}
                </span>
              </div>
              <Link
                to={createLink(item)}
                className="btn-secondary btn-sm"
              >
                写文案
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
