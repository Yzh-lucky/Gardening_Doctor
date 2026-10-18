"""图片存储抽象 + 上传校验（准备文档 3.3 步骤 1）。

当前实现落本地磁盘：`UPLOAD_DIR/年/月/{sha256}.{ext}`，URL 走 FastAPI 挂载的 /static。
以后换对象存储（OSS/COS/CDN）时只需要改 save_bytes/公开 URL 这一段，
业务层（diagnosis 路由、recognizer）拿到的始终是 UploadedImage，不用动。

几个刻意为之的点：
- 格式判定看**文件头魔数**，不看后缀名 —— 后缀可以随便改名，魔数不行。
- 文件名用内容 sha256，天然去重：同一张图重复上传不会写第二份。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from app.core.config import settings
from app.core.response import BizError, Code
from app.utils.timeutil import now_cn

# 允许的图片类型：魔数前缀 → (扩展名, MIME)
# JPEG: FF D8 FF；PNG: 89 50 4E 47 0D 0A 1A 0A；WEBP: "RIFF"…"WEBP"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_RIFF_MAGIC = b"RIFF"
_WEBP_TAG = b"WEBP"


@dataclass(slots=True)
class UploadedImage:
    """校验通过并已落盘的一张图片。content 同时保留在内存，供送进大模型用。"""

    filename: str
    content: bytes
    ext: str
    mime: str
    sha256: str
    url: str
    size: int


def detect_image_type(content: bytes) -> tuple[str, str] | None:
    """按魔数识别图片类型，返回 (ext, mime)，不认识返回 None。"""
    if content[:8] == _PNG_MAGIC:
        return "png", "image/png"
    if content[:3] == _JPEG_MAGIC:
        return "jpg", "image/jpeg"
    # WEBP 头：0-4 是 RIFF，8-12 是 WEBP
    if len(content) >= 12 and content[:4] == _RIFF_MAGIC and content[8:12] == _WEBP_TAG:
        return "webp", "image/webp"
    return None


def _max_bytes() -> int:
    return settings.MAX_IMAGE_SIZE_MB * 1024 * 1024


def save_bytes(content: bytes, ext: str, digest: str, when: datetime | None = None) -> str:
    """写盘并返回可访问的 URL。已存在同一份（同 sha256）直接跳过，不重复写。"""
    day = when or now_cn()
    rel_dir = f"{day.year:04d}/{day.month:02d}"
    target_dir = settings.upload_path / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{digest}.{ext}"
    path = target_dir / name
    if not path.exists():
        path.write_bytes(content)
    return f"{settings.UPLOAD_URL_PREFIX}/{rel_dir}/{name}"


def process_image(content: bytes, filename: str = "") -> UploadedImage:
    """单张图片的完整校验 + 落盘。不合法直接抛业务异常，由全局处理器转标准响应。

    校验顺序按"先便宜后昂贵"：空文件 → 大小 → 格式，最后才做 sha256 与写盘。
    """
    if not content:
        raise BizError(Code.IMAGE_FORMAT_UNSUPPORTED, "图片内容为空")
    if len(content) > _max_bytes():
        raise BizError(
            Code.IMAGE_TOO_LARGE,
            f"单张图片不能超过 {settings.MAX_IMAGE_SIZE_MB}MB",
        )

    detected = detect_image_type(content)
    if detected is None:
        raise BizError(Code.IMAGE_FORMAT_UNSUPPORTED, "仅支持 jpg/jpeg/png/webp 格式")
    ext, mime = detected

    digest = hashlib.sha256(content).hexdigest()
    url = save_bytes(content, ext, digest)
    return UploadedImage(
        filename=filename or f"{digest}.{ext}",
        content=content,
        ext=ext,
        mime=mime,
        sha256=digest,
        url=url,
        size=len(content),
    )


def process_images(items: list[tuple[str, bytes]]) -> list[UploadedImage]:
    """批量处理：先卡数量上限，再逐张校验。返回顺序与入参一致（前端按上传顺序渲染）。"""
    if not items:
        raise BizError(Code.PARAM_INVALID, "请至少上传 1 张图片")
    if len(items) > settings.MAX_IMAGES_PER_REQUEST:
        raise BizError(
            Code.IMAGE_TOO_LARGE,
            f"最多上传 {settings.MAX_IMAGES_PER_REQUEST} 张图片",
        )
    return [process_image(content, filename) for filename, content in items]
