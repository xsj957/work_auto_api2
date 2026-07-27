# -*- coding: utf-8 -*-
"""
支付测试 - 公共辅助函数
======================
支付专属逻辑（资源管理已从 utils.test_helpers 统一导入）。

保留：
- PAYMENT_CHANNELS 支付渠道配置
- FlowError 异常类（向后兼容）
- log_payment_info 支付日志
- checkout_and_calc 结账+计算金额
- find_and_bind_member 会员查询+绑定
- create_payment 创建支付单
- submit_payment 提交支付
- get_member_balance 查询余额
- verify_no_duplicate 校验重复收款
"""

import json
import time

from utils.config import config
from utils.debug_utils import info
from utils.test_helpers import (
    # 共享配置
    STORE_NO, MERCHANT_NO,
    # 资源管理（复用，不重复写）
    create_region, verify_region,
    create_fee, verify_fee,
    create_desk, verify_desk, verify_desk_idle,
    close_desk, open_clock,
    poll_until_found,
    # 异常
    TestFlowError,
)

BASE_URL = config.host + "/fast"  # 向后兼容

# ================================================================
#  配置常量
# ================================================================

_pt = config.payment_test

# 支付渠道列表：[(code, name, phone), ...]
PAYMENT_CHANNELS = [
    (ch['code'], ch['name'], ch.get('phone', ''))
    for ch in _pt.get('channels', [])
]


# ================================================================
#  异常类（向后兼容）
# ================================================================

class FlowError(TestFlowError):
    """支付流程异常（继承 TestFlowError，保持向后兼容）"""
    pass


# ================================================================
#  工具函数
# ================================================================

def log_payment_info(response_data, prefix=""):
    """记录支付相关的核心字段"""
    detail = response_data if isinstance(response_data, dict) else {}
    if not detail:
        return
    info(f"{prefix}订单号={detail.get('orderNo', 'N/A')}")
    info(f"{prefix}桌台状态={detail.get('deskStatus', 'N/A')}({detail.get('statusName', 'N/A')})")
    info(f"{prefix}订单总额={detail.get('totalAmount', 0)}元")
    info(f"{prefix}台费={detail.get('feePrice', 0)}元")
    info(f"{prefix}商品={detail.get('productPrice', 0)}元")
    info(f"{prefix}服务={detail.get('servePrice', 0)}元")
    info(f"{prefix}实付金额={detail.get('actualPayMoney', 0)}元")
    info(f"{prefix}已收金额={detail.get('receivePayMoney', 0)}元")
    info(f"{prefix}未付金额={detail.get('noPayMoney', 0)}元")

    payment_list = detail.get("paymentList", [])
    if payment_list:
        info(f"{prefix}支付记录: 共{len(payment_list)}笔")
        for p in payment_list:
            info(f"{prefix}  - {p.get('payTypeName', 'N/A')} {p.get('paymentPrice', 0)}元, "
                  f"状态={p.get('paymentStatusName', 'N/A')}, "
                  f"payOrderId={p.get('payOrderId', 'N/A')}")

    relations = detail.get("ordersRelations", [])
    if relations:
        info(f"{prefix}关联子订单: {len(relations)}个")
        for r in relations:
            info(f"{prefix}  - {r.get('orderNo', 'N/A')}, 状态={r.get('status', 'N/A')}")

    paid = detail.get("paidOrderNos", [])
    if paid:
        info(f"{prefix}已支付子订单: {paid}")

    fee_time = detail.get("totalFeeTimeMinutes", 0)
    if fee_time:
        info(f"{prefix}总计费时长={fee_time}分钟")

    fee_list = detail.get("feeList", [])
    if fee_list:
        info(f"{prefix}台费明细: 共{len(fee_list)}条")
        for f in fee_list:
            info(f"{prefix}  - 时长={f.get('feeTimeMinute', 0)}分钟, "
                  f"金额={f.get('feePrice', 0)}元, "
                  f"规则={f.get('segmentRule', 'N/A')}")


# ================================================================
#  支付流程步骤封装
# ================================================================

def open_desk(api_client, token, desk_no):
    """计时开台（支付场景需要等待65秒确保计费）"""
    order_no = open_clock(api_client, token, desk_no)
    info(f"      等待65秒，确保产生至少1分钟计费...")
    time.sleep(65)
    return order_no


def checkout_and_calc(api_client, token, order_no, golfer_no=None):
    """结账 + 计算金额"""
    # 结账
    info(f"  结账（closeDesk, close=false）... orderNo={order_no}")
    response = close_desk(api_client, token, order_no, close=False)
    data = response.get_data()
    child_order_no = data if not isinstance(data, dict) else data
    if not child_order_no:
        child_order_no = order_no
    info(f"      结账成功! 子订单号={child_order_no}")

    # 计算金额
    payload = {"orderNo": child_order_no}
    if golfer_no:
        payload["golferNo"] = golfer_no
    info(f"  计算金额（pay）... orderNo={child_order_no}, golferNo={golfer_no or '无'}")
    api_client.post(
        "/merchant-api/store/desk/orders/pay", payload, token, "计算金额"
    )

    # 获取真实金额
    payload2 = {"id": child_order_no, "filter": {"storeNo": STORE_NO}}
    response2 = api_client.post(
        "/merchant-api/store/desk/orders/detail", payload2, token, "获取金额"
    )
    total_amount = response2.get_data("totalAmount", default=0)
    info(f"      应付金额={total_amount}元")

    return child_order_no, total_amount


def find_and_bind_member(api_client, token, desk_no, member_phone):
    """查询会员并绑定桌台"""
    # 查询会员
    info(f"  查询会员... 手机号={member_phone}")
    payload = {
        "storeNo": STORE_NO,
        "pageNo": 1,
        "pageSize": 10,
        "searchName": member_phone,
        "filter": {"storeNo": STORE_NO},
    }
    response = api_client.post(
        "/merchant-api/store/golfer/pageV2", payload, token, "查询会员"
    )
    golfer_list = response.get_data("list", default=[])
    if not golfer_list:
        raise FlowError(f"未找到手机号={member_phone}的会员")
    golfer_no = golfer_list[0].get("golferNo")
    golfer_name = golfer_list[0].get("golferName")
    balance = golfer_list[0].get("totalBalance", 0)
    info(f"      会员: golferNo={golfer_no}, 姓名={golfer_name}, 余额={balance}元")

    # 绑定会员到桌台
    info(f"  绑定会员到桌台... deskNo={desk_no}, golferNo={golfer_no}")
    payload2 = {
        "deskNo": desk_no,
        "golferNoList": [golfer_no],
        "filter": {"storeNo": STORE_NO},
    }
    api_client.post(
        "/merchant-api/store/desk/addGolfer", payload2, token, "绑定会员"
    )
    info(f"      会员绑定成功!")

    return golfer_no


def create_payment(api_client, token, order_no, payment_price, golfer_no=None):
    """创建支付单"""
    payload = {
        "orderNo": order_no,
        "paymentPrice": payment_price,
        "needPrintBill": False,
    }
    if golfer_no:
        payload["golferNo"] = golfer_no
    info(f"  创建支付单... orderNo={order_no}, 金额={payment_price}元")
    time.sleep(2)
    response = api_client.post(
        "/merchant-api/store/desk/orders/payment/create", payload, token, "创建支付单"
    )
    pay_order_id = response.get_data()
    if isinstance(pay_order_id, dict):
        pay_order_id = pay_order_id.get("payOrderId") or pay_order_id.get("id") or pay_order_id
    # 强制转 int，防止服务端期望 Long 但收到 Object
    if pay_order_id is not None:
        try:
            pay_order_id = int(pay_order_id)
        except (ValueError, TypeError):
            pass
    info(f"      支付单创建成功! payOrderId={pay_order_id}")
    return pay_order_id


def submit_payment(api_client, token, pay_order_id, order_no, payment_price,
                   golfer_no=None, channel_code="cash"):
    """提交支付"""
    payload = {
        "id": pay_order_id,
        "channelCode": channel_code,
    }

    # 余额支付需要 channelExtras
    if golfer_no and channel_code in ["czk", "tfk"]:
        extra_obj = {
            "orderType": "桌台订单",
            "givePrice": "0",
            "storeNo": STORE_NO,
            "couponName": "",
            "orderNo": order_no,
            "price": str(payment_price),
            "couponPrice": "0",
            "TfkGivenPrice": "0",
        }
        payload["channelExtras"] = {
            "flow_type": "1",
            "extra": json.dumps(extra_obj, ensure_ascii=False),
            "golfer_no": golfer_no,
            "channelCode": channel_code,
        }
        payload["filter"] = {"storeNo": STORE_NO}

    info(f"  提交支付... payOrderId={pay_order_id}, channelCode={channel_code}")
    api_client.post(
        "/merchant-api/pay/order/submit", payload, token, "提交支付", expect_code=200
    )
    info(f"      支付提交成功!")


def get_member_balance(api_client, token, phone, label=""):
    """查询会员余额"""
    payload = {
        "storeNo": STORE_NO,
        "pageNo": 1,
        "pageSize": 10,
        "searchName": phone,
        "filter": {"storeNo": STORE_NO},
    }
    response = api_client.post(
        "/merchant-api/store/golfer/pageV2", payload, token, f"查余额{label or phone}"
    )
    g_list = response.get_data("list", default=[])
    if not g_list:
        info(f"      未找到会员: {phone}")
        return None
    g = g_list[0]
    balance = g.get("totalBalance", 0)
    desk_balance = g.get("deskBalance", 0)
    info(f"      {label or phone}: 总余额={balance}元, 台费卡={desk_balance}元")
    return balance


def verify_no_duplicate(api_client, token, child_order_no, expected_amount):
    """校验是否未发生重复收款"""
    payload = {
        "orderNo": child_order_no,
        "golferNo": "",
        "filter": {"storeNo": STORE_NO},
    }
    info(f"  校验支付结果... orderNo={child_order_no}")
    response = api_client.post(
        "/merchant-api/store/desk/orders/pay", payload, token, "校验支付"
    )
    result = response.get_data(default={})

    payment_list = result.get("paymentList", [])
    success_count = sum(1 for p in payment_list if p.get("paymentStatus") == "success")
    total_paid = sum(p.get("paymentPrice", 0) for p in payment_list if p.get("paymentStatus") == "success")

    info(f"      支付记录: 共{len(payment_list)}笔, 成功{success_count}笔")
    for p in payment_list:
        info(f"        - {p.get('payTypeName')} {p.get('paymentPrice')}元, 状态={p.get('paymentStatusName')}")
    info(f"      实付总额={total_paid}元, 应付={expected_amount}元")

    if success_count > 1:
        info(f"      ❌ Bug复现! 同一订单有 {success_count} 笔成功支付，累计 {total_paid}元")
        raise FlowError(f"重复收款! {success_count}笔成功支付, 累计{total_paid}元")
    elif success_count == 1 and total_paid > expected_amount:
        info(f"      ❌ Bug复现! 单笔支付金额 {total_paid}元 > 应付 {expected_amount}元")
        raise FlowError(f"超额收款! 实付{total_paid}元 > 应付{expected_amount}元")
    else:
        info(f"      ✓ 未发生重复收款，支付结果正常")

    return result
