"""应用配置：用 pydantic-settings 从 .env 读取，集中管理所有可变参数。"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（config.py 位于 backend/app/core/ 下）
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 基础 ----------
    APP_NAME: str = "AI 园艺医生"
    APP_ENV: str = "dev"  # dev / staging / production
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "dev-secret-key-change-me"

    # ---------- 数据库 ----------
    DATABASE_URL: str = "mysql+pymysql://root:root@127.0.0.1:3306/gardening_doctor?charset=utf8mb4"
    DB_ECHO: bool = False

    # ---------- 微信 ----------
    WECHAT_APPID: str = ""
    WECHAT_SECRET: str = ""
    # 未配置 AppID 时（本地开发）允许用 mock code 直接登录，见 services/wechat.py
    WECHAT_MOCK_LOGIN: bool = True

    # ---------- 大模型 ----------
    LLM_PROVIDER: str = "stub"  # stub / qwen / doubao
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_BASE_URL: str = ""
    LLM_TIMEOUT: int = 15

    # ---------- 业务阈值 ----------
    MAX_IMAGES_PER_REQUEST: int = 3
    MAX_IMAGE_SIZE_MB: int = 2
    DAILY_FREE_QUOTA: int = 10
    USER_TOKEN_EXPIRE_DAYS: int = 7
    ADMIN_TOKEN_EXPIRE_HOURS: int = 12

    # ---------- 限流与成本熔断（T3.3） ----------
    # 单用户每分钟请求数 + 全局每秒请求数，两个维度都超则返回 3002 / 429
    RATE_LIMIT_USER_PER_MINUTE: int = 6
    RATE_LIMIT_GLOBAL_QPS: int = 10
    # 成本折算：按 token 计价，今日累计超过上限就熔断，避免 Key 配错时费用失控
    LLM_PRICE_PER_1K_TOKENS: float = 0.02
    DAILY_COST_LIMIT_CNY: float = 50.0

    # ---------- 后台种子账号 ----------
    # 只被 scripts/seed_admin.py 读取，用来初始化/重置后台管理员；服务启动不会自动建账号
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123456"

    # ---------- 存储与跨域 ----------
    UPLOAD_DIR: str = "uploads"
    # 图片对外 URL 前缀：必须与 STATIC_MOUNT_PATH 挂载点一致，否则 /static 下取不到文件
    UPLOAD_URL_PREFIX: str = "/static"
    STATIC_MOUNT_PATH: str = "/static"
    CORS_ORIGINS: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def _check_db_url(cls, v: str) -> str:
        if not v or v.startswith("mysql+") is False:
            raise ValueError("DATABASE_URL 必须是 mysql+pymysql://... 形式")
        return v

    @property
    def upload_path(self) -> Path:
        """图片存储目录的绝对路径，相对路径按 backend/ 解析。"""
        p = Path(self.UPLOAD_DIR)
        return p if p.is_absolute() else (BACKEND_DIR / p)

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS 支持逗号分隔；小程序本身不受 CORS 限制，留空即可。"""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def wechat_configured(self) -> bool:
        return bool(self.WECHAT_APPID and self.WECHAT_SECRET)

    @property
    def llm_configured(self) -> bool:
        return bool(self.LLM_API_KEY and self.LLM_PROVIDER != "stub")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
