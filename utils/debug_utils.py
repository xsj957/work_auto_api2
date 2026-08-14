# -*- coding: utf-8 -*-
"""
日志工具
========
提供 info() 日志函数和 @capture_failure 失败捕获装饰器。
日志级别仅允许：info / warning / error。

使用示例：
    from utils.debug_utils import info, capture_failure

    @capture_failure
    def test_something(self, api_client):
        response = api_client.post("/api/endpoint", data)
        info(f"响应数据: {response.data}")
"""

# 1. 标准库
import json
import time
import traceback
from functools import wraps
from typing import Any, Callable, Dict, Optional

# 2. 第三方库
import pytest

# 3. 项目模块
from utils.log_control import INFO, ERROR, WARNING


# ================================================================
#  调试日志（始终输出，写入测试日志文件）
# ================================================================

def info(message: str, *args, **kwargs):
    """
    输出业务信息日志（始终输出到测试日志文件）

    Args:
        message: 日志消息
        *args: 格式化参数
        **kwargs: 格式化参数

    使用示例：
        info("请求参数: {}", params)
        debug("响应数据: {}", response.data)
        info("用户信息: user_id={}, name={}", user_id, user_name)
    """
    if args or kwargs:
        try:
            message = message.format(*args, **kwargs)
        except Exception as e:
            ERROR.logger.warning(f"调试日志格式化失败: {e}")
    INFO.logger.info(message)


# ================================================================
#  失败捕获
# ================================================================

class FailureCapture:
    """失败捕获器"""

    def __init__(self):
        self._failures = []

    def capture(
        self,
        test_name: str,
        error: Exception,
        request_info: Dict = None,
        response_info: Dict = None
    ):
        failure = {
            "test_name": test_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "timestamp": time.time(),
            "request_info": request_info or {},
            "response_info": response_info or {}
        }
        self._failures.append(failure)
        ERROR.logger.error(f"测试失败已捕获: {test_name}")

    def get_failures(self) -> list:
        return self._failures.copy()

    def clear(self):
        self._failures.clear()

    def has_failures(self) -> bool:
        return len(self._failures) > 0

    def export_to_json(self, file_path: str):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self._failures, f, indent=2, ensure_ascii=False)
        INFO.logger.info(f"失败信息已导出到: {file_path}")


failure_capture = FailureCapture()


def capture_failure(func: Callable) -> Callable:
    """
    失败捕获装饰器

    自动捕获测试失败信息并记录到 Allure 报告
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            test_name = func.__name__
            failure_capture.capture(
                test_name=test_name,
                error=e
            )

            try:
                import allure
                allure.attach(
                    traceback.format_exc(),
                    name="错误堆栈",
                    attachment_type=allure.attachment_type.TEXT
                )

                if 'api_client' in kwargs:
                    client = kwargs['api_client']
                    if hasattr(client, 'last_request'):
                        allure.attach(
                            json.dumps(client.last_request, indent=2, ensure_ascii=False),
                            name="失败请求详情",
                            attachment_type=allure.attachment_type.JSON
                        )
            except ImportError:
                pass

            raise

    return wrapper


# ================================================================
#  Pytest 钩子
# ================================================================

def pytest_runtest_makereport(item, call):
    """
    测试失败时自动捕获详情（在 conftest.py 中注册）
    """
    if call.when == "call" and call.excinfo is not None:
        test_name = item.name
        error = call.excinfo.value

        request_info = {}
        response_info = {}

        if hasattr(item, "funcargs"):
            if "api_client" in item.funcargs:
                client = item.funcargs["api_client"]
                if hasattr(client, "last_request"):
                    request_info = client.last_request

        failure_capture.capture(
            test_name=test_name,
            error=error,
            request_info=request_info,
            response_info=response_info
        )
