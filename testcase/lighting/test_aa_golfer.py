# -*- coding: utf-8 -*-
"""
追加会员+AA结账测试
==================
测试计时开台 → 批量追加会员 → AA结账流程

自动化改造：
- 自动创建区域/台费/桌台（fixture teardown 自动清理）
- 不再依赖 config.yaml 中的预配桌台数据
"""

import pytest

from core.assertions import assert_response
from utils.config import config
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority
from utils.test_helpers import get_golfer_no


@pytest.mark.regression
@pytest.mark.lighting
@mark_priority(1)
@capture_failure
def test_aa_golfer_workflow(api_client, auth_context, lighting_resources):
    """
    计时开台 → 批量追加会员 → AA结账

    测试步骤：
    1. 自动创建区域/台费/桌台（fixture）
    2. 计时开台
    3. 批量追加会员
    4. AA结账(pendingOrder, close=true)
    5. 自动清理资源（fixture teardown）

    验证点：
    - 开台响应 code == 200
    - 追加会员响应 code == 200
    - AA结账响应 code == 200
    """
    token = auth_context.token
    store_no = auth_context.store_no
    desk_no = lighting_resources['desk_no']

    # 查询两个会员
    golfer_phones = config.business_data.get('golferPhones', ['13538506002', '13538227451'])
    golfer_nos = []
    for phone in golfer_phones:
        golfer_no = get_golfer_no(api_client, token, phone)
        if golfer_no:
            golfer_nos.append(golfer_no)
    info(f"查询到的会员: {golfer_nos}")

    # 1. 计时开台
    info("AA前置开台...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/createClockOpen",
        {"deskNo": desk_no, "filter": {"storeNo": store_no}},
        token, "AA前置开台"
    )
    assert_response(response).code_is(200).data_is_not_null().validate()
    order_no = response.get_data()
    info(f"      开台成功! orderNo={order_no}")

    # 2. 批量追加会员
    info("批量追加会员...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/golfer/batchCreate",
        {
            "orderNo": order_no,
            "golferNoList": golfer_nos,
            "filter": {"storeNo": store_no}
        },
        token, "批量追加会员"
    )
    assert_response(response).code_is(200).validate()

    # 3. AA结账（每个会员分别结账）
    info("AA结账...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/closeDesk",
        {
            "close": True,
            "orderNo": order_no,
            "filter": {"storeNo": store_no},
            "userNo": "MU202606171016150897"
        },
        token, f"AA结账-{','.join(golfer_nos)}"
    )
    assert_response(response).code_is(200).validate()
    info("追加会员+AA结账测试通过")
