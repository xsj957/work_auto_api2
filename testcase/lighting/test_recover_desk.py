# -*- coding: utf-8 -*-
"""
恢复关台测试
============
测试计时开台 → 等待 → 关台流程

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


@pytest.mark.regression
@pytest.mark.lighting
@mark_priority(1)
@capture_failure
def test_recover_desk(api_client, auth_context, lighting_resources):
    """
    计时开台 → 等待5秒 → 关台

    测试步骤：
    1. 自动创建区域/台费/桌台（fixture）
    2. 计时开台
    3. 等待5秒
    4. 关台
    5. 自动清理资源（fixture teardown）

    验证点：
    - 开台响应 code == 200
    - 关台响应 code == 200
    """
    token = auth_context.token
    store_no = auth_context.store_no
    desk_no = lighting_resources['desk_no']

    # 1. 计时开台
    info("恢复关台前置开台...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/createClockOpen",
        {"deskNo": desk_no, "filter": {"storeNo": store_no}},
        token, "恢复关台前置开台"
    )
    assert_response(response).code_is(200).data_is_not_null().validate()
    order_no = response.get_data()
    info(f"      开台成功! orderNo={order_no}")

    # 2. 等待5秒
    info("等待5秒...")
    time.sleep(5)

    # 3. 关台
    info("恢复关台...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/closeDesk",
        {
            "orderNo": order_no,
            "close": True,
            "userNo": config.business_data.get("userNo", ""),
            "filter": {"storeNo": store_no}
        },
        token, "恢复关台"
    )
    assert_response(response).code_is(200).validate()
    info("恢复关台测试通过")
