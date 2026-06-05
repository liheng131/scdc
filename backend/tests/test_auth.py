import pytest
from httpx import AsyncClient
from app.main import app
from app.core.security import verify_password, get_password_hash
from app.core.db import get_db
from app.models.user import User

def test_security_hashing():
    password = "supersecretpassword"
    hashed = get_password_hash(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)

@pytest.mark.asyncio
async def test_login_access_token_success(async_db):
    app.dependency_overrides[get_db] = lambda: async_db
    
    # Prepare mock user
    hashed_password = get_password_hash("testpassword")
    test_user = User(
        username="testuser",
        email="test@example.com",
        password_hash=hashed_password,
        role="viewer",
        status="active"
    )
    async_db.add(test_user)
    await async_db.commit()

    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/auth/login/access-token",
            data={"username": "testuser", "password": "testpassword"}
        )
    
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    assert tokens["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_access_token_failure(async_db):
    app.dependency_overrides[get_db] = lambda: async_db

    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/auth/login/access-token",
            data={"username": "nonexistent", "password": "password"}
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Incorrect email or password"


def test_captcha_token_and_answer():
    """captcha 服务：返回 token/question/answer，且一次性消费"""
    from app.services.captcha import generate_captcha, validate_captcha
    data = generate_captcha()
    assert "token" in data and "question" in data and "answer" in data
    # 验证答案正确
    assert validate_captcha(data["token"], data["answer"]) is True
    # 二次消费应失败
    assert validate_captcha(data["token"], data["answer"]) is False


@pytest.mark.asyncio
async def test_register_success_and_unique(async_db):
    """
    注册端点：
    1. 注册成功 → 201
    2. 邮箱重复 → 409 EMAIL_TAKEN
    3. 用户名重复 → 409 USERNAME_TAKEN
    4. captcha 错误 → 400 INVALID_CAPTCHA
    """
    from app.services.captcha import generate_captcha

    app.dependency_overrides[get_db] = lambda: async_db

    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. 注册成功
        cap = generate_captcha()
        payload = {
            "email": "newuser@example.com",
            "username": "newuser1",
            "password": "Passw0rd1",
            "confirm_password": "Passw0rd1",
            "captcha_token": cap["token"],
            "captcha_answer": cap["answer"],
        }
        r = await ac.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 201
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["email"] == "newuser@example.com"
        assert body["data"]["username"] == "newuser1"
        assert body["data"]["role"] == "viewer"

        # 2. 邮箱重复 → 409 EMAIL_TAKEN
        cap2 = generate_captcha()
        payload2 = {
            **payload,
            "username": "otheruser",
            "captcha_token": cap2["token"],
            "captcha_answer": cap2["answer"],
        }
        r2 = await ac.post("/api/v1/auth/register", json=payload2)
        assert r2.status_code == 409
        assert r2.json()["detail"] == "EMAIL_TAKEN"

        # 3. 用户名重复 → 409 USERNAME_TAKEN
        cap3 = generate_captcha()
        payload3 = {
            **payload,
            "email": "another@example.com",
            "captcha_token": cap3["token"],
            "captcha_answer": cap3["answer"],
        }
        r3 = await ac.post("/api/v1/auth/register", json=payload3)
        assert r3.status_code == 409
        assert r3.json()["detail"] == "USERNAME_TAKEN"

        # 4. captcha 错误 → 400 INVALID_CAPTCHA
        cap4 = generate_captcha()
        payload4 = {
            **payload,
            "email": "third@example.com",
            "username": "thirduser",
            "captcha_token": cap4["token"],
            "captcha_answer": 9999,  # 错误答案
        }
        r4 = await ac.post("/api/v1/auth/register", json=payload4)
        assert r4.status_code == 400
        assert r4.json()["detail"] == "INVALID_CAPTCHA"


@pytest.mark.asyncio
async def test_register_get_captcha_endpoint(async_db):
    """GET /captcha 端点应返回 token 与 question，且不泄露 answer"""
    app.dependency_overrides[get_db] = lambda: async_db
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/auth/captcha")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert "token" in body["data"]
        assert "question" in body["data"]
        # 不应泄露 answer
        assert "answer" not in body["data"]
