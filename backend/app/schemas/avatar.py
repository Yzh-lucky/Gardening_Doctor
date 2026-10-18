"""头像上传出参。"""
from pydantic import BaseModel


class AvatarOut(BaseModel):
    avatar_url: str
