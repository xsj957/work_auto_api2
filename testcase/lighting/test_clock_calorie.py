# -*- coding: utf-8 -*-
"""
计时+卡钟测试
============
测试计时开台 → 手动卡钟 → 计时关台流程

自动化改造：
- 自动创建区域/台费/桌台（fixture teardown 自动清理）
- 不再依赖 config.yaml 中的预配桌台数据
"""

import time

import pytest

from core.assertions import assert_response
from utils.config import config
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority


@pytest.mark.smoke
@pytest.mark.lighting
@mark_priority(0)
@capture_failure
def test_clock_calorie_flow(api_client, auth_context, lighting_resources):
    """
    计时开台 → 手动卡钟 → 计时关台

    测试步骤：
    1. 自动创建区域/台费/桌台（fixture）
    2. 计时开台
    3. 手动卡钟
    4. 计时关台
    5. 自动清理资源（fixture teardown）

    验证点：
    - 开台响应 code == 200
    - 卡钟响应 code == 200, msg 包含"成功"
    - 关台响应 code == 200, msg 包含"成功"
    """
    token = auth_context.token
    store_no = auth_context.store_no
    desk_no = lighting_resources['desk_no']

    # 1. 计时开台
    info("计时开台...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/createClockOpen",
        {"deskNo": desk_no, "filter": {"storeNo": store_no}},
        token, "计时开台"
    )
    assert_response(response).code_is(200).data_is_not_null().validate()
    order_no = response.get_data()
    info(f"      开台成功! orderNo={order_no}")

    # 等待服务端处理开台的 fee 记录，避免卡钟时唯一键冲突
    time.sleep(3)

    # 2. 手动卡钟
    info("手动卡钟...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/calorieClock",
        {"orderNo": order_no, "filter": {"storeNo": store_no}},
        token, "手动卡钟"
    )
    assert_response(response).code_is(200).msg_contains("成功").validate()

    # 3. 计时关台
    info("计时关台...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/closeDesk",
        {
            "orderNo": order_no,
            "close": True,
            "userNo": config.business_data.get("userNo", ""),
            "filter": {"storeNo": store_no}
        },
        token, "计时关台"
    )
    assert_response(response).code_is(200).msg_contains("成功").validate()
    info("计时+卡钟流程测试通过")
