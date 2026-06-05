"""
认证相关的 Pydantic 模型

包含：
- CaptchaOut: 验证接口响应
- RegisterIn: 注册请求（含字段级校验）
- RegisterOut: 注册成功响应
"""
import re
from pydantic import BaseModel, EmailStr, Field, field_validator


class CaptchaOut(BaseModel):
    token: str
    question: str


# 用户名字符白名单：英文字母 / 数字 / 下划线 / 中文
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff]{3,32}$")
# 邮箱正则（Pydantic EmailStr 已含基础校验，这里再加一道）
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=64)
    confirm_password: str = Field(min_length=8, max_length=64)
    captcha_token: str = Field(min_length=1, max_length=64)
    captcha_answer: int

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("USERNAME_FORMAT_INVALID")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("WEAK_PASSWORD")
        return v

    @field_validator("confirm_password")
    @classmethod
    def _validate_confirm(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("PASSWORD_MISMATCH")
        return v


class RegisterOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
