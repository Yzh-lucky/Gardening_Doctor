"""头像上传接口（新增模块，不修改任何已有接口）。

POST /user/avatar：登录用户上传单张头像，复用 services/storage 的魔数与大小校验、
sha256 去重落盘，返回可持久化的 avatar_url；再由已有的 PUT /user/profile 写入用户资料。
"""
from fastapi import APIRouter, File, UploadFile

from app.core.deps import CurrentUserId
from app.core.response import ApiResponse, ok
from app.schemas.avatar import AvatarOut
from app.services.storage import process_image

router = APIRouter(prefix="/user", tags=["user"])


@router.post("/avatar", response_model=ApiResponse[AvatarOut], summary="上传头像")
async def upload_avatar(
    user_id: CurrentUserId,
    file: UploadFile = File(..., description="头像图片，单张 ≤ 2MB，支持 jpg/jpeg/png/webp"),
) -> ApiResponse[AvatarOut]:
    # user_id 仅用于鉴权（未登录返回 1001/401），不写库，写库统一交给 PUT /user/profile
    content = await file.read()
    image = process_image(content, file.filename or "")
    return ok(AvatarOut(avatar_url=image.url))
