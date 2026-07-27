# -*- coding: utf-8 -*-
"""
测试标记工具
============
提供测试标记分类和运行控制功能。

使用示例：
    # 在测试中使用标记
    @pytest.mark.smoke
    def test_login(self):
        ...

    @pytest.mark.regression
    @pytest.mark.slow
    def test_full_flow(self):
        ...

    # 运行特定标记的测试
    pytest -m smoke tests/
    pytest -m "smoke and not slow" tests/
"""

import pytest


# ================================================================
#  自定义标记定义
# ================================================================

def register_markers(config):
    """
    注册自定义标记

    在 conftest.py 的 pytest_configure 中调用：
        from utils.markers import register_markers
        register_markers(config)
    """
    # 测试类型标记
    config.addinivalue_line(
        "markers",
        "smoke: 冒烟测试 - 核心功能快速验证，每次提交都运行"
    )
    config.addinivalue_line(
        "markers",
        "regression: 回归测试 - 完整功能验证，每日构建运行"
    )
    config.addinivalue_line(
        "markers",
        "nightly: 夜间测试 - 耗时较长的测试，每晚运行"
    )
    config.addinivalue_line(
        "markers",
        "weekly: 周测试 - 非常耗时的测试，每周运行"
    )

    # 测试特性标记
    config.addinivalue_line(
        "markers",
        "slow: 慢速测试 - 执行时间较长，需要手动触发或排除"
    )
    config.addinivalue_line(
        "markers",
        "flaky: 不稳定测试 - 已知不稳定，需要修复"
    )
    config.addinivalue_line(
        "markers",
        "skip: 跳过测试 - 暂时跳过的测试"
    )

    # 业务模块标记
    config.addinivalue_line(
        "markers",
        "payment: 支付模块测试"
    )
    config.addinivalue_line(
        "markers",
        "lighting: 灯控模块测试"
    )
    config.addinivalue_line(
        "markers",
        "desk: 桌台模块测试"
    )
    config.addinivalue_line(
        "markers",
        "user: 用户模块测试"
    )
    config.addinivalue_line(
        "markers",
        "order: 订单模块测试"
    )

    # 测试优先级标记
    config.addinivalue_line(
        "markers",
        "priority(level): 测试优先级 - P0(最高), P1, P2, P3(最低)"
    )

    # 环境标记
    config.addinivalue_line(
        "markers",
        "env(name): 指定测试运行的环境 - dev, uat, staging, prod"
    )


# ================================================================
#  标记辅助函数
# ================================================================

def mark_priority(level: int):
    """
    标记测试优先级

    Args:
        level: 优先级级别 (0-3)
            0: P0 - 最高优先级，核心功能
            1: P1 - 高优先级，重要功能
            2: P2 - 中优先级，一般功能
            3: P3 - 低优先级，边缘功能

    Returns:
        pytest.mark: 优先级标记

    使用示例：
        @mark_priority(0)
        def test_critical_feature(self):
            ...
    """
    if not 0 <= level <= 3:
        raise ValueError(f"优先级必须在 0-3 之间，当前值: {level}")
    return pytest.mark.priority(level)


def mark_env(env_name: str):
    """
    标记测试运行的环境

    Args:
        env_name: 环境名称 (dev/uat/staging/prod)

    Returns:
        pytest.mark: 环境标记

    使用示例：
        @mark_env("uat")
        def test_uat_only(self):
            ...
    """
    valid_envs = ["dev", "uat", "staging", "prod"]
    if env_name not in valid_envs:
        raise ValueError(f"环境必须是 {valid_envs} 之一，当前值: {env_name}")
    return pytest.mark.env(env_name)


# ================================================================
#  标记过滤函数
# ================================================================

def should_run_test(item, current_env: str = None) -> bool:
    """
    判断测试是否应该运行

    Args:
        item: pytest 测试项
        current_env: 当前环境

    Returns:
        bool: 是否应该运行
    """
    # 检查环境标记
    env_marker = item.get_closest_marker("env")
    if env_marker and current_env:
        required_env = env_marker.args[0] if env_marker.args else None
        if required_env and required_env != current_env:
            return False

    # 检查是否标记为跳过
    if item.get_closest_marker("skip"):
        return False

    return True


# ================================================================
#  Pytest 钩子
# ================================================================

def pytest_collection_modifyitems(config, items):
    """
    修改测试集合

    在 conftest.py 中调用此函数来过滤测试
    """
    from utils.env_manager import env_manager

    current_env = env_manager.get_env()

    # 过滤不符合当前环境的测试
    selected_items = []
    deselected_items = []

    for item in items:
        if should_run_test(item, current_env):
            selected_items.append(item)
        else:
            deselected_items.append(item)

    # 更新测试集合
    items[:] = selected_items

    # 报告被跳过的测试
    if deselected_items:
        config.hook.pytest_deselected(items=deselected_items)
