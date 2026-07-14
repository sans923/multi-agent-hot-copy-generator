"""
合规检测 Skill
==============
- check_sensitive_words：敏感词/违禁词检测
- check_plagiarism_overlap：与参考长文的重叠度检测（防洗稿）
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.models.toutiao_reference import ToutiaoReference
from app.services.writing_pattern_service import has_ngram_overlap
from app.skills.base import BaseSkill
from app.skills.skill_response import skill_fail, skill_ok
from app.utils.logger import logger

_SENSITIVE_WORDS_CACHE: list[str] | None = None
_DEFAULT_NGRAM_LEN = 10
_DEFAULT_OVERLAP_THRESHOLD = 0.15  # 重叠字符占比超过 15% 视为高风险


_DEFAULT_SENSITIVE_WORDS = [
    "最好",
    "第一",
    "顶级",
    "日赚",
    "万元不是梦",
    "稳赚",
    "包治",
    "绝对",
]


def _load_sensitive_words() -> list[str]:
    global _SENSITIVE_WORDS_CACHE
    if _SENSITIVE_WORDS_CACHE is not None:
        return _SENSITIVE_WORDS_CACHE

    words: list[str] = list(_DEFAULT_SENSITIVE_WORDS)
    word_file = Path(__file__).resolve().parent.parent / "data" / "sensitive_words.txt"
    if word_file.exists():
        for line in word_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line not in words:
                words.append(line)

    _SENSITIVE_WORDS_CACHE = words
    return words


def _find_sensitive_hits(text: str, words: list[str]) -> list[dict]:
    hits: list[dict] = []
    lowered = text.lower()
    for word in words:
        if not word:
            continue
        if word.lower() in lowered or word in text:
            hits.append({"word": word, "severity": "high"})
    return hits


def _compute_overlap_metrics(text: str, sources: list[str], n: int = _DEFAULT_NGRAM_LEN) -> dict:
    """计算与多篇参考文的重叠指标（滑动窗口 n-gram）。"""
    if not text or not sources:
        return {
            "max_overlap_chars": 0,
            "overlap_ratio": 0.0,
            "overlap_segments": [],
            "risk_level": "low",
        }

    combined = "".join(sources)
    windows = max(len(text) - n + 1, 1)
    hit_windows = 0
    segments: list[str] = []

    for i in range(len(text) - n + 1):
        chunk = text[i : i + n]
        if chunk in combined:
            hit_windows += 1
            if len(segments) < 5 and chunk not in segments:
                segments.append(chunk)

    overlap_ratio = hit_windows / windows
    max_overlap = n
    for seg in re.findall(rf"[\u4e00-\u9fa5]{{{n},}}", text):
        if seg in combined:
            max_overlap = max(max_overlap, len(seg))

    if overlap_ratio >= 0.35 or max_overlap >= 25:
        risk = "high"
    elif overlap_ratio >= _DEFAULT_OVERLAP_THRESHOLD or max_overlap >= n + 5:
        risk = "medium"
    else:
        risk = "low"

    return {
        "max_overlap_chars": max_overlap,
        "overlap_ratio": round(overlap_ratio, 4),
        "overlap_segments": segments[:5],
        "risk_level": risk,
    }


class CheckSensitiveWordsSkill(BaseSkill):
    """敏感词/违禁词检测。"""

    @property
    def name(self) -> str:
        return "check_sensitive_words"

    @property
    def description(self) -> str:
        return (
            "检测文案中的敏感词、违禁词、绝对化广告用语。"
            "审核流程第一步调用；若未通过应先 optimize_copy 修改再保存。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待检测文案正文"},
                "platform": {
                    "type": "string",
                    "description": "目标平台，用于日志",
                    "default": "weibo",
                },
            },
            "required": ["text"],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        text = (kwargs.get("text") or "").strip()
        platform = kwargs.get("platform", "weibo")

        if not text:
            return skill_fail("text 不能为空")

        words = _load_sensitive_words()
        hits = _find_sensitive_hits(text, words)
        passed = len(hits) == 0
        risk_level = "low" if passed else ("high" if len(hits) >= 3 else "medium")

        logger.info(
            f"敏感词检测: platform={platform}, hits={len(hits)}, passed={passed}"
        )

        return skill_ok(
            {
                "passed": passed,
                "hit_count": len(hits),
                "hits": hits,
                "risk_level": risk_level,
                "platform": platform,
                "checked_word_count": len(words),
            },
            message="未命中敏感词" if passed else f"命中 {len(hits)} 个敏感词/违禁表达",
        )


class CheckPlagiarismOverlapSkill(BaseSkill):
    """与参考长文库的重叠度检测（洗稿风险）。"""

    @property
    def name(self) -> str:
        return "check_plagiarism_overlap"

    @property
    def description(self) -> str:
        return (
            "检测文案与头条参考长文库的内容重叠度，识别洗稿风险。"
            "在 review_copy_quality 之前调用；overlap 过高需重写而非微调。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待检测文案正文"},
                "topic": {
                    "type": "string",
                    "description": "话题关键词，用于缩小参考文范围",
                },
                "ngram_len": {
                    "type": "integer",
                    "description": "连续汉字重叠判定长度，默认10",
                    "default": 10,
                },
                "reference_limit": {
                    "type": "integer",
                    "description": "参与比对的参考文数量，默认5",
                    "default": 5,
                },
            },
            "required": ["text"],
        }

    def execute(self, db: Session, **kwargs) -> dict:
        text = (kwargs.get("text") or "").strip()
        topic = (kwargs.get("topic") or "").strip()
        ngram_len = int(kwargs.get("ngram_len", _DEFAULT_NGRAM_LEN))
        limit = min(int(kwargs.get("reference_limit", 5)), 10)

        if not text:
            return skill_fail("text 不能为空")

        query = db.query(ToutiaoReference)
        if topic:
            pattern = f"%{topic}%"
            query = query.filter(
                or_(
                    ToutiaoReference.keyword.like(pattern),
                    ToutiaoReference.title.like(pattern),
                )
            )
        rows = query.order_by(desc(ToutiaoReference.like_count)).limit(limit).all()

        sources = [f"{r.title or ''}{r.content or ''}" for r in rows]
        metrics = _compute_overlap_metrics(text, sources, n=ngram_len)
        hard_block = has_ngram_overlap(text, sources, n=ngram_len)

        passed = not hard_block and metrics["risk_level"] == "low"
        need_rewrite = metrics["risk_level"] == "high" or hard_block

        logger.info(
            f"洗稿检测: topic={topic}, refs={len(rows)}, "
            f"risk={metrics['risk_level']}, passed={passed}"
        )

        return skill_ok(
            {
                "passed": passed,
                "need_rewrite": need_rewrite,
                "reference_count": len(rows),
                "max_overlap_chars": metrics["max_overlap_chars"],
                "overlap_ratio": metrics["overlap_ratio"],
                "overlap_segments": metrics["overlap_segments"],
                "risk_level": metrics["risk_level"],
                "ngram_len": ngram_len,
            },
            message="重叠度正常" if passed else "检测到与参考长文高度重叠，建议重写",
        )
