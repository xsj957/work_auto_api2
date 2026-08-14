# -*- coding: utf-8 -*-
"""
小程序支付流程测试
=================
Web 端建资源 + 开台绑定会员 → 小程序端完成支付

关键区别（vs test_payment_flow.py）：
- 关台 / 计算金额 / 创建支付单 / 提交支付 → 使用 app-api 前缀 + xcx_token
- xcx_token 从小程序抓包获取，写入 config.yaml，长期有效
- 其他接口路径和参数与 Web 端完全一致

业务流程:
  Web:   创建资源(region/fee/desk) → 查询绑定会员 → 计时开台(等待65s)
  小程序: closeDesk → pay(计算金额) → payment/create → pay/order/submit
       → 支付后校验 → cancelPay → 最终detail
  Web:   清理资源
"""

# 1. 标准库
import time

# 2. 第三方库
import pytest

# 3. 项目模块
from core.api_client import APIClient
from core.assertions import assert_response
from utils.config import config
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


@pytest.mark.regression
@pytest.mark.payment
@mark_priority(0)
@capture_failure
@pytest.mark.parametrize("channel_code,channel_name,member_phone", PAYMENT_CHANNELS)
def test_miniprogram_payment_flow(api_client, auth_context, channel_code, channel_name, member_phone):
    """
    小程序支付流程:
    Web建资源 → 开台绑定会员 → 小程序端关台/计算金额/创建支付单/提交支付 → 校验
    """
    token = auth_context.token
    merchant_no = auth_context.merchant_no
    xcx_token = config.business_data.get("xcx_token", "")
    golfer_phones = config.business_data.get("golferPhones", [])

    if not xcx_token:
        info("      小程序Token未配置，跳过测试")
        pytest.skip("小程序Token未配置")

    golfer_no = None

    info("=" * 60)
    info(f"   小程序支付流程测试 [支付方式: {channel_name} ({channel_code})]")
    if member_phone:
        info(f"   会员手机号: {member_phone}")
    info("   流程: Web建资源 → 开台绑定会员 → 小程序端完成支付")
    info("=" * 60)

    # Arrange（准备）：Web 端创建资源
    suffix = f"{int(time.time()) % 100000}"
    region_name = f"小程序支付区_{suffix}"
    fee_name = f"小程序支付费_{suffix}"
    desk_name = f"小程序支付桌_{suffix}"

    # Step 1-2: 创建区域
    region_id = create_region(api_client, token, merchant_no, name=region_name)
    region_no = verify_region(api_client, token, region_name)

    # Step 3-4: 创建台费
    fee_id = create_fee(api_client, token, merchant_no, name=fee_name)
    fee_no, _ = verify_fee(api_client, token, fee_name)

    # Step 5-7: 创建桌台
    desk_id = create_desk(api_client, token, region_no, fee_no, fee_name, desk_name=desk_name)
    desk_no, _ = verify_desk(api_client, token, desk_name)
    verify_desk_idle(api_client, token, desk_name)

    try:
        # ─ Web 端：绑定会员 + 开台 ──

        # Step 8: 绑定会员（小程序端操作必须有会员身份）
        # 余额支付使用 member_phone，现金/线下支付使用第一个 golferPhone
        bind_phone = member_phone or (golfer_phones[0] if golfer_phones else None)
        if bind_phone:
            golfer_no = find_and_bind_member(api_client, token, desk_no, bind_phone)
        else:
            info("      ⚠️ 无可用会员手机号，小程序端操作可能失败")

        # Step 9-10: 计时开台 + 等待计费
        order_no = open_desk(api_client, token, desk_no)

        info(f"  ✅ Web 端资源创建和开台完成，切换到小程序端...")
        info(f"     deskNo={desk_no}, orderNo={order_no}")

        # ── 小程序端：关台 + 支付 ──
        info(f"  使用 app-api 前缀 + xcx_token 执行后续操作")

        # Step 11: 查询是否需要支付（Web端调用）
        api_client.post(
            "/merchant-api/store/desk/needPay",
            {"merchantNo": merchant_no, "orderNo": order_no, "filter": {"storeNo": STORE_NO}},
            token, "needPay(Web)"
        )

        # Step 12: 小程序端关台
        info(f"  [小程序] 关台... orderNo={order_no}")
        response = api_client.post(
            "/app-api/store/desk/orders/closeDesk",
            {
                "orderNo": order_no,
                "close": False,
                "is_check": False,
                "golferNoList": [golfer_no] if golfer_no else [],
                "filter": {"storeNo": STORE_NO},
            },
            token=xcx_token, step_name="小程序关台"
        )
        data = response.get_data()
        child_order_no = data.get("orderNo", data) if isinstance(data, dict) else data
        if not child_order_no:
            child_order_no = order_no
        info(f"      小程序关台成功! 子订单号={child_order_no}")

        # Step 13: 小程序端计算金额
        info(f"  [小程序] 计算金额... orderNo={child_order_no}")
        api_client.post(
            "/app-api/store/desk/orders/pay",
            {"orderNo": child_order_no, "golferNo": golfer_no or ""},
            token=xcx_token, step_name="小程序计算金额"
        )

        # Step 14: 获取真实金额（Web端 detail）
        response = api_client.post(
            "/merchant-api/store/desk/orders/detail",
            {"id": child_order_no, "filter": {"storeNo": STORE_NO}},
            token, "获取金额"
        )
        total_amount = response.get_data("totalAmount", default=0)
        info(f"      应付金额={total_amount}元")

        # Step 15: 小程序端创建支付单
        pay_order_id = create_payment(api_client, token, child_order_no, total_amount, golfer_no)

        # Step 16: 小程序端提交支付
        submit_payment(api_client, token, pay_order_id, child_order_no, total_amount, golfer_no, channel_code)

        # 等待支付回调处理
        info("      等待支付处理...")
        time.sleep(3)

        # Step 17: 支付后校验（小程序端）
        response = api_client.post(
            "/app-api/store/desk/orders/pay",
            {"orderNo": child_order_no, "golferNo": "", "filter": {"storeNo": STORE_NO}},
            token=xcx_token, step_name="小程序支付后校验"
        )
        pay_result_data = response.get_data(default={})
        log_payment_info(pay_result_data, prefix="  支付后校验: ")

        if pay_result_data.get("deskStatus") != "3":
            raise FlowError(f"桌台未关闭! deskStatus={pay_result_data.get('deskStatus')}")
        info(f"      ✓ 桌台已自动关闭! deskStatus=3")

        # Step 18: 关闭支付会话（小程序端）
        api_client.post(
            "/app-api/store/desk/orders/cancelPay",
            {"orderNo": child_order_no, "filter": {"storeNo": STORE_NO}},
            token=xcx_token, step_name="小程序cancelPay"
        )
        info(f"      支付会话已关闭!")

        # Step 19: 最终详情校验（Web端）
        response = api_client.post(
            "/merchant-api/store/desk/orders/detail",
            {"id": order_no, "filter": {"storeNo": STORE_NO}},
            token, "最终detail(Web)"
        )
        final_data = response.get_data(default={})
        log_payment_info(final_data, prefix="  最终校验: ")

        if final_data.get("deskStatus") != "3":
            raise FlowError(f"父订单桌台状态异常! deskStatus={final_data.get('deskStatus')}")
        info(f"      ✓ 父订单桌台已关闭! deskStatus=3")

        info("=" * 60)
        info("   小程序支付流程测试全部通过!")
        info("=" * 60)

    finally:
        # Assert（清理）：Web 端删除资源
        info("  清理测试资源...")
        from utils.test_helpers import cleanup_region, cleanup_fee, cleanup_desk
        cleanup_desk(api_client, token, desk_id, strict=False)
        cleanup_fee(api_client, token, fee_id, strict=False)
        cleanup_region(api_client, token, region_id, strict=False)
        info("  资源清理完成!")
