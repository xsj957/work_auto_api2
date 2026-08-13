# -*- coding: utf-8 -*-
"""
灯控测试
========
测试灯控相关功能：临时灯开关、区域灯控等

测试场景：
1. 临时灯开台（数据驱动）
2. 区域全开灯
3. 区域全关灯
4. 桌台灯控开关

自动化改造：
- 区域灯控测试自动创建区域（fixture teardown 自动清理）
- 桌台灯控测试自动创建桌台（fixture teardown 自动清理）
- 不再依赖硬编码的 region_no 和预配桌台数据

前置条件：
- 有效的登录 Token（通过 auth_context fixture 提供）
- 灯控设备配置正确

预期结果：
- 灯控指令发送成功
- 响应 code == 200
- 响应消息包含"成功"
"""

# 1. 标准库

# 2. 第三方库
import pytest

# 3. 项目模块
from core.api_client import APIClient
from core.assertions import assert_response
from core.data_loader import DataLoader
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority


# ================================================================
#  冒烟测试（核心功能快速验证）
# ================================================================

@pytest.mark.smoke
@pytest.mark.lighting
@mark_priority(0)
@capture_failure
def test_region_light_on(api_client, auth_context, lighting_resources):
    """
    区域全开灯测试

    测试步骤：
    1. 自动创建区域（fixture）
    2. 发送区域全开灯指令
    3. 验证响应结果

    验证点：
    - 响应 code == 200
    - 响应消息包含"成功"
    """
    # Arrange（准备）
    region_no = lighting_resources['region_no']
    info(f"测试参数: region_no={region_no}, lightStatus=1")

    # Act（执行）
    info("发送区域全开灯指令...")
    response = api_client.post(
        "/merchant-api/store/desk/regionSwitchLight",
        {
            "regionNo": region_no,
            "deviceSwitch": 1,  # 开灯
            "storeNo": auth_context.store_no
        },
        token=auth_context.token,
        step_name="区域全开灯"
    )

    # Assert（断言）
    assert_response(response)\
        .code_is(200)\
        .msg_contains("成功")\
        .validate()

    info("区域全开灯成功")


@pytest.mark.smoke
@pytest.mark.lighting
@mark_priority(0)
@capture_failure
def test_region_light_off(api_client, auth_context, lighting_resources):
    """
    区域全关灯测试

    测试步骤：
    1. 自动创建区域（fixture）
    2. 发送区域全关灯指令
    3. 验证响应结果

    验证点：
    - 响应 code == 200
    - 响应消息包含"成功"
    """
    # Arrange（准备）
    region_no = lighting_resources['region_no']
    info(f"测试参数: region_no={region_no}, lightStatus=0")

    # Act（执行）
    info("发送区域全关灯指令...")
    response = api_client.post(
        "/merchant-api/store/desk/regionSwitchLight",
        {
            "regionNo": region_no,
            "deviceSwitch": 0,  # 关灯
            "storeNo": auth_context.store_no
        },
        token=auth_context.token,
        step_name="区域全关灯"
    )

    # Assert（断言）
    assert_response(response)\
        .code_is(200)\
        .msg_contains("成功")\
        .validate()

    info("区域全关灯成功")


# ================================================================
#  数据驱动测试
# ================================================================

@pytest.mark.regression
@pytest.mark.lighting
@mark_priority(1)
@capture_failure
@DataLoader.parametrize("data/lighting/test_temp_light.yaml")
def test_temp_light(api_client, auth_context, lighting_resources, test_case):
    """
    临时灯开关测试（数据驱动）

    测试临时灯的开启和关闭功能，支持多个测试场景。

    测试步骤：
    1. 自动创建桌台（fixture）
    2. 从 YAML 加载测试数据
    3. 发送临时灯请求（使用 fixture 的 desk_no）
    4. 验证响应结果

    验证点：
    - 响应 code == 预期 code
    - 响应消息包含"成功"

    Args:
        api_client: API 客户端
        auth_context: 认证上下文
        lighting_resources: 灯光测试资源（fixture）
        test_case: 测试用例数据（来自 YAML）
    """
    # Arrange（准备）
    device_id = test_case["device_id"]
    desk_no = lighting_resources['desk_no']  # 使用 fixture 创建的桌台
    lsid = test_case["lsid"]
    expected_code = test_case["expected_code"]

    info(f"测试参数: device_id={device_id}, desk_no={desk_no}, expected_code={expected_code}")

    # Act（执行）
    info("发送临时灯请求...")
    response = api_client.post(
        "/merchant-api/store/device/tempOpenLight",
        {
            "id": device_id,
            "deskNo": desk_no,
            "lsid": lsid,
            "storeNo": auth_context.store_no
        },
        token=auth_context.token,
        step_name="临时灯开台"
    )

    response2 = api_client.post(
        "/merchant-api/store/device/tempCloseLight",
        {
            "id": device_id,
            "deskNo": desk_no,
            "lsid": lsid,
            "storeNo": auth_context.store_no
        },
        token=auth_context.token,
        step_name="临时灯关台"
    )
    # Assert（断言）
    assert_response(response)\
        .code_is(expected_code)\
        .msg_contains("成功")\
        .validate()

    assert_response(response2)\
        .code_is(200)\
        .msg_contains("成功")\
        .validate()

    info("临时灯测试通过")
