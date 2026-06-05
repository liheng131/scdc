"""
数学验证服务

设计目标：
- 拦截机器流量（不防专业人士，仅防脚本）
- 真人几乎零成本（10 以内加减乘除）
- 无第三方依赖（无图形验证码库）

为什么用 TTLCache 而不是 Redis：
- 验证码生命周期短（5 分钟），不需要持久化
- 单进程内存足够；多 worker 时每 worker 各自一份（小损失）
- 零运维成本
"""
import random
import uuid
from cachetools import TTLCache


# token -> (answer: int, created_at: float)
_captcha_store: TTLCache = TTLCache(maxsize=10000, ttl=300)

# 出题符号
_OPERATORS = ["+", "-", "*", "/"]


def _generate_add() -> tuple[str, int]:
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    return f"{a} + {b} = ?", a + b


def _generate_sub() -> tuple[str, int]:
    a = random.randint(1, 10)
    b = random.randint(1, a)  # 保证非负
    return f"{a} - {b} = ?", a - b


def _generate_mul() -> tuple[str, int]:
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    return f"{a} × {b} = ?", a * b


def _generate_div() -> tuple[str, int]:
    # 保证整除：先生成商，再生成被除数
    b = random.randint(2, 10)
    quotient = random.randint(1, 10)
    a = b * quotient
    return f"{a} ÷ {b} = ?", quotient


_GENERATORS = [_generate_add, _generate_sub, _generate_mul, _generate_div]


def generate_captcha() -> dict:
    """生成一道新的算式与对应的 token（5 分钟内有效）"""
    gen = random.choice(_GENERATORS)
    question, answer = gen()
    token = str(uuid.uuid4())
    _captcha_store[token] = answer
    return {"token": token, "question": question, "answer": answer}


def validate_captcha(token: str, answer: int) -> bool:
    """
    校验用户的答案。
    一次性消费：无论对错，校验后从缓存删除该 token。
    """
    expected = _captcha_store.pop(token, None)
    if expected is None:
        return False
    return int(answer) == int(expected)
