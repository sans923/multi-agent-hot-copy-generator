import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-icon">🔥</span>
          <span className="brand-text">热点文案</span>
        </Link>
        <nav className="nav">
          <NavLink to="/" end>
            工作台
          </NavLink>
          <NavLink to="/create">生成文案</NavLink>
          <NavLink to="/hotlist">热榜</NavLink>
          {user?.is_admin && (
            <NavLink to="/admin/users">用户管理</NavLink>
          )}
        </nav>
        <div className="header-user">
          <Link to="/profile" className="user-link">
            {user?.nickname || user?.username}
          </Link>
          {user?.is_admin && <span className="badge-admin">管理员</span>}
          <button type="button" className="btn-ghost" onClick={logout}>
            退出
          </button>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
