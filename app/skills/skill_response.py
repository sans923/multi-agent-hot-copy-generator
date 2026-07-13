"""
Skill 统一返回格式
==================
所有 Skill 通过 skill_ok / skill_fail 返回，SkillExecutor 自动补全 meta。

结构：
{
    "success": bool,
    "error": str | null,
    "data": { ... 业务字段 ... },
    "meta": { "skill": "...", "latency_ms": ... },
    ...data 字段扁平化副本（兼容旧 Agent 读取 top-level 键）
}
"""

from __future__ import annotations

from typing import Any

_ENVELOPE_KEYS = frozenset({"success", "error", "data", "meta", "message"})


def skill_ok(data: dict[str, Any] | None = None, *, message: str | None = None) -> dict[str, Any]:
    """构造成功返回（业务字段放入 data）。"""
    payload = dict(data or {})
    result: dict[str, Any] = {
        "success": True,
        "error": None,
        "data": payload,
    }
    if message:
        result["message"] = message
    return result


def skill_fail(error: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造失败返回。"""
    payload = dict(data or {})
    return {
        "success": False,
        "error": error,
        "data": payload,
    }


def normalize_skill_result(
    raw: dict[str, Any],
    skill_name: str,
    latency_ms: float,
) -> dict[str, Any]:
    """
    将 Skill 原始 dict 规范化为统一信封，并保留 top-level 扁平字段以兼容旧代码。
    """
    success = bool(raw.get("success"))
    error = raw.get("error")

    if isinstance(raw.get("data"), dict):
        data = dict(raw["data"])
        for key, value in raw.items():
            if key not in _ENVELOPE_KEYS:
                data.setdefault(key, value)
    else:
        data = {k: v for k, v in raw.items() if k not in _ENVELOPE_KEYS}

    meta: dict[str, Any] = {
        "skill": skill_name,
        "latency_ms": round(latency_ms, 1),
    }
    if isinstance(raw.get("meta"), dict):
        meta.update(raw["meta"])

    normalized: dict[str, Any] = {
        "success": success,
        "error": error if not success else None,
        "data": data,
        "meta": meta,
    }
    if raw.get("message"):
        normalized["message"] = raw["message"]

    for key, value in data.items():
        if key not in normalized:
            normalized[key] = value

    return normalized
