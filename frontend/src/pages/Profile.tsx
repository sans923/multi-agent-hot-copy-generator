import { FormEvent, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";
import { updateMyProfile } from "../api/users";
import { ApiError } from "../api/client";

export function Profile() {
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const [nickname, setNickname] = useState(user?.nickname ?? "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password && password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    if (password && password.length < 6) {
      setError("密码至少 6 位");
      return;
    }

    setSaving(true);
    try {
      const payload: { nickname?: string; password?: string } = {};
      if (nickname !== user?.nickname) payload.nickname = nickname;
      if (password) payload.password = password;

      if (Object.keys(payload).length === 0) {
        toast.info("没有需要保存的修改");
        return;
      }

      await updateMyProfile(payload);
      await refreshUser();
      setPassword("");
      setConfirm("");
      toast.success("资料已更新");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "保存失败";
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <div className="page page-narrow">
      <div className="page-header">
        <div>
          <h1>个人中心</h1>
          <p className="page-desc">管理账号信息与登录密码</p>
        </div>
      </div>

      <div className="profile-card">
        <dl className="profile-meta">
          <div>
            <dt>用户名</dt>
            <dd>{user.username}</dd>
          </div>
          <div>
            <dt>邮箱</dt>
            <dd>{user.email}</dd>
          </div>
          <div>
            <dt>角色</dt>
            <dd>{user.is_admin ? "管理员" : "普通用户"}</dd>
          </div>
          <div>
            <dt>注册时间</dt>
            <dd>{new Date(user.created_at).toLocaleString("zh-CN")}</dd>
          </div>
        </dl>
      </div>

      <form className="form-card" onSubmit={handleSubmit}>
        <label>
          昵称
          <input
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            maxLength={50}
          />
        </label>
        <label>
          新密码（留空则不修改）
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
        </label>
        <label>
          确认新密码
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "保存中…" : "保存修改"}
        </button>
      </form>
    </div>
  );
}
