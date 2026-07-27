# -*- coding: utf-8 -*-
"""
小程序测试
==========
测试小程序端开台 → 关台流程

注意：小程序接口使用 /app-api/ 前缀和 xcx_token

自动化改造：
- 自动创建区域/台费/桌台（fixture teardown 自动清理）
- 不再依赖 config.yaml 中的预配桌台数据
"""

import pytest

from core.assertions import assert_response
from utils.config import config
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority


class TestMiniprogram:
    """小程序测试"""

    @pytest.mark.regression
    @pytest.mark.lighting
    @mark_priority(1)
    @capture_failure
    def test_miniprogram_flow(self, api_client, auth_context, lighting_resources):
        """
        小程序开台 → 小程序关台

        测试步骤：
        1. 自动创建区域/台费/桌台（fixture）
        2. 小程序端计时开台（使用 app_host + xcx_token）
        3. 小程序端关台
        4. 自动清理资源（fixture teardown）

        验证点：
        - 开台响应 code == 200
        - 关台响应 code == 200
        """
        xcx_token = config.business_data.get('xcx_token', '')
        store_no = auth_context.store_no
        desk_no = lighting_resources['desk_no']
        golfer_no = config.business_data.get('golferNo', '')

        if not xcx_token:
            info("      小程序Token未配置，跳过测试")
            pytest.skip("小程序Token未配置")

        # 1. 小程序端开台
        info("小程序开台...")
        response = api_client.post(
            "/app-api/store/desk/orders/createClockOpenV3",
            {"deskNo": desk_no, "filter": {"storeNo": store_no}},
            token=xcx_token, step_name="小程序开台"
        )
        assert_response(response).code_is(200).data_is_not_null().validate()
        order_data = response.get_data()
        order_no = order_data.get("orderNo") if isinstance(order_data, dict) else order_data
        info(f"      小程序开台成功! orderNo={order_no}")

        # 2. 小程序端关台
        info("小程序关台...")
        response = api_client.post(
            "/app-api/store/desk/orders/closeDesk",
            {
                "orderNo": order_no,
                "close": True,
                "is_check": False,
                "golferNoList": [golfer_no]
            },
            token=xcx_token, step_name="小程序关台"
        )
        assert_response(response).code_is(200).validate()
        info("小程序流程测试通过")
