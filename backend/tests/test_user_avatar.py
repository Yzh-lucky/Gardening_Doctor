"""登录模块补充：POST /user/avatar 头像上传接口验收。

覆盖：未登录鉴权（1001/401）、合法图片上传（落盘 + 返回 /static 地址）、
非法格式（2002）、以及"上传接口不写库"（写库仍走 PUT /user/profile）。

运行：在 backend/ 目录执行 `python -m pytest tests -q`
"""
from conftest import PNG_BYTES


def test_upload_avatar_requires_auth(client):
    resp = client.post(
        "/api/v1/user/avatar",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 1001


def test_upload_avatar_returns_persistable_url(auth):
    resp = auth["client"].post(
        "/api/v1/user/avatar",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
        headers=auth["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["avatar_url"].startswith("/static/")


def test_upload_avatar_rejects_non_image(auth):
    resp = auth["client"].post(
        "/api/v1/user/avatar",
        files={"file": ("a.txt", b"not-an-image", "text/plain")},
        headers=auth["headers"],
    )
    assert resp.json()["code"] == 2002


def test_upload_avatar_does_not_write_profile(auth):
    """上传只落盘，不写库：users.avatar_url 保持不变，写库仍由 PUT /user/profile 负责。"""
    before = auth["client"].get("/api/v1/user/profile", headers=auth["headers"]).json()["data"]
    assert before["avatar_url"] is None

    auth["client"].post(
        "/api/v1/user/avatar",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
        headers=auth["headers"],
    )

    after = auth["client"].get("/api/v1/user/profile", headers=auth["headers"]).json()["data"]
    assert after["avatar_url"] is None
