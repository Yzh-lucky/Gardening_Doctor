"""内容安全（T3.4）：调用微信 wxa 安全接口做图片 + 文本合规检测，违规返回 2004 且不扣额度。

三条约定：
1. **未配置 AppID 就跳过**：本地/开发阶段没有微信凭证，不能因此让识别不可用，
   只打一条 warning 日志（告警）放行，等线上配好凭证再真正生效。
2. **检测不可用（网络/凭证失效）时放行（fail-open）**：安全接口是辅助关卡，
   挂了不能和识别主链路一起挂；只记 warning，交给后续人工/日志巡检。
3. **违规直接拦**：命中微信的违规码 87014 抛 2004，在扣额度之前拦掉。

调用点：POST /diagnosis 在校验图片格式/体积之后、进入 recognize 之前，
这样被拦的请求既不落库也不消耗额度。
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.response import BizError, Code
from app.services.storage import UploadedImage

logger = get_logger("app.content_safety")

_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
_IMG_CHECK_URL = "https://api.weixin.qq.com/wxa/img_sec_check"
_MSG_CHECK_URL = "https://api.weixin.qq.com/wxa/msg_sec_check"

# 微信内容安全接口的"内容违规"错误码
UNSAFE_ERRCODE = 87014

_TIMEOUT = 5


async def _get_access_token() -> str:
    params = {
        "grant_type": "client_credential",
        "appid": settings.WECHAT_APPID,
        "secret": settings.WECHAT_SECRET,
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_TOKEN_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"access_token 获取失败: {data}")
    return token


async def _img_sec_check(token: str, image: UploadedImage) -> int:
    """返回微信 errcode（0 表示通过）。异常向上抛，由 scan_images 统一按 fail-open 处理。"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _IMG_CHECK_URL,
            params={"access_token": token},
            files={"media": (f"image.{_ext(image.mime)}", image.content, image.mime)},
        )
        resp.raise_for_status()
        return int(resp.json().get("errcode", 0))


async def _msg_sec_check(token: str, text: str) -> int:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _MSG_CHECK_URL,
            params={"access_token": token},
            json={"content": text, "version": 2, "scene": 2},
        )
        resp.raise_for_status()
        return int(resp.json().get("errcode", 0))


def _ext(mime: str) -> str:
    return {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")


async def scan_images(images: list[UploadedImage]) -> None:
    if not settings.wechat_configured:
        logger.warning("content_safety_skipped", extra={"scope": "image", "reason": "wechat_not_configured"})
        return
    try:
        token = await _get_access_token()
        for image in images:
            errcode = await _img_sec_check(token, image)
            if errcode == UNSAFE_ERRCODE:
                logger.warning("content_unsafe", extra={"scope": "image", "errcode": errcode})
                raise BizError(Code.CONTENT_UNSAFE, "图片内容不合规，请更换后重试")
    except BizError:
        raise
    except Exception as exc:  # noqa: BLE001 - 安全接口不可用时放行，不能拖垮主链路
        logger.warning("content_safety_unavailable", extra={"scope": "image", "error": str(exc)[:200]})


async def scan_text(text: str | None) -> None:
    cleaned = (text or "").strip()
    if not cleaned:
        return
    if not settings.wechat_configured:
        logger.warning("content_safety_skipped", extra={"scope": "text", "reason": "wechat_not_configured"})
        return
    try:
        token = await _get_access_token()
        errcode = await _msg_sec_check(token, cleaned)
        if errcode == UNSAFE_ERRCODE:
            logger.warning("content_unsafe", extra={"scope": "text", "errcode": errcode})
            raise BizError(Code.CONTENT_UNSAFE, "文本内容不合规，请修改后重试")
    except BizError:
        raise
    except Exception as exc:  # noqa: BLE001 - 同上，fail-open
        logger.warning("content_safety_unavailable", extra={"scope": "text", "error": str(exc)[:200]})
