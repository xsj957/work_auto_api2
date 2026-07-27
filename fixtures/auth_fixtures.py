# -*- coding: utf-8 -*-
"""
认证 Fixtures
=============
提供登录认证、Token 管理等功能。

Fixtures:
1. api_client - API 客户端实例
2. auth_token - 登录 Token
3. merchant_no - 商户编号
4. store_no - 门店编号
5. auth_context - 认证上下文（包含所有认证信息）
"""

import time

import pytest
from utils.config import config
from utils.log_control import WARNING
from core.api_client import APIClient
from core.context import TestContext

# 简化的缓存实现（内存缓存）
_cache = {}

def get_cache(key: str, default: str = "") -> str:
    """获取缓存值"""
    return _cache.get(key, default)

def update_cache(key: str, value: str):
    """更新缓存"""
    _cache[key] = value


@pytest.fixture(scope="session")
def api_client():
    """
    API 客户端（会话级）

    整个测试会话共享同一个客户端实例。

    使用示例：
        def test_something(api_client):
            response = api_client.post("/api/users", data)
    """
    client = APIClient()
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_token(api_client) -> str:
    """
    登录 Token（会话级）

    自动登录并返回 Token，整个测试会话共享。
    登录失败时自动重试 3 次，指数退避。

    使用示例：
        def test_something(api_client, auth_token):
            response = api_client.post(
                "/api/protected",
                data,
                token=auth_token
            )
    """
    # 尝试从缓存获取
    token = get_cache("merchant_token", "")
    if token:
        return token

    # 执行登录（最多重试 3 次）
    max_attempts = 3
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = api_client.post(
                "/merchant-api/system/auth/login",
                {
                    "username": config.business_data['login']['username'],
                    "password": config.business_data['login']['password']
                },
                step_name=f"登录 (第{attempt}次)"
            )

            token = response.get_data("accessToken")
            if not token:
                raise RuntimeError(f"登录失败: 未获取到 accessToken (code={response.code}, msg={response.msg})")

            # 缓存 Token
            update_cache("merchant_token", token)
            return token

        except Exception as e:
            last_error = e
            if attempt < max_attempts:
                wait = 2 ** attempt  # 指数退避: 2s, 4s
                WARNING.logger.warning(f"登录失败，{wait}s 后重试 ({attempt}/{max_attempts}): {e}")
                time.sleep(wait)

    raise RuntimeError(f"登录失败，已重试 {max_attempts} 次: {last_error}")


@pytest.fixture(scope="session")
def merchant_no(api_client, auth_token) -> str:
    """
    商户编号（会话级）

    从登录响应或缓存中获取。

    使用示例：
        def test_something(merchant_no):
            data = {"merchantNo": merchant_no}
    """
    # 尝试从缓存获取
    merchant_no = get_cache("merchantNoZM", "")
    if merchant_no:
        return merchant_no

    # 从配置获取
    merchant_no = config.business_data.get("merchantNo", "")
    if not merchant_no:
        # 尝试从登录响应获取
        response = api_client.post(
            "/merchant-api/system/auth/login",
            {
                "username": config.business_data['login']['username'],
                "password": config.business_data['login']['password']
            },
            token=auth_token,
            step_name="获取商户信息"
        )
        merchant_no = response.get_data("merchantNo")

    # 缓存商户编号
    if merchant_no:
        update_cache("merchantNoZM", merchant_no)

    return merchant_no


@pytest.fixture(scope="session")
def store_no() -> str:
    """
    门店编号（会话级）

    从配置中获取。

    使用示例：
        def test_something(store_no):
            data = {"storeNo": store_no}
    """
    return config.business_data['storeNo']


@pytest.fixture(scope="session")
def auth_context(auth_token, merchant_no, store_no) -> TestContext:
    """
    认证上下文（会话级）

    包含所有认证信息的 TestContext 对象。

    使用示例：
        def test_something(auth_context):
            token = auth_context.token
            merchant_no = auth_context.merchant_no

            response = api_client.post(
                "/api/endpoint",
                data,
                token=auth_context.token
            )
    """
    ctx = TestContext(
        token=auth_token,
        merchant_no=merchant_no,
        store_no=store_no
    )
    return ctx


# ================================================================
#  便捷 Fixtures（组合）
# ================================================================

@pytest.fixture(scope="function")
def function_auth_context(auth_token, merchant_no, store_no) -> TestContext:
    """
    函数级认证上下文

    每个测试函数都会创建一个新的上下文实例。

    使用示例：
        def test_something(function_auth_context):
            # 可以安全地修改上下文，不会影响其他测试
            function_auth_context.set("custom_key", "custom_value")
    """
    return TestContext(
        token=auth_token,
        merchant_no=merchant_no,
        store_no=store_no
    )
