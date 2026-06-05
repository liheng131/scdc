"""
数学验证服务单元测试

覆盖：
- 4 种运算都能正确生成且 answer 正确
- 一次性消费：同一 token 第二次校验失败
- TTL 过期：通过 monkeypatch 模拟时间流逝
"""
import time
import pytest

from app.services import captcha
from app.services.captcha import generate_captcha, validate_captcha


@pytest.fixture(autouse=True)
def _clear_captcha_store():
    """每个用例前后清空缓存，避免污染"""
    captcha._captcha_store.clear()
    yield
    captcha._captcha_store.clear()


def test_generate_captcha_returns_expected_keys():
    result = generate_captcha()
    assert "token" in result
    assert "question" in result
    assert "answer" in result
    assert isinstance(result["token"], str) and len(result["token"]) > 0
    assert "= ?" in result["question"]


def test_generate_captcha_covers_all_operators():
    """反复生成，期望至少覆盖 4 种运算符各一次"""
    seen = set()
    for _ in range(200):
        q = generate_captcha()["question"]
        if " + " in q:
            seen.add("+")
        elif " - " in q:
            seen.add("-")
        elif " × " in q:
            seen.add("*")
        elif " ÷ " in q:
            seen.add("/")
        if len(seen) == 4:
            break
    assert seen == {"+", "-", "*", "/"}


def test_validate_captcha_correct_answer():
    result = generate_captcha()
    assert validate_captcha(result["token"], result["answer"]) is True


def test_validate_captcha_wrong_answer():
    result = generate_captcha()
    assert validate_captcha(result["token"], result["answer"] + 1) is False


def test_validate_captcha_one_time_consume():
    """一次性消费：第一次正确，第二次（无论什么答案）都失败"""
    result = generate_captcha()
    assert validate_captcha(result["token"], result["answer"]) is True
    assert validate_captcha(result["token"], result["answer"]) is False


def test_validate_captcha_unknown_token():
    assert validate_captcha("nonexistent-token", 0) is False


def test_validate_captcha_ttl_expiry(monkeypatch):
    """通过把内部 timer 替换为一个返回远未来时间的函数来模拟 TTL 过期"""
    result = generate_captcha()

    # 直接替换 cachetools 内部 _Timer 封装的真实 timer 函数
    # _TimedCache.__timer -> _Timer.__timer
    inner_timer = captcha._captcha_store._TimedCache__timer
    real_timer_attr = "_TimedCache__timer"  # name-mangled private on _Timer
    original = inner_timer._Timer__timer  # _Timer._Timer__timer is the raw func
    future = time.monotonic() + captcha._captcha_store.ttl + 1
    monkeypatch.setattr(
        inner_timer, "_Timer__timer", lambda: future
    )

    # 触发一次 expire 清理过期项
    captcha._captcha_store.expire()

    assert captcha._captcha_store.get(result["token"]) is None
    assert validate_captcha(result["token"], result["answer"]) is False
