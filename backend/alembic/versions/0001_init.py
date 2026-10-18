"""init schema：users / diagnosis_records / diseases / feedbacks / quota_usages / admins

字段与《AI园艺医生-项目开发准备文档》3.5.2 建表 SQL 对齐；
唯一差异：diagnosis_records 增加 deleted_at，用于软删除（API 要求 DELETE /diagnosis/{id} 软删除）。

Revision ID: 0001_init
Revises:
Create Date: 2026-10-17

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 用户 ----------
    op.create_table(
        "users",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("openid", sa.String(64), nullable=False, comment="微信 openid"),
        sa.Column("unionid", sa.String(64), nullable=True),
        sa.Column("nickname", sa.String(64), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("openid", name="uk_openid"),
        mysql_engine="InnoDB",
        comment="用户",
    )

    # ---------- 诊断记录 ----------
    op.create_table(
        "diagnosis_records",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("image_urls", sa.JSON(), nullable=False, comment="图片地址数组"),
        sa.Column("image_hash", sa.String(64), nullable=True, comment="首图 sha256，用于缓存命中"),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="created",
            comment="created/recognizing/success/degraded/failed/corrected",
        ),
        sa.Column("prompt_version", sa.String(16), nullable=True),
        sa.Column("model_name", sa.String(64), nullable=True),
        sa.Column("disease_name", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True, comment="结构化识别结果"),
        sa.Column("cost_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        comment="诊断记录",
    )
    op.create_index("idx_user_time", "diagnosis_records", ["user_id", "created_at"])
    op.create_index("idx_hash", "diagnosis_records", ["image_hash"])

    # ---------- 病虫害知识库 ----------
    op.create_table(
        "diseases",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("aliases", sa.String(255), nullable=True),
        sa.Column("category", sa.String(32), nullable=True, comment="真菌性/细菌性/病毒性/虫害/生理性"),
        sa.Column("symptoms", sa.Text(), nullable=True),
        sa.Column("causes", sa.Text(), nullable=True),
        sa.Column("plan_l1", sa.JSON(), nullable=True, comment="家庭安全处置"),
        sa.Column("plan_l2", sa.JSON(), nullable=True, comment="低毒合规处置"),
        sa.Column("plan_l3", sa.JSON(), nullable=True, comment="专业干预"),
        sa.Column("safety_notes", sa.Text(), nullable=True),
        sa.Column("confused_with", sa.String(255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uk_name"),
        mysql_engine="InnoDB",
        comment="病虫害知识库",
    )
    op.create_index("idx_category", "diseases", ["category"])

    # ---------- 反馈 ----------
    op.create_table(
        "feedbacks",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("record_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("type", sa.String(16), nullable=False, comment="like/dislike/wrong"),
        sa.Column("correct_name", sa.String(64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        comment="用户反馈",
    )
    op.create_index("idx_record", "feedbacks", ["record_id"])

    # ---------- 每日额度 ----------
    op.create_table(
        "quota_usages",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("limit_count", sa.Integer(), nullable=False, server_default="10"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "stat_date", name="uk_user_date"),
        mysql_engine="InnoDB",
        comment="每日额度",
    )

    # ---------- 管理员 ----------
    op.create_table(
        "admins",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uk_username"),
        mysql_engine="InnoDB",
        comment="后台管理员",
    )


def downgrade() -> None:
    op.drop_table("admins")
    op.drop_table("quota_usages")
    op.drop_index("idx_record", table_name="feedbacks")
    op.drop_table("feedbacks")
    op.drop_index("idx_category", table_name="diseases")
    op.drop_table("diseases")
    op.drop_index("idx_hash", table_name="diagnosis_records")
    op.drop_index("idx_user_time", table_name="diagnosis_records")
    op.drop_table("diagnosis_records")
    op.drop_table("users")
