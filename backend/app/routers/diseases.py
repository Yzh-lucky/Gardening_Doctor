"""病虫害科普接口（API接口文档 3.8）：免鉴权只读知识库，供小程序「常见病虫害科普」浏览与搜索。

两个接口：
- GET /diseases        分页 + 关键字/类别筛选，返回精简字段列表
- GET /diseases/{id}   返回单条完整知识（含三档方案）

约定：
- 免鉴权：不挂 CurrentUserId，游客也能查看；
- 只读：不写库，直接查 diseases 表（知识库由后台 /admin/diseases 维护）；
- 找不到记录返回 4001（与详情/反馈等接口同一口径）。
"""
from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.core.deps import DbSession, PageParams
from app.core.response import ApiResponse, BizError, Code, PageData, ok
from app.models.disease import Disease
from app.schemas.disease import DiseaseBrief, DiseaseDetail, disease_brief_out, disease_detail_out

router = APIRouter(prefix="/diseases", tags=["diseases"])


@router.get("", response_model=ApiResponse[PageData[DiseaseBrief]], summary="科普列表")
async def list_diseases(
    db: DbSession,
    page_params: PageParams,
    keyword: str | None = Query(default=None, description="按病名/别名模糊搜索"),
    category: str | None = Query(default=None, description="按类别过滤，如 真菌性病害"),
) -> ApiResponse[PageData[DiseaseBrief]]:
    """分页返回知识库条目；keyword 只匹配病名与别名，症状不进检索词（科普搜索按病名找更准）。"""
    page, page_size = page_params
    conditions = []
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        conditions.append(or_(Disease.name.like(pattern), Disease.aliases.like(pattern)))
    if category and category.strip():
        conditions.append(Disease.category == category.strip())

    total = int(db.scalar(select(func.count()).select_from(Disease).where(*conditions)) or 0)
    rows = db.scalars(
        select(Disease)
        .where(*conditions)
        .order_by(Disease.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ok(
        PageData[DiseaseBrief](
            list=[disease_brief_out(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            has_more=page * page_size < total,
        )
    )


@router.get("/{disease_id}", response_model=ApiResponse[DiseaseDetail], summary="科普详情")
async def disease_detail(disease_id: int, db: DbSession) -> ApiResponse[DiseaseDetail]:
    """按 id 查一条完整知识库；不存在返回 4001。"""
    disease = db.get(Disease, disease_id)
    if disease is None:
        raise BizError(Code.RECORD_NOT_FOUND, "病害不存在")
    return ok(disease_detail_out(disease))
