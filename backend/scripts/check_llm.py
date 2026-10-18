"""大模型连通性自测脚本（任务 T1.6 验收）。

用法（在 backend/ 目录，先激活 venv）：
    python scripts/check_llm.py                 # 用 .env 里配置的 provider
    python scripts/check_llm.py --provider stub # 强制用假模型
    python scripts/check_llm.py --image leaf.jpg # 带一张真实图片测多模态

输出：provider / model / 耗时 / token 数 / 模型返回的前 500 字。
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import get_logger, setup_logging  # noqa: E402
from app.services.llm import LLMError, LLMImage, get_llm_provider, reset_llm_provider  # noqa: E402

SAMPLE_PROMPT = (
    "你是家庭园艺病虫害诊断助手。请判断图中植物可能患了什么病虫害，"
    "并以 JSON 输出，字段包括 disease_name、confidence、symptom_summary、plan_l1_safe。"
)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", help="覆盖 LLM_PROVIDER，例如 stub/qwen/doubao")
    parser.add_argument("--image", action="append", default=[], help="图片路径，可传多次")
    parser.add_argument("--prompt", default=SAMPLE_PROMPT)
    args = parser.parse_args()

    setup_logging()
    logger = get_logger("scripts.check_llm")

    if args.provider:
        import os

        os.environ["LLM_PROVIDER"] = args.provider
        # 已实例化的 settings/缓存要重建，才能生效
        from app.core import config as config_module

        config_module.get_settings.cache_clear()
        config_module.settings = config_module.get_settings()
        reset_llm_provider()

    provider = get_llm_provider()
    print(f"[check_llm] provider={provider.describe()} health={provider.health()}")

    images = []
    for path in args.image:
        p = Path(path)
        if not p.exists():
            print(f"[check_llm] 图片不存在：{p}")
            return 2
        suffix = p.suffix.lower().lstrip(".")
        mime = "image/png" if suffix == "png" else "image/webp" if suffix == "webp" else "image/jpeg"
        images.append(LLMImage(content=p.read_bytes(), mime_type=mime))
    print(f"[check_llm] 附带图片 {len(images)} 张")

    try:
        resp = await provider.chat(system_prompt="你是专业的植物医生。", user_prompt=args.prompt, images=images)
    except LLMError as exc:
        logger.error("llm_check_failed", extra={"error": str(exc), "retryable": exc.retryable})
        print(f"[check_llm] 调用失败：{exc}")
        return 1

    print(f"[check_llm] model={resp.model_name} latency_ms={resp.latency_ms} tokens={resp.total_tokens}")
    print("[check_llm] 返回内容（前 500 字）：")
    print(resp.text[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
