"""发布准备接口的数据契约。"""

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


PublishPlatform = Literal["toutiao", "douyin"]
MediaType = Literal["image", "video"]


class PublishPreparationRequest(BaseModel):
    """准备头条发布包或抖音 H5 用户确认投稿。"""

    platform: PublishPlatform
    media_url: HttpUrl | None = Field(
        default=None,
        description="抖音投稿使用的公网 HTTPS 图片或视频地址",
    )
    media_type: MediaType | None = None

    @model_validator(mode="after")
    def validate_media_pair(self) -> "PublishPreparationRequest":
        if (self.media_url is None) != (self.media_type is None):
            raise ValueError("media_url 与 media_type 必须同时提供")
        if self.media_url is not None and self.media_url.scheme != "https":
            raise ValueError("抖音投稿素材必须使用公网 HTTPS 地址")
        return self


class PublishPreparationResponse(BaseModel):
    """不会伪造发布成功，只描述下一步用户确认动作。"""

    platform: PublishPlatform
    mode: Literal["assisted_export", "user_confirmed_post"]
    ready: bool
    requires_user_confirmation: bool = True
    copy_id: int
    title: str
    content: str
    hashtags: list[str] = Field(default_factory=list)
    package_text: str
    creator_url: str | None = None
    launch_url: str | None = None
    media_url: str | None = None
    media_type: MediaType | None = None
    blockers: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)

