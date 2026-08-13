"""头条辅助发布与抖音 H5 用户确认投稿。"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.models.copy import Copy
from app.schemas.publishing import (
    PublishPreparationRequest,
    PublishPreparationResponse,
)


TOUTIAO_CREATOR_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DOUYIN_H5_SHARE_SCHEME = "snssdk1128://openplatform/share"


class DouyinOpenPlatformError(RuntimeError):
    """抖音开放平台凭证或 open ticket 获取失败。"""


def is_allowed_media_host(media_url: object, allowed_hosts: str) -> bool:
    """仅允许明确配置的自有 CDN/对象存储主机，避免开放签名能力被滥用。"""
    host = str(getattr(media_url, "host", "") or "").rstrip(".").lower()
    allowed = {
        value.strip().rstrip(".").lower()
        for value in allowed_hosts.split(",")
        if value.strip()
    }
    return bool(host and host in allowed)


def _clean_hashtags(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value).strip().lstrip("#").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        result.append(tag)
    return result[:5]


def _build_package_text(copy: Copy, hashtags: list[str]) -> str:
    blocks = [str(copy.title or "").strip(), str(copy.content or "").strip()]
    if hashtags:
        blocks.append(" ".join(f"#{tag}" for tag in hashtags))
    return "\n\n".join(block for block in blocks if block)


def prepare_toutiao_publication(copy: Copy) -> PublishPreparationResponse:
    """生成可复制发布包；真正提交仍由用户在头条创作页完成。"""
    hashtags = _clean_hashtags(copy.hashtags)
    return PublishPreparationResponse(
        platform="toutiao",
        mode="assisted_export",
        ready=True,
        copy_id=copy.id,
        title=str(copy.title or "未命名文章").strip(),
        content=str(copy.content or "").strip(),
        hashtags=hashtags,
        package_text=_build_package_text(copy, hashtags),
        creator_url=TOUTIAO_CREATOR_URL,
        instructions=[
            "系统已复制标题、正文和标签组成的发布包",
            "在头条创作页粘贴内容并检查排版、封面与原创声明",
            "由账号本人确认发布",
        ],
    )


def build_douyin_h5_signature(
    ticket: str,
    nonce_str: str,
    timestamp: str,
) -> str:
    """按官方 H5 投稿协议对 open ticket 参数做 MD5 签名。"""
    raw = f"nonce_str={nonce_str}&ticket={ticket}&timestamp={timestamp}"
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def build_douyin_h5_schema(
    *,
    client_key: str,
    ticket: str,
    nonce_str: str,
    timestamp: str,
    title: str,
    hashtags: list[str],
    media_url: str,
    media_type: str,
    state: str,
) -> str:
    """生成移动端可拉起抖音发布器的 H5 Schema。"""
    params: dict[str, str | int] = {
        "share_type": "h5",
        "client_key": client_key,
        "nonce_str": nonce_str,
        "timestamp": timestamp,
        "signature": build_douyin_h5_signature(ticket, nonce_str, timestamp),
        "state": state,
        "title": title,
        "hashtag_list": json.dumps(hashtags, ensure_ascii=False, separators=(",", ":")),
        "share_to_type": 0,
    }
    params["video_path" if media_type == "video" else "image_path"] = media_url
    if media_type == "video":
        params["share_to_publish"] = 1
    return f"{DOUYIN_H5_SHARE_SCHEME}?{urlencode(params)}"


def prepare_douyin_publication(
    copy: Copy,
    request: PublishPreparationRequest,
    *,
    enabled: bool,
    client_key: str,
    ticket: str | None = None,
    allowed_media_hosts: str = "",
    nonce_str: str | None = None,
    timestamp: str | None = None,
    external_blocker: str | None = None,
) -> PublishPreparationResponse:
    """预检并准备抖音投稿，不把“已拉起”误记成“已发布”。"""
    hashtags = _clean_hashtags(copy.hashtags)
    blockers: list[str] = []
    if not enabled:
        blockers.append("未启用 DOUYIN_H5_SHARE_ENABLED，需先在开放平台获批 H5 投稿能力")
    if not client_key.strip():
        blockers.append("未配置 DOUYIN_CLIENT_KEY")
    if request.media_url is None or request.media_type is None:
        blockers.append("抖音 H5 投稿至少需要一个公网 HTTPS 图片或视频地址")
    elif not is_allowed_media_host(request.media_url, allowed_media_hosts):
        blockers.append("素材域名不在 DOUYIN_MEDIA_ALLOWED_HOSTS 自有 CDN 白名单中")
    if external_blocker:
        blockers.append(external_blocker)
    if enabled and client_key.strip() and request.media_url is not None and not ticket:
        blockers.append("未取得抖音 open ticket，无法生成安全投稿链接")

    launch_url = None
    if not blockers and ticket and request.media_url and request.media_type:
        launch_url = build_douyin_h5_schema(
            client_key=client_key.strip(),
            ticket=ticket,
            nonce_str=nonce_str or secrets.token_urlsafe(12),
            timestamp=timestamp or str(int(time.time())),
            title=str(copy.title or "内容投稿").strip(),
            hashtags=hashtags,
            media_url=str(request.media_url),
            media_type=request.media_type,
            state=f"task-{copy.task_id}-copy-{copy.id}",
        )

    return PublishPreparationResponse(
        platform="douyin",
        mode="user_confirmed_post",
        ready=launch_url is not None,
        copy_id=copy.id,
        title=str(copy.title or "内容投稿").strip(),
        content=str(copy.content or "").strip(),
        hashtags=hashtags,
        package_text=_build_package_text(copy, hashtags),
        launch_url=launch_url,
        media_url=str(request.media_url) if request.media_url else None,
        media_type=request.media_type,
        blockers=blockers,
        instructions=[
            "请在手机端点击投稿按钮拉起抖音",
            "在抖音发布器中检查素材、标题、话题和可见范围",
            "由账号本人确认发布；拉起发布器不代表作品已经发布",
        ],
    )


@dataclass(frozen=True)
class _CachedTicket:
    value: str
    expires_at: float


class DouyinOpenPlatformClient:
    """获取并缓存 H5 投稿签名所需的 client token 与 open ticket。"""

    def __init__(
        self,
        *,
        client_key: str,
        client_secret: str,
        base_url: str = "https://open.douyin.com",
        timeout: float = 10.0,
    ) -> None:
        self.client_key = client_key
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._ticket: _CachedTicket | None = None
        self._lock = threading.Lock()

    def get_open_ticket(self) -> str:
        now = time.monotonic()
        if self._ticket and self._ticket.expires_at > now + 300:
            return self._ticket.value
        with self._lock:
            now = time.monotonic()
            if self._ticket and self._ticket.expires_at > now + 300:
                return self._ticket.value
            ticket, expires_in = self._fetch_open_ticket()
            self._ticket = _CachedTicket(ticket, now + max(expires_in, 1))
            return ticket

    def _fetch_open_ticket(self) -> tuple[str, int]:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                token_response = client.post(
                    "/oauth/client_token/",
                    json={
                        "grant_type": "client_credential",
                        "client_key": self.client_key,
                        "client_secret": self.client_secret,
                    },
                )
                token_response.raise_for_status()
                token_data = self._unwrap_data(token_response.json(), "client token")
                access_token = str(token_data.get("access_token") or "")
                if not access_token:
                    raise DouyinOpenPlatformError("抖音未返回 client token")

                ticket_response = client.get(
                    "/open/getticket/",
                    headers={"access-token": access_token},
                )
                ticket_response.raise_for_status()
                ticket_data = self._unwrap_data(ticket_response.json(), "open ticket")
                expires_in = int(ticket_data.get("expires_in") or 7200)
        except (httpx.HTTPError, ValueError) as exc:
            raise DouyinOpenPlatformError("连接抖音开放平台失败") from exc

        ticket = str(ticket_data.get("ticket") or "")
        if not ticket:
            raise DouyinOpenPlatformError("抖音未返回 open ticket")
        return ticket, expires_in

    @staticmethod
    def _unwrap_data(payload: object, label: str) -> dict[str, object]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise DouyinOpenPlatformError(f"抖音 {label} 响应格式异常")
        data = payload["data"]
        error_code = int(data.get("error_code") or 0)
        if error_code:
            raise DouyinOpenPlatformError(f"抖音 {label} 获取失败（错误码 {error_code}）")
        return data
