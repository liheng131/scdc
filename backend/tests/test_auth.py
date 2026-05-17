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
