# -*- coding: utf-8 -*-
"""
支付流程测试
============
测试完整支付流程：创建资源 → 开台 → 计费 → 结账 → 支付 → 验证

业务流程:
  登录 → 新增区域 → 查询校验区域 → 新增台费 → 查询校验台费
  → 新增桌台 → 查询校验桌台 → listV3校验桌台空闲
  → 计时开台 → 订单详情(detail) → 查询支付(needPay) → 结账(closeDesk)
  → 计算金额(pay) → 创建支付单 → 提交支付
  → 支付后校验(pay) → 关闭支付会话(cancelPay) → 最终详情校验(detail)
  → 清理数据(删除桌台 → 删除台费 → 删除区域)
"""

# 1. 标准库
import time

# 2. 第三方库
import pytest

# 3. 项目模块
from core.api_client import APIClient
from core.assertions import assert_response
from utils.payment_helpers import (
    PAYMENT_CHANNELS, STORE_NO,
    create_region, verify_region,
    create_fee, verify_fee,
    create_desk, verify_desk, verify_desk_idle,
    open_desk, checkout_and_calc,
    find_and_bind_member, create_payment, submit_payment,
    log_payment_info, FlowError,
)
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority


@pytest.mark.smoke
@pytest.mark.payment
@mark_priority(0)
@capture_failure
@pytest.mark.parametrize("channel_code,channel_name,member_phone", PAYMENT_CHANNELS)
def test_full_payment_flow(api_client, auth_context, channel_code, channel_name, member_phone):
    """
    完整支付流程测试:
    登录 → 区域 → 台费 → 桌台 → 开台 → detail → needPay
    → 结账 → pay → 支付 → 校验 → cancelPay → 最终detail
    """
    token = auth_context.token
    merchant_no = auth_context.merchant_no
    golfer_no = None

    info("=" * 60)
    info(f"   支付业务流程自动化测试 [支付方式: {channel_name} ({channel_code})]")
    if member_phone:
        info(f"   会员手机号: {member_phone} → 开台前需绑定会员到桌台")
    info("   流程: 登录 → 区域 → 台费 → 桌台 → 开台 → detail → needPay"
          " → 结账 → pay → 支付 → 校验 → 验证关闭")
    info("=" * 60)

    # Arrange（准备）：创建资源
    suffix = f"{int(time.time()) % 100000}"
    region_name = f"支付区_{suffix}"
    fee_name = f"支付费_{suffix}"
    desk_name = f"支付桌_{suffix}"

    # Step 1: 创建区域
    region_id = create_region(api_client, token, merchant_no, name=region_name)

    # Step 2: 校验区域
    region_no = verify_region(api_client, token, region_name)

    # Step 3: 创建台费
    fee_id = create_fee(api_client, token, merchant_no, name=fee_name)

    # Step 4: 校验台费
    fee_no, fee_id = verify_fee(api_client, token, fee_name)

    # Step 5: 创建桌台
    desk_id = create_desk(api_client, token, region_no, fee_no, fee_name, desk_name=desk_name)

    # Step 6: 校验桌台
    desk_no, desk_id = verify_desk(api_client, token, desk_name)

    # Step 7: 校验桌台空闲
    verify_desk_idle(api_client, token, desk_name)

    try:
        # Act（执行）：支付流程
        # Step 8: 绑定会员（余额支付需要）
        if member_phone:
            golfer_no = find_and_bind_member(api_client, token, desk_no, member_phone)

        # Step 9: 计时开台
        order_no = open_desk(api_client, token, desk_no)

        # Step 10: 获取订单详情
        info(f"  获取订单详情... orderNo={order_no}")
        response = api_client.post(
            "/merchant-api/store/desk/orders/detail",
            {"id": order_no, "filter": {"storeNo": STORE_NO}},
            token, "订单详情"
        )
        total_amount = response.get_data("totalAmount", default=0)

        # Step 11: 查询是否需要支付
        api_client.post(
            "/merchant-api/store/desk/needPay",
            {"merchantNo": merchant_no, "orderNo": order_no, "filter": {"storeNo": STORE_NO}},
            token, "needPay"
        )

        # Step 12-13: 结账 + 计算金额
        child_order_no, total_amount = checkout_and_calc(api_client, token, order_no, golfer_no)

        # Step 14: 创建支付单
        pay_order_id = create_payment(api_client, token, child_order_no, total_amount, golfer_no)

        # Step 15: 提交支付
        submit_payment(api_client, token, pay_order_id, child_order_no, total_amount, golfer_no, channel_code)

        # 等待支付回调处理
        info("      等待支付处理...")
        time.sleep(3)

        # Step 16: 支付后校验
        response = api_client.post(
            "/merchant-api/store/desk/orders/pay",
            {"orderNo": child_order_no, "golferNo": "", "filter": {"storeNo": STORE_NO}},
            token, "支付后校验"
        )
        pay_result_data = response.get_data(default={})
        log_payment_info(pay_result_data, prefix="  支付后校验: ")

        if pay_result_data.get("deskStatus") != "3":
            raise FlowError(f"桌台未关闭! deskStatus={pay_result_data.get('deskStatus')}")
        info(f"      ✓ 桌台已自动关闭! deskStatus=3")

        # Step 17: 关闭支付会话
        api_client.post(
            "/merchant-api/store/desk/orders/cancelPay",
            {"orderNo": child_order_no, "filter": {"storeNo": STORE_NO}},
            token, "cancelPay"
        )
        info(f"      支付会话已关闭!")

        # Step 18: 最终详情校验
        response = api_client.post(
            "/merchant-api/store/desk/orders/detail",
            {"id": order_no, "filter": {"storeNo": STORE_NO}},
            token, "最终detail"
        )
        final_data = response.get_data(default={})
        log_payment_info(final_data, prefix="  最终校验: ")

        if final_data.get("deskStatus") != "3":
            raise FlowError(f"父订单桌台状态异常! deskStatus={final_data.get('deskStatus')}")
        info(f"      ✓ 父订单桌台已关闭! deskStatus=3")

        info("=" * 60)
        info("   支付业务流程测试全部通过!")
        info("=" * 60)

    finally:
        # Assert（清理）：删除资源
        info("  清理测试资源...")
        from utils.test_helpers import cleanup_region, cleanup_fee, cleanup_desk
        cleanup_desk(api_client, token, desk_id, strict=False)
        cleanup_fee(api_client, token, fee_id, strict=False)
        cleanup_region(api_client, token, region_id, strict=False)
        info("  资源清理完成!")
