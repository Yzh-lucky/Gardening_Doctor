"""微信开放平台能力封装：code2session（登录）。内容安全接口在 T3.4 接入。"""
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.response import BizError, Code

logger = get_logger("app.wechat")

CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"

# 微信返回的错误码 → 业务码
_CODE_MAP = {
    40029: Code.WECHAT_CODE_INVALID,   # code 无效
    40163: Code.WECHAT_CODE_INVALID,   # code 已被使用
    45011: Code.COST_CIRCUIT_OPEN,     # 频率限制（这里归到"服务繁忙"，实际由上层决定）
}


@dataclass(slots=True)
class WxSession:
    openid: str
    unionid: str | None = None
    session_key: str | None = None


async def code2session(code: str) -> WxSession:
    """用 code 换 openid。

    本地开发没有 AppID 时走 mock 分支：code 以 `mock_` 开头即可拿到一个稳定的假 openid，
    这样 W1 就能把"登录 → 拿 token → 受保护接口"整条链路跑通，等拿到真实 AppID 再切真接口。
    """
    if not settings.wechat_configured:
        if not settings.WECHAT_MOCK_LOGIN:
            raise BizError(Code.WECHAT_UNAVAILABLE, "服务端未配置微信 AppID/Secret")
        if not code.startswith("mock_"):
            raise BizError(
                Code.WECHAT_CODE_INVALID,
                "本地开发未配置微信 AppID，请使用 mock_ 前缀的 code 登录",
            )
        logger.info("wechat_mock_login", extra={"code_suffix": code[-8:]})
        return WxSession(openid=f"mock_openid_{code[len('mock_'):]}")

    params = {
        "appid": settings.WECHAT_APPID,
        "secret": settings.WECHAT_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        # trust_env=False：忽略 HTTP_PROXY/HTTPS_PROXY 等环境变量，微信接口固定直连，避免被终端里残留的代理配置拖垮
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            resp = await client.get(CODE2SESSION_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("wechat_code2session_http_error", extra={"error": str(exc)})
        raise BizError(Code.WECHAT_UNAVAILABLE) from exc

    errcode = data.get("errcode")
    if errcode:
        logger.warning("wechat_code2session_failed", extra={"errcode": errcode, "errmsg": data.get("errmsg")})
        raise BizError(_CODE_MAP.get(errcode, Code.WECHAT_CODE_INVALID), data.get("errmsg") or None)

    openid = data.get("openid")
    if not openid:
        logger.warning("wechat_code2session_no_openid", extra={"resp": data})
        raise BizError(Code.WECHAT_UNAVAILABLE)
    return WxSession(openid=openid, unionid=data.get("unionid"), session_key=data.get("session_key"))
