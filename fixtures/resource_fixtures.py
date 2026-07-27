# -*- coding: utf-8 -*-
"""
资源管理 Fixtures
=================
提供测试资源的前置创建和后置清理。

架构分层：
    conftest.py           → pytest hooks + fixture 注册（本文件被 import）
    fixtures/
      auth_fixtures.py    → session 级：登录 / token（全局前置，整个会话只执行一次）
      resource_fixtures.py→ function 级：每个测试的前置创建 + 后置清理（本文件）
    utils/
      test_helpers.py     → 业务逻辑：create_xxx / verify_xxx / cleanup_xxx

Fixtures：
    lighting_resources    → 单桌台场景（计时、灯控、暂停、恢复等）
    lighting_resources_2  → 双桌台场景（转台、并台）

所有 fixture 均为 function 级，每个测试独立创建 → 独立清理，互不干扰。
清理顺序：desk → fee → region（逆序 teardown，依赖 pytest 自动管理）。
"""

import pytest

from utils.test_helpers import (
    create_test_resources,
    create_test_resources_2,
    cleanup_test_resources,
)


# ================================================================
#  单桌台资源（8 个灯控测试使用）
# ================================================================

@pytest.fixture(scope="function")
def lighting_resources(api_client, auth_context):
    """
    单桌台测试资源（function 级）

    前置：自动创建 region → fee → desk
    后置：自动清理 desk → fee → region

    Returns:
        Dict: {region_id, region_no, region_name,
               fee_id, fee_no, fee_name,
               desk_id, desk_no, desk_name}

    使用示例：
        def test_clock_calorie(api_client, auth_context, lighting_resources):
            desk_no = lighting_resources['desk_no']
            api_client.post("/orders/createClockOpen", {"deskNo": desk_no, ...})
    """
    from utils.debug_utils import info

    token = auth_context.token

    # ── 前置：创建资源 ──
    info("  [灯光资源] 开始创建区域→台费→桌台...")
    resources = create_test_resources(api_client, token)
    info(f"  [灯光资源] 创建完成: desk_no={resources['desk_no']}")

    yield resources

    # ── 后置：清理资源 ──
    info("  [灯光资源] 开始清理资源...")
    cleanup_test_resources(api_client, token, resources)
    info("  [灯光资源] 清理完成")


# ================================================================
#  双桌台资源（转台、并台测试使用）
# ================================================================

@pytest.fixture(scope="function")
def lighting_resources_2(api_client, auth_context):
    """
    双桌台测试资源（function 级）

    前置：自动创建 region → fee → desk1 + desk2（两个桌台绑定同一个台费）
    后置：自动清理 desk1 + desk2 → fee → region

    Returns:
        Dict: {region_id, region_no, region_name,
               fee_id, fee_no, fee_name,
               desk1_id, desk1_no, desk1_name,
               desk2_id, desk2_no, desk2_name}

    使用示例：
        def test_combine(api_client, auth_context, lighting_resources_2):
            desk_no_1 = lighting_resources_2['desk1_no']
            desk_no_2 = lighting_resources_2['desk2_no']
    """
    from utils.debug_utils import info

    token = auth_context.token

    # ── 前置：创建资源 ──
    info("  [灯光资源] 开始创建区域→台费→双桌台...")
    resources = create_test_resources_2(api_client, token)
    info(f"  [灯光资源] 创建完成: desk1={resources['desk1_no']}, desk2={resources['desk2_no']}")

    yield resources

    # ── 后置：清理资源 ──
    info("  [灯光资源] 开始清理资源...")
    cleanup_test_resources(api_client, token, resources)
    info("  [灯光资源] 清理完成")
