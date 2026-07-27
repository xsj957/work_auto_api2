# -*- coding: utf-8 -*-
"""
资源管理 Fixtures
=================
提供测试资源的自动创建和清理功能。

Fixtures:
1. test_region - 测试区域（自动创建和清理）
2. test_fee - 测试台费（自动创建和清理）
3. test_desk - 测试桌台（自动创建和清理，依赖 test_region + test_fee）
4. test_resources - 资源管理器（统一管理多个资源）

所有创建/清理逻辑统一从 utils.test_helpers 导入，不重复写。
"""

import pytest
from typing import Dict, Any

from utils.test_helpers import (
    create_region, verify_region, cleanup_region,
    create_fee, verify_fee, cleanup_fee,
    create_desk, verify_desk, verify_desk_idle, cleanup_desk,
    _gen_suffix, REGION_NAME_PREFIX, FEE_NAME_PREFIX, DESK_NAME_PREFIX,
)


# ================================================================
#  区域 Fixtures
# ================================================================

@pytest.fixture(scope="function")
def test_region(api_client, auth_context):
    """
    测试区域（函数级）
    自动创建区域，测试结束后自动清理。
    Returns: Dict: 包含 region_id, region_no, region_name
    """
    suffix = _gen_suffix()
    region_name = f"{REGION_NAME_PREFIX}_{suffix}"

    region_id = create_region(api_client, auth_context.token, name=region_name)
    region_no = verify_region(api_client, auth_context.token, name=region_name)

    resource = {
        "region_id": region_id,
        "region_no": region_no,
        "region_name": region_name,
    }

    yield resource

    # 清理资源
    cleanup_region(api_client, auth_context.token, region_id)


# ================================================================
#  台费 Fixtures
# ================================================================

@pytest.fixture(scope="function")
def test_fee(api_client, auth_context):
    """
    测试台费（函数级）
    自动创建台费，测试结束后自动清理。
    Returns: Dict: 包含 fee_id, fee_no, fee_name
    """
    suffix = _gen_suffix()
    fee_name = f"{FEE_NAME_PREFIX}_{suffix}"

    fee_id = create_fee(api_client, auth_context.token, name=fee_name)
    fee_no, _ = verify_fee(api_client, auth_context.token, name=fee_name)

    resource = {
        "fee_id": fee_id,
        "fee_no": fee_no,
        "fee_name": fee_name,
    }

    yield resource

    # 清理资源
    cleanup_fee(api_client, auth_context.token, fee_id)


# ================================================================
#  桌台 Fixtures
# ================================================================

@pytest.fixture(scope="function")
def test_desk(api_client, auth_context, test_region, test_fee):
    """
    测试桌台（函数级）
    自动创建桌台，测试结束后自动清理。
    依赖 test_region 和 test_fee fixtures。
    Returns: Dict: 包含 desk_id, desk_no, desk_name
    """
    suffix = _gen_suffix()
    desk_name = f"{DESK_NAME_PREFIX}_{suffix}_1"

    desk_id = create_desk(
        api_client, auth_context.token,
        region_no=test_region['region_no'],
        fee_no=test_fee['fee_no'],
        fee_name=test_fee['fee_name'],
        desk_name=desk_name,
    )
    desk_no, _ = verify_desk(api_client, auth_context.token, name=desk_name)

    resource = {
        "desk_id": desk_id,
        "desk_no": desk_no,
        "desk_name": desk_name,
    }

    yield resource

    # 清理资源
    cleanup_desk(api_client, auth_context.token, desk_id)


# ================================================================
#  资源管理器 Fixture
# ================================================================

@pytest.fixture(scope="function")
def test_resources(api_client, auth_context):
    """
    资源管理器（函数级）
    提供统一的资源创建和清理接口。
    支持属性调用：test_resources.create_region()

    使用示例：
        def test_something(test_resources):
            region = test_resources.create_region()
            fee = test_resources.create_fee()
            desk = test_resources.create_desk(region['region_no'], fee['fee_no'])
    """

    class _ResourceManager:
        def __init__(self):
            self.api_client = api_client
            self.auth_context = auth_context
            self.created = []

        def create_region(self) -> Dict[str, Any]:
            """创建区域"""
            suffix = _gen_suffix()
            region_name = f"{REGION_NAME_PREFIX}_{suffix}"
            region_id = create_region(api_client, auth_context.token, name=region_name)
            region_no = verify_region(api_client, auth_context.token, name=region_name)
            resource = {"region_id": region_id, "region_no": region_no, "region_name": region_name}
            self.created.append(("region", resource))
            return resource

        def create_fee(self) -> Dict[str, Any]:
            """创建台费"""
            suffix = _gen_suffix()
            fee_name = f"{FEE_NAME_PREFIX}_{suffix}"
            fee_id = create_fee(api_client, auth_context.token, name=fee_name)
            fee_no, _ = verify_fee(api_client, auth_context.token, name=fee_name)
            resource = {"fee_id": fee_id, "fee_no": fee_no, "fee_name": fee_name}
            self.created.append(("fee", resource))
            return resource

        def create_desk(self, region_no: str, fee_no: str, fee_name: str = "") -> Dict[str, Any]:
            """创建桌台"""
            suffix = _gen_suffix()
            desk_name = f"{DESK_NAME_PREFIX}_{suffix}_1"
            desk_id = create_desk(
                api_client, auth_context.token,
                region_no=region_no, fee_no=fee_no,
                fee_name=fee_name, desk_name=desk_name,
            )
            desk_no, _ = verify_desk(api_client, auth_context.token, name=desk_name)
            resource = {"desk_id": desk_id, "desk_no": desk_no, "desk_name": desk_name}
            self.created.append(("desk", resource))
            return resource

    manager = _ResourceManager()
    yield manager

    # 逆序清理所有资源
    for resource_type, resource in reversed(manager.created):
        try:
            if resource_type == "desk":
                cleanup_desk(api_client, auth_context.token, resource["desk_id"])
            elif resource_type == "fee":
                cleanup_fee(api_client, auth_context.token, resource["fee_id"])
            elif resource_type == "region":
                cleanup_region(api_client, auth_context.token, resource["region_id"])
        except Exception as e:
            from utils.log_control import WARNING
            WARNING.logger.warning(f"清理 {resource_type} 失败: {e}")
