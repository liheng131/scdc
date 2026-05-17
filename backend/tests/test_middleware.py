from fastapi.testclient import TestClient
from app.main import app
from app.core.exceptions import BusinessException
from app.api.router import api_router

# 注册一个测试用的抛出异常的路由
@app.get("/api/v1/test/biz_error")
async def biz_error():
    raise BusinessException("测试业务异常", code=400)

@app.get("/api/v1/test/sys_error")
async def sys_error():
    raise ValueError("系统异常")

client = TestClient(app, raise_server_exceptions=False)

def test_health_check_format():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["code"] == 0
    assert json_data["msg"] == "success"
    assert "version" in json_data["data"]

def test_timing_middleware():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "X-Process-Time" in response.headers

def test_cors():
    response = client.options("/api/v1/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

def test_business_exception_handler():
    response = client.get("/api/v1/test/biz_error")
    assert response.status_code == 400
    json_data = response.json()
    assert json_data["code"] == 400
    assert json_data["msg"] == "测试业务异常"

def test_global_exception_handler():
    response = client.get("/api/v1/test/sys_error")
    assert response.status_code == 500
    json_data = response.json()
    assert json_data["code"] == 500
    assert json_data["msg"] == "服务器内部错误"

def test_validation_exception_handler():
    # 利用 FastAPI 的自动参数校验触发 422
    @app.get("/api/v1/test/validation")
    async def validation_test(id: int):
        return {"id": id}
    
    response = client.get("/api/v1/test/validation?id=abc")
    assert response.status_code == 422
    json_data = response.json()
    assert json_data["code"] == 422
    assert json_data["msg"] == "参数校验失败"
    assert "data" in json_data
