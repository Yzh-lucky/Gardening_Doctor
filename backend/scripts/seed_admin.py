"""初始化（或重置）后台管理员账号。

用法（在 backend/ 目录下执行）：
    .\\.venv\\Scripts\\python.exe -m scripts.seed_admin
    .\\.venv\\Scripts\\python.exe -m scripts.seed_admin --username admin --password 你的密码

账号密码默认取 .env 里的 ADMIN_USERNAME / ADMIN_PASSWORD。
不放在服务启动时自动建号：生产环境"启动即建管理员"是个安全隐患，改成显式执行更稳。
"""
import argparse
import sys
from pathlib import Path

# 允许直接 `python scripts/seed_admin.py` 运行（把 backend/ 加进 sys.path）
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.admin import Admin  # noqa: E402


def seed_admin(username: str, password: str) -> None:
    with SessionLocal() as db:
        admin = db.scalar(select(Admin).where(Admin.username == username))
        if admin is None:
            admin = Admin(username=username, password_hash=hash_password(password))
            db.add(admin)
            action = "created"
        else:
            # 已存在就当"重置密码"用，幂等，方便本地反复跑
            admin.password_hash = hash_password(password)
            action = "password_reset"
        db.commit()
        db.refresh(admin)
        print(f"[seed_admin] {action}: id={admin.id} username={admin.username}")


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化后台管理员账号")
    parser.add_argument("--username", default=settings.ADMIN_USERNAME)
    parser.add_argument("--password", default=settings.ADMIN_PASSWORD)
    args = parser.parse_args()
    seed_admin(args.username, args.password)


if __name__ == "__main__":
    main()
