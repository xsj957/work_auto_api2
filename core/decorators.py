# -*- coding: utf-8 -*-
"""
装饰器工具
==========
提供常用的测试装饰器，包括重试、性能监控、资源管理等。

使用示例：
    @retry(max_attempts=3, delay=1)
    def test_flaky_api(self):
        ...

    @with_timing
    def test_slow_api(self):
        ...
"""

# 1. 标准库
import time
import functools
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Callable, Any, Optional

# 2. 项目模块
from utils.log_control import INFO, ERROR


def retry(max_attempts: int = 3, delay: float = 1.0,
          exceptions: tuple = (Exception,)) -> Callable:
    """
    重试装饰器

    当函数抛出指定异常时，自动重试执行。

    Args:
        max_attempts: 最大尝试次数（默认 3）
        delay: 重试间隔（秒，默认 1.0）
        exceptions: 需要捕获的异常类型（默认捕获所有 Exception）

    Returns:
        Callable: 装饰后的函数

    使用示例：
        @retry(max_attempts=3, delay=2)
        def test_flaky_api(self, client):
            response = client.post("/api/unstable", data)
            assert response.code == 200

        # 指定特定异常
        @retry(max_attempts=5, exceptions=(ConnectionError, TimeoutError))
        def test_network_api(self):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        INFO.logger.warning(
                            f"[重试] {func.__name__} 第 {attempt}/{max_attempts} 次失败: {e}, "
                            f"{delay}秒后重试..."
                        )
                        time.sleep(delay)
                    else:
                        ERROR.logger.error(
                            f"[重试] {func.__name__} 所有 {max_attempts} 次尝试均失败: {e}"
                        )

            # 所有尝试都失败，抛出最后一个异常
            raise last_exception

        return wrapper
    return decorator


def with_timing(func: Callable) -> Callable:
    """
    性能监控装饰器

    记录函数执行时间，并在日志中输出。

    Args:
        func: 被装饰的函数

    Returns:
        Callable: 装饰后的函数

    使用示例：
        @with_timing
        def test_slow_api(self, client):
            response = client.post("/api/slow", data)
            assert response.code == 200

        # 日志输出：
        # [性能] test_slow_api 执行时间: 2.345s
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            INFO.logger.info(f"[性能] {func.__name__} 执行时间: {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            ERROR.logger.error(f"[性能] {func.__name__} 执行时间: {elapsed:.3f}s (失败: {e})")
            raise

    return wrapper


def with_resources(*resource_names: str) -> Callable:
    """
    资源管理装饰器

    自动管理测试资源的创建和清理（需要配合 fixture 使用）。

    注意：这个装饰器主要用于标记，实际资源管理应该通过 pytest fixtures 实现。

    Args:
        *resource_names: 资源名称列表

    Returns:
        Callable: 装饰后的函数

    使用示例：
        @with_resources('region', 'fee', 'desk')
        def test_payment_flow(self, region, fee, desk):
            # 资源会自动创建和清理
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 记录使用的资源（用于调试）
            INFO.logger.info(f"[资源] {func.__name__} 使用资源: {resource_names}")
            return func(*args, **kwargs)

        # 标记使用的资源（可用于 pytest 插件）
        wrapper._resources = resource_names
        return wrapper

    return decorator


def skip_if(condition: bool, reason: str = "") -> Callable:
    """
    条件跳过装饰器

    当条件为 True 时，跳过测试。

    Args:
        condition: 跳过条件
        reason: 跳过原因

    Returns:
        Callable: 装饰后的函数

    使用示例：
        @skip_if(not config.mysql_db.switch, reason="数据库未启用")
        def test_db_feature(self):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if condition:
                import pytest
                pytest.skip(reason)
            return func(*args, **kwargs)

        return wrapper
    return decorator


def timeout(seconds: float) -> Callable:
    """
    超时装饰器

    如果函数执行时间超过指定秒数，抛出 TimeoutError。
    使用 ThreadPoolExecutor 实现，兼容 Windows 和 Linux。

    Args:
        seconds: 超时时间（秒）

    Returns:
        Callable: 装饰后的函数

    使用示例：
        @timeout(10)
        def test_slow_api(self):
            # 如果超过 10 秒，抛出 TimeoutError
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=seconds)
                except FuturesTimeoutError:
                    raise TimeoutError(
                        f"{func.__name__} 执行超时 ({seconds}秒)"
                    )

        return wrapper
    return decorator


def log_call(func: Callable) -> Callable:
    """
    调用日志装饰器

    记录函数的调用参数和返回值。

    Args:
        func: 被装饰的函数

    Returns:
        Callable: 装饰后的函数

    使用示例：
        @log_call
        def create_order(self, desk_no, amount):
            ...

        # 日志输出：
        # [调用] create_order(desk_no='desk_001', amount=20.0)
        # [返回] create_order -> {'order_no': 'order_123'}
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        # 记录调用参数
        INFO.logger.info(f"[调用] {func.__name__}({kwargs})")

        try:
            result = func(*args, **kwargs)
            # 记录返回值
            INFO.logger.info(f"[返回] {func.__name__} -> {result}")
            return result
        except Exception as e:
            ERROR.logger.error(f"[异常] {func.__name__} -> {e}")
            raise

    return wrapper


# ================================================================
#  组合装饰器
# ================================================================

def robust_test(max_attempts: int = 3, timeout_seconds: float = 30) -> Callable:
    """
    健壮测试装饰器（组合：重试 + 超时）

    Args:
        max_attempts: 最大尝试次数
        timeout_seconds: 超时时间（秒）

    Returns:
        Callable: 装饰后的函数

    使用示例：
        @robust_test(max_attempts=3, timeout_seconds=10)
        def test_flaky_api(self):
            ...
    """
    def decorator(func: Callable) -> Callable:
        # 先应用 timeout，再应用 retry
        func = timeout(timeout_seconds)(func)
        func = retry(max_attempts=max_attempts, delay=1.0)(func)
        return func

    return decorator


# ================================================================
#  便捷函数
# ================================================================

def time_execution(func: Callable, *args, **kwargs) -> tuple:
    """
    测量函数执行时间（便捷函数）

    Args:
        func: 要执行的函数
        *args, **kwargs: 函数参数

    Returns:
        tuple: (结果, 执行时间秒数)

    使用示例：
        result, elapsed = time_execution(my_function, arg1, arg2)
        print(f"执行时间: {elapsed:.3f}s")
    """
    start_time = time.time()
    result = func(*args, **kwargs)
    elapsed = time.time() - start_time
    return result, elapsed
