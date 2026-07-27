# -*- coding: utf-8 -*-
"""
根级 Pytest 配置
================
1. 将项目根目录注入 sys.path，确保 utils / core / fixtures 等模块可被正确导入
2. 提供全局 pytest 钩子（会话日志、marker 注册等）

说明：
    pytest 收集 testcase/ 下的测试时，默认只把测试文件所在目录加入 sys.path，
    项目根目录下的 utils、core、fixtures 等包无法通过绝对导入找到。
    这里在 conftest 加载阶段（早于所有测试模块导入）把项目根目录插入 sys.path，
    从根源上解决 ModuleNotFoundError。
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

# 尝试导入 allure（可选）
try:
    import allure
    HAS_ALLURE = True
except ImportError:
    HAS_ALLURE = False

# ================================================================
#  路径注入（必须在其他项目模块导入之前执行）
# ================================================================

# 项目根目录 = conftest.py 所在目录
PROJECT_ROOT = str(Path(__file__).parent.resolve())

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ================================================================
#  模块导入（路径注入之后）
# ================================================================

from utils.log_control import INFO, switch_test_logger
from utils.markers import register_markers

# 直接导入所有 fixtures（不再通过 fixtures/conftest.py 中转）
from fixtures.auth_fixtures import (
    api_client,
    auth_token,
    merchant_no,
    store_no,
    auth_context,
    function_auth_context,
)
from fixtures.resource_fixtures import (
    lighting_resources,
    lighting_resources_2,
)


# ================================================================
#  Pytest Hooks
# ================================================================

def pytest_configure(config):
    """在 pytest 启动时注册所有自定义 markers"""
    register_markers(config)


def pytest_sessionstart(session):
    """
    测试会话开始钩子

    在整个测试会话开始前执行，创建本次会话的日志文件。
    日志文件命名：autoapi_{YYYYMMDD_HHMMSS}.log
    """
    # 生成会话级日志文件名（按秒级时间戳确保每次执行唯一）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_logger_name = f"test_framework_session_{timestamp}"

    from utils.log_control import get_logger
    session_logger = get_logger(name=session_logger_name)

    # 更新全局日志实例指向本次会话的 logger
    INFO.logger = session_logger

    INFO.logger.info("=" * 60)
    INFO.logger.info(f"测试会话开始 | 日志文件: autoapi_{timestamp}.log")
    INFO.logger.info("=" * 60)


def pytest_sessionfinish(session, exitstatus):
    """
    测试会话结束钩子

    在整个测试会话结束后执行。
    """
    INFO.logger.info("=" * 60)
    INFO.logger.info(f"测试会话结束 (状态码: {exitstatus})")
    INFO.logger.info("=" * 60)


def pytest_runtest_setup(item):
    """
    每个测试用例执行前钩子

    1. 切换日志文件到测试用例级别，文件名格式：{test_name}_{YYYYMMDD_HHMMSS}.log
    2. 从测试方法 docstring 第一行提取中文标题，设置为 Allure 报告标题
    """
    test_name = item.name  # 如 test_cash_payment 或 test_cash_payment[cash_payment_001]

    # 切换日志文件
    switch_test_logger(INFO.logger)
    INFO.logger.info(f"--- 开始测试: {test_name} ---")

    # 设置 Allure 标题（从 docstring 第一行提取）
    if HAS_ALLURE:
        # 模块名作为 parent_suite（如 "支付测试"、"灯控测试"）
        module_dir = Path(item.fspath).parent.name  # payment / lighting / ...
        _MODULE_LABELS = {
            "payment": "支付测试",
            "lighting": "灯控测试",
        }
        allure.dynamic.parent_suite(_MODULE_LABELS.get(module_dir, module_dir))

        # 类名作为 suite
        cls = getattr(item, "cls", None)
        if cls:
            allure.dynamic.suite(cls.__name__)

        # docstring 第一行作为用例标题
        doc = item.function.__doc__
        if doc:
            title = doc.strip().split('\n')[0].strip()
            allure.dynamic.title(title)
