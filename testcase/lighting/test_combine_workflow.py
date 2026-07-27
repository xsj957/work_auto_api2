# -*- coding: utf-8 -*-
"""
并台流程测试
============
测试桌台1开台 + 桌台2开台 → 并台 → 桌台2关台

自动化改造：
- 自动创建区域/台费/两个桌台（fixture teardown 自动清理）
- 不再依赖 config.yaml 中的预配桌台数据
"""

import pytest

from core.assertions import assert_response
from utils.config import config
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority


class TestCombineWorkflow:
    """并台流程测试"""

    @pytest.mark.regression
    @pytest.mark.lighting
    @mark_priority(1)
    @capture_failure
    def test_combine_workflow(self, api_client, auth_context, lighting_resources_2):
        """
        桌台1开台 + 桌台2开台 → 并台 → 桌台2关台

        测试步骤：
        1. 自动创建区域/台费/桌台1+桌台2（fixture）
        2. 桌台1开台
        3. 桌台2开台
        4. 并台（桌台2 → 桌台1）
        5. 桌台2关台
        6. 自动清理资源（fixture teardown）

        验证点：
        - 开台响应 code == 200
        - 并台响应 code == 200
        - 关台响应 code == 200
        """
        token = auth_context.token
        store_no = auth_context.store_no
        desk_no_1 = lighting_resources_2['desk1_no']
        desk_no_2 = lighting_resources_2['desk2_no']

        # 1. 桌台1开台
        info("并台1开台...")
        response = api_client.post(
            "/merchant-api/store/desk/orders/createClockOpen",
            {"deskNo": desk_no_1, "filter": {"storeNo": store_no}},
            token, "并台1开台"
        )
        assert_response(response).code_is(200).data_is_not_null().validate()
        order_no_1 = response.get_data()
        info(f"      开台成功! orderNo={order_no_1}")

        # 2. 桌台2开台
        info("并台2开台...")
        response = api_client.post(
            "/merchant-api/store/desk/orders/createClockOpen",
            {"deskNo": desk_no_2, "filter": {"storeNo": store_no}},
            token, "并台2开台"
        )
        assert_response(response).code_is(200).data_is_not_null().validate()
        order_no_2 = response.get_data()
        info(f"      开台成功! orderNo={order_no_2}")

        # 3. 并台（桌台2 → 桌台1）
        info(f"并台: {desk_no_2} → {desk_no_1}...")
        response = api_client.post(
            "/merchant-api/store/desk/orders/updateByCombine",
            {
                "changeDeskNo": desk_no_1,
                "orderNo": order_no_2,
                # "deskIds": [],
                # "productIds": [],
                # "serveIds": [],
                # "golferNos": [],
                "storeNo": store_no
            },
            token, "并台"
        )
        assert_response(response).code_is(200).validate()
        info("      并台成功!")

        # 4. 桌台2关台
        info("并台2关台...")
        response = api_client.post(
            "/merchant-api/store/desk/orders/closeDesk",
            {
                "orderNo": order_no_1,
                "close": True,
                "userNo": config.business_data.get("userNo", ""),
                "storeNo": store_no
            },
            token, "并台2关台"
        )
        assert_response(response).code_is(200).validate()
        info("并台流程测试通过")
