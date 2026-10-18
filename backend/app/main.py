"""FastAPI 应用入口。

启动：`uvicorn app.main:app --reload --port 8000`（在 backend/ 目录下执行）
文档：http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import TraceIdMiddleware
from app.routers import admin, auth, diagnosis, diseases, feedback, health, quota, user
from app.services.llm import get_llm_provider

setup_logging()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "app_start",
        extra={"env": settings.APP_ENV, "llm": get_llm_provider().describe(), "upload_dir": str(settings.upload_path)},
    )
    yield
    logger.info("app_stop")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version="1.0.0",
        description="家庭园艺病虫害识别与分层防治方案 · 接口契约见《API接口文档》",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 中间件：trace_id 必须最先加（越早加的越外层）
    app.add_middleware(TraceIdMiddleware)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    # 业务路由统一挂 /api/v1
    api_router = APIRouter(prefix=settings.API_V1_PREFIX)
    api_router.include_router(health.router)
    api_router.include_router(auth.router)
    api_router.include_router(user.router)
    api_router.include_router(quota.router)
    api_router.include_router(diagnosis.router)
    api_router.include_router(feedback.router)
    api_router.include_router(diseases.router)
    api_router.include_router(admin.router)
    app.include_router(api_router)

    # 没有域名期间，图片先由后端静态目录提供；上线前换成已备案的 CDN 域名
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.STATIC_MOUNT_PATH,
        StaticFiles(directory=str(settings.upload_path)),
        name="static",
    )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=settings.DEBUG)
