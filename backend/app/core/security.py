"""
安全与认证模块

职责：
- 密码哈希与验证（bcrypt 算法）
- JWT（JSON Web Token）令牌生成
- API Key 对称加密存储

选择 bcrypt 的原因：
- 内置盐值（salt），无需额外管理
- 计算成本可调，能有效抵御暴力破解
- 是 OWASP 推荐的密码存储算法
"""

from datetime import datetime, timedelta
from typing import Any, Union
from passlib.context import CryptContext
import jwt
from cryptography.fernet import Fernet
from app.core.config import settings

# 密码哈希上下文：使用 bcrypt，自动标记旧算法为"弃用"以便渐进式迁移
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = settings.jwt_algorithm


def _get_fernet() -> Fernet:
    key = settings.secret_key.encode("utf-8")[:32].ljust(32, b"0")
    return Fernet(key.encode("base64") if hasattr(key, "encode") else __import__("base64").b64encode(key))


def encrypt_api_key(plain: str) -> str:
    if not plain:
        return ""
    import base64
    key = settings.secret_key.encode("utf-8")[:32].ljust(32, b"\0")
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted: str) -> str:
    if not encrypted:
        return ""
    import base64
    key = settings.secret_key.encode("utf-8")[:32].ljust(32, b"\0")
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与数据库中哈希值是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """将明文密码转换为 bcrypt 哈希值，用于存储到数据库"""
    return pwd_context.hash(password)

def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None
) -> str:
    """
    生成 JWT 访问令牌

    参数：
    - subject：令牌主体（通常为用户 ID 字符串）
    - expires_delta：自定义过期时间，不传则使用配置中的默认值

    返回：
    - 编码后的 JWT 字符串

    令牌包含 claims：
    - exp：过期时间戳
    - sub：主体标识（用户 ID）
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt
