# -*- coding: utf-8 -*-
"""
挂单流程测试
============
测试计时开台 → 挂单流程

自动化改造：
- 自动创建区域/台费/桌台（fixture teardown 自动清理）
- 不再依赖 config.yaml 中的预配桌台数据
"""

import pytest

from core.assertions import assert_response
from utils.config import config
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority


@pytest.mark.regression
@pytest.mark.lighting
@mark_priority(1)
@capture_failure
def test_pending_workflow(api_client, auth_context, lighting_resources):
    """
    计时开台 → 挂单

    测试步骤：
    1. 自动创建区域/台费/桌台（fixture）
    2. 计时开台
    3. 挂单
    4. 自动清理资源（fixture teardown）

    验证点：
    - 开台响应 code == 200
    - 挂单响应 code == 200
    """
    token = auth_context.token
    store_no = auth_context.store_no
    desk_no = lighting_resources['desk_no']
    golfer_no = config.business_data.get('golferNo', '')

    # 1. 计时开台
    info("挂单前置开台...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/createClockOpen",
        {"deskNo": desk_no, "filter": {"storeNo": store_no}},
        token, "挂单前置开台"
    )
    assert_response(response).code_is(200).data_is_not_null().validate()
    order_no = response.get_data()
    info(f"      开台成功! orderNo={order_no}")

    # 2. 挂单
    info("执行挂单...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/pendingOrder",
        {
            "close": True,
            "orderNo": order_no,
            "golferNo": golfer_no,
            "remark": "123",
            "filter": {"storeNo": store_no}
        },
        token, "挂单"
    )
    assert_response(response).code_is(200).validate()
    info("挂单流程测试通过")
