# -*- coding: utf-8 -*-
"""
转台流程测试
============
测试桌台1开台 → 转台到桌台2 → 桌台2关台

自动化改造：
- 自动创建区域/台费/两个桌台（fixture teardown 自动清理）
- 不再依赖 config.yaml 中的预配桌台数据
"""

import pytest

from core.assertions import assert_response
from utils.config import config
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority


class TestTurnWorkflow:
    """转台流程测试"""

    @pytest.mark.regression
    @pytest.mark.lighting
    @mark_priority(1)
    @capture_failure
    def test_turn_workflow(self, api_client, auth_context, lighting_resources_2):
        """
        桌台1开台 → 转台到桌台2 → 桌台2关台

        测试步骤：
        1. 自动创建区域/台费/桌台1+桌台2（fixture）
        2. 桌台1计时开台
        3. 转台（桌台1 → 桌台2）
        4. 桌台2关台
        5. 自动清理资源（fixture teardown）

        验证点：
        - 开台响应 code == 200
        - 转台响应 code == 200
        - 关台响应 code == 200
        """
        token = auth_context.token
        store_no = auth_context.store_no
        desk_no_1 = lighting_resources_2['desk1_no']
        desk_no_2 = lighting_resources_2['desk2_no']

        # 1. 桌台1开台
        info("转台1开台...")
        response = api_client.post(
            "/merchant-api/store/desk/orders/createClockOpen",
            {"deskNo": desk_no_1, "storeNo": store_no},
            token, "转台1开台"
        )
        assert_response(response).code_is(200).data_is_not_null().validate()
        order_no_1 = response.get_data()

        # 2. 转台（桌台1 → 桌台2）
        info(f"转台: {desk_no_1} → {desk_no_2}...")
        response = api_client.post(
            "/merchant-api/store/desk/orders/updateByTurn",
            {
                "changeDeskNo": desk_no_2,
                "orderNo": order_no_1,
                # "deskIds": [],
                # "productIds": [],
                # "serveIds": [],
                # "golferNos": [],
                "storeNo": store_no
            },
            token, "转台"
        )
        assert_response(response).code_is(200).validate()
        # 转台后获取新订单号
        turn_data = response.get_data()
        # 转台接口可能返回：字符串（新订单号）或 dict（包含 orderNo）
        if isinstance(turn_data, str) and turn_data:
            order_no_2 = turn_data
        elif isinstance(turn_data, dict):
            order_no_2 = turn_data.get("orderNo", order_no_1)
        else:
            order_no_2 = order_no_1
        info(f"      转台成功! 新orderNo={order_no_2}")

        # 3. 桌台2关台
        info("转台2关台...")
        response = api_client.post(
            "/merchant-api/store/desk/orders/closeDesk",
            {
                "orderNo": order_no_2,
                "close": True,
                "userNo": config.business_data.get("userNo", ""),
                "storeNo": store_no
            },
            token, "转台2关台"
        )
        assert_response(response).code_is(200).validate()
        info("转台流程测试通过")
