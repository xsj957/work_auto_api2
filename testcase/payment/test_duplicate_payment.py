# -*- coding: utf-8 -*-
"""
重复收款 Bug 测试 - 余额支付并发支付场景

验证: 同一桌台订单在同一秒内发起两次支付，系统是否能防止重复收款

流程:
  登录 → 新增区域 → 新增台费 → 新增桌台 → 查询校验
  → listV3校验空闲 → 查询会员 → 绑定会员
  → 计时开台 → 等待计费 → detail → needPay → 结账 → pay
  → 并发创建两笔支付单 → 并发提交两笔支付
  → 校验是否只有一笔支付成功
  → 清理数据
"""

import json
import multiprocessing
import time

import pytest
import requests as http_requests

from utils.config import config
from utils.payment_helpers import (
    STORE_NO,
    create_region, verify_region,
    create_fee, verify_fee,
    create_desk, verify_desk, verify_desk_idle,
    open_desk, checkout_and_calc,
    find_and_bind_member, create_payment, submit_payment,
    verify_no_duplicate, get_member_balance,
    FlowError,
)
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority
from utils.test_helpers import _gen_suffix, cleanup_desk, cleanup_fee, cleanup_region


# ============================================================
#  多进程 worker（模块级函数，multiprocessing 要求可 pickle）
# ============================================================

def _submit_worker(url_submit, payload, headers, fire, result_queue):
    """
    多进程并发 submit worker。
    模拟 JMeter 线程组：每个进程是独立的 HTTP 客户端，
    等待 fire 信号后同时发出请求。
    """
    fire.wait()
    try:
        resp = http_requests.post(url_submit, json=payload, headers=headers, timeout=15, verify=False)
        data = resp.json()
    except Exception as e:
        data = {"code": 0, "msg": str(e)}
    result_queue.put(data)


def _create_worker(url_create, payload, headers, fire, result_queue, idx):
    """多进程并发 create worker。"""
    fire.wait()
    try:
        resp = http_requests.post(url_create, json=payload, headers=headers, timeout=15, verify=False)
        data = resp.json()
    except Exception as e:
        data = {"code": 0, "msg": str(e), "data": None}
    result_queue.put({"idx": idx, "code": data.get("code", 0), "msg": data.get("msg", ""), "data": data.get("data")})


def _close_worker(url_close, payload, headers, fire, result_queue):
    """多进程 closeDesk worker。"""
    fire.wait()
    try:
        resp = http_requests.post(url_close, json=payload, headers=headers, timeout=15, verify=False)
        data = resp.json()
    except Exception as e:
        data = {"code": 0, "msg": str(e), "data": None}
    result_queue.put({"type": "close", "code": data.get("code", 0), "msg": data.get("msg", ""), "data": data.get("data")})


def _cancel_worker(url_cancel, payload, headers, fire, result_queue):
    """多进程 cancelPay worker。"""
    fire.wait()
    try:
        resp = http_requests.post(url_cancel, json=payload, headers=headers, timeout=15, verify=False)
        data = resp.json()
    except Exception as e:
        data = {"code": 0, "msg": str(e), "data": None}
    result_queue.put({"type": "cancel", "code": data.get("code", 0), "msg": data.get("msg", ""), "data": data.get("data")})


# ============================================================
#  公共辅助函数
# ============================================================


def _cleanup_resources(api_client, token, region_id, fee_id, desk_id):
    """统一清理测试资源"""
    info("  清理测试资源...")
    cleanup_desk(api_client, token, desk_id, strict=False)
    cleanup_fee(api_client, token, fee_id, strict=False)
    cleanup_region(api_client, token, region_id, strict=False)
    info("  资源清理完成!")


def _setup_ready_to_pay(api_client, auth_context):
    """公共前置：创建完整环境并结账就绪。返回 (token, merchant_no, golfer_no, child_order_no, total_amount, region_id, fee_id, desk_id)"""
    suffix = _gen_suffix()
    tag = f"_{suffix}"
    region_name = f"测试区{tag}"
    fee_name = f"测试费{tag}"
    desk_name = f"测试桌台{tag}"

    token = auth_context.token
    merchant_no = auth_context.merchant_no

    # 创建环境
    region_id = create_region(api_client, token, merchant_no, name=region_name)
    region_no = verify_region(api_client, token, name=region_name)

    create_fee(api_client, token, merchant_no, name=fee_name)
    fee_no, fee_id = verify_fee(api_client, token, name=fee_name)

    create_desk(api_client, token, region_no, fee_no, fee_name, desk_name=desk_name)
    desk_no, desk_id = verify_desk(api_client, token, name=desk_name)
    verify_desk_idle(api_client, token, name=desk_name)

    # 从配置读取会员手机号
    member_phone = config.business_data.get("golferPhones", ["13538506002"])[0]
    golfer_no = find_and_bind_member(api_client, token, desk_no, member_phone)
    order_no = open_desk(api_client, token, desk_no)
    child_order_no, total_amount = checkout_and_calc(api_client, token, order_no, golfer_no)

    return token, merchant_no, golfer_no, child_order_no, total_amount, region_id, fee_id, desk_id


def _do_concurrent_submit(api_client, auth_context, channel_code="czk"):
    """并发 submit 核心逻辑，支持不同支付渠道（多进程实现）"""
    info("=" * 60)
    info(f"  用例2[{channel_code}]: 并发 submit - 同一 payOrderId 异步同时提交两次")
    info("=" * 60)
    token, _, golfer_no, child_order_no, total_amount, region_id, fee_id, desk_id = _setup_ready_to_pay(api_client, auth_context)

    try:
        pay_order_id = create_payment(api_client, token, child_order_no, total_amount, golfer_no)

        # 多进程并发 submit
        base_url = config.host + "/fast"
        url_submit = f"{base_url}/merchant-api/pay/order/submit"

        extra_obj = {
            "orderType": "桌台订单",
            "givePrice": "0",
            "storeNo": STORE_NO,
            "couponName": "",
            "orderNo": child_order_no,
            "price": str(total_amount),
            "couponPrice": "0",
            "TfkGivenPrice": "0",
        }
        submit_payload = {
            "id": pay_order_id,
            "channelCode": channel_code,
            "channelExtras": {
                "flow_type": "1",
                "extra": json.dumps(extra_obj, ensure_ascii=False),
                "golfer_no": golfer_no,
                "channelCode": channel_code,
            },
            "filter": {"storeNo": STORE_NO},
        }
        headers = {"Content-Type": "application/json", "Authorization": token}

        fire = multiprocessing.Event()
        result_queue = multiprocessing.Queue()
        processes = []

        for i in range(2):
            p = multiprocessing.Process(
                target=_submit_worker,
                args=(url_submit, submit_payload, headers, fire, result_queue),
                name=f"submit-{i+1}",
            )
            processes.append(p)

        for p in processes:
            p.start()

        time.sleep(0.5)
        info(f"  发令！2 个进程同时发出 submit 请求...")
        fire.set()

        for p in processes:
            p.join(timeout=30)

        # 收集结果
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        success_count = sum(1 for r in results if r.get("code") == 200)
        for idx, r in enumerate(results):
            if r.get("code") == 200:
                info(f"      第{idx+1}次 submit 成功 ✅")
            else:
                info(f"      第{idx+1}次 submit 失败: {r.get('msg')}")

        info(f"      结果: {success_count} 笔成功, {2 - success_count} 笔失败")
        if success_count >= 2:
            info(f"      ⚠️️⚠️ 两次 submit 都成功! 发生重复扣款!")

        time.sleep(3)
        verify_no_duplicate(api_client, token, child_order_no, total_amount)

    finally:
        _cleanup_resources(api_client, token, region_id, fee_id, desk_id)


def _verify_two_golfers(api_client, token, child_order_no):
    """校验双会员支付结果（支付记录 + 余额）"""
    response = api_client.post(
        "/merchant-api/store/desk/orders/pay",
        {"orderNo": child_order_no, "golferNo": "", "filter": {"storeNo": STORE_NO}},
        token, "校验支付"
    )
    result = response.get_data(default={})
    payment_list = result.get("paymentList", [])
    success_count = sum(1 for p in payment_list if p.get("paymentStatus") == "success")
    total_paid = sum(p.get("paymentPrice", 0) for p in payment_list if p.get("paymentStatus") == "success")

    info(f"      支付记录: 共{len(payment_list)}笔, 成功{success_count}笔, 实付总额={total_paid}元")
    for p in payment_list:
        info(f"        - {p.get('payTypeName')} {p.get('paymentPrice')}元, "
              f"状态={p.get('paymentStatusName')}")

    if success_count > 1:
        info(f"       ⚠️ 支付记录异常: {success_count}笔成功支付")
    else:
        info(f"      ✓ 支付记录正常: {success_count}笔成功")


def _setup_two_golfers(api_client, auth_context):
    """
    双会员前置：创建资源 + 查询两个会员 + 绑定到桌台 + 开台 + 结账。
    返回 dict: golfer_a, golfer_b, golfer_no_a, golfer_no_b, child_order_no,
               total_amount, desk_no, region_id, fee_id, desk_id,
               balance_a_before, balance_b_before, golfer_a_info, golfer_b_info
    """
    suffix = _gen_suffix()
    tag = f"_{suffix}"
    region_name = f"测试区{tag}"
    fee_name = f"测试费{tag}"
    desk_name = f"测试桌台{tag}"

    token = auth_context.token
    merchant_no = auth_context.merchant_no

    # 创建资源
    region_id = create_region(api_client, token, merchant_no, name=region_name)
    region_no = verify_region(api_client, token, name=region_name)
    create_fee(api_client, token, merchant_no, name=fee_name)
    fee_no, fee_id = verify_fee(api_client, token, name=fee_name)
    create_desk(api_client, token, region_no, fee_no, fee_name, desk_name=desk_name)
    desk_no, desk_id = verify_desk(api_client, token, name=desk_name)
    verify_desk_idle(api_client, token, name=desk_name)

    # 查询两个会员（从配置读取手机号）
    phones = config.business_data.get("golferPhones", ["13538506002"])
    if len(phones) < 2:
        raise FlowError(f"config.yaml golferPhones 需至少2个手机号，当前只有{len(phones)}个")

    golfer_info = {}
    for phone in phones[:2]:
        response = api_client.post(
            "/merchant-api/store/golfer/pageV2",
            {"storeNo": STORE_NO, "pageNo": 1, "pageSize": 10,
             "searchName": phone, "filter": {"storeNo": STORE_NO}},
            token, f"查询会员{phone}"
        )
        g_list = response.get_data("list", default=[])
        if not g_list:
            raise FlowError(f"未找到手机号={phone}的会员")
        g = g_list[0]
        golfer_info[phone] = {
            "golferNo": g.get("golferNo"),
            "name": g.get("golferName"),
            "balance_before": g.get("totalBalance", 0),
        }
        info(f"  会员{phone}: golferNo={g.get('golferNo')}, "
             f"姓名={g.get('golferName')}, 初始余额={g.get('totalBalance', 0)}元")

    phone_a, phone_b = phones[0], phones[1]
    golfer_no_a = golfer_info[phone_a]["golferNo"]
    golfer_no_b = golfer_info[phone_b]["golferNo"]

    # 绑定两个会员到桌台
    api_client.post(
        "/merchant-api/store/desk/addGolfer",
        {"deskNo": desk_no, "golferNoList": [golfer_no_a, golfer_no_b],
         "filter": {"storeNo": STORE_NO}},
        token, "绑定两个会员"
    )
    info(f"  两个会员已绑定到桌台: [{golfer_no_a}, {golfer_no_b}]")

    # 开台 → 结账
    order_no = open_desk(api_client, token, desk_no)
    child_order_no, total_amount = checkout_and_calc(api_client, token, order_no, golfer_no_a)

    return {
        "token": token,
        "golfer_no_a": golfer_no_a,
        "golfer_no_b": golfer_no_b,
        "child_order_no": child_order_no,
        "total_amount": total_amount,
        "desk_no": desk_no,
        "region_id": region_id,
        "fee_id": fee_id,
        "desk_id": desk_id,
        "balance_a_before": golfer_info[phone_a]["balance_before"],
        "balance_b_before": golfer_info[phone_b]["balance_before"],
        "golfer_a_info": golfer_info[phone_a],
        "golfer_b_info": golfer_info[phone_b],
    }


# ============================================================
#  pytest 测试用例
# ============================================================

# ============================================================
#  用例1: 同一子订单并发 create（同一秒发出两个请求）
# ============================================================
@pytest.mark.payment
@mark_priority(0)
@capture_failure
def test_01_concurrent_create(api_client, auth_context):
    """
    风险: payment/create 未校验同一子订单是否已有 pay_order
    预期: 第二次 create 应被拒绝，或两条 create 只有一条能 submit 成功
    """
    info("=" * 60)
    info("  用例1: 并发 create - 同一子订单同一秒两次创建支付单")
    info("=" * 60)
    token, _, golfer_no, child_order_no, total_amount, region_id, fee_id, desk_id = _setup_ready_to_pay(api_client, auth_context)

    try:
        # 多进程并发 create
        base_url = config.host + "/fast"
        url_create = f"{base_url}/merchant-api/store/desk/orders/payment/create"
        headers = {"Content-Type": "application/json", "Authorization": token}
        payload = {"orderNo": child_order_no, "paymentPrice": total_amount,
                   "needPrintBill": False, "golferNo": golfer_no}

        fire = multiprocessing.Event()
        result_queue = multiprocessing.Queue()
        processes = []

        for i in range(2):
            p = multiprocessing.Process(
                target=_create_worker,
                args=(url_create, payload, headers, fire, result_queue, i + 1),
                name=f"create-{i+1}",
            )
            processes.append(p)

        for p in processes:
            p.start()

        time.sleep(0.5)
        info(f"  发令！2 个进程同时发出 create 请求...")
        fire.set()

        for p in processes:
            p.join(timeout=30)

        # 收集结果
        results = {}
        while not result_queue.empty():
            r = result_queue.get()
            results[r["idx"]] = {"code": r["code"], "msg": r["msg"], "data": r["data"]}
            info(f"      进程{r['idx']}: code={r['code']}, msg={r['msg']}, payOrderId={r['data']}")

        success_ids = [r["data"] for r in results.values() if r["code"] == 200 and r["data"]]
        info(f"  成功创建 {len(success_ids)} 笔支付单: {success_ids}")

        for pid in success_ids:
            try:
                submit_payment(api_client, token, pid, child_order_no, total_amount, golfer_no)
            except Exception as e:
                info(f"      submit {pid} 失败(预期内): {e}")

        time.sleep(3)
        verify_no_duplicate(api_client, token, child_order_no, total_amount)

    finally:
        _cleanup_resources(api_client, token, region_id, fee_id, desk_id)


# ============================================================
#  用例2: 同一 payOrderId 重复 submit（储值卡）
# ============================================================
@pytest.mark.payment
@mark_priority(0)
@capture_failure
def test_02_double_submit(api_client, auth_context):
    """储值卡(czk)并发 submit - 同一 payOrderId 异步同时提交两次"""
    _do_concurrent_submit(api_client, auth_context, channel_code="czk")


# ============================================================
#  用例2-tfk: 同一 payOrderId 重复 submit（台费卡）
# ============================================================
@pytest.mark.payment
@mark_priority(0)
@capture_failure
def test_02_double_submit_tfk(api_client, auth_context):
    """台费卡(tfk)并发 submit - 同一 payOrderId 异步同时提交两次"""
    _do_concurrent_submit(api_client, auth_context, channel_code="tfk")


# ============================================================
#  用例3: 支付成功后再 create
# ============================================================
@pytest.mark.payment
@mark_priority(0)
@capture_failure
def test_03_create_after_paid(api_client, auth_context):
    """
    风险: 支付成功后订单状态已变，但 create 未校验订单状态仍允许创建新支付单
    预期: 支付成功后再次 create 应被拒绝
    """
    info("=" * 60)
    info("  用例3: 支付成功后再 create - 已支付订单能否再创建支付单")
    info("=" * 60)
    token, _, golfer_no, child_order_no, total_amount, region_id, fee_id, desk_id = _setup_ready_to_pay(api_client, auth_context)

    try:
        # 第1笔: 正常创建+提交+成功
        pay_order_id = create_payment(api_client, token, child_order_no, total_amount, golfer_no)
        try:
            submit_payment(api_client, token, pay_order_id, child_order_no, total_amount, golfer_no)
            info(f"      第1笔支付成功")
        except Exception as e:
            info(f"      第1笔支付失败: {e}")

        time.sleep(2)

        # 支付成功后再 create
        try:
            pay_order_id_2 = create_payment(api_client, token, child_order_no, total_amount, golfer_no)
            info(f"      ⚠️ 支付成功后仍创建成功! payOrderId={pay_order_id_2}")
            # 如果创建成功，尝试提交
            try:
                submit_payment(api_client, token, pay_order_id_2, child_order_no, total_amount, golfer_no)
                info(f"      ️ 第2笔也提交成功! 可能重复收款")
            except Exception as e:
                info(f"      第2笔提交失败(预期内): {e}")
        except Exception as e:
            info(f"      支付成功后 create 被拒绝(预期内): {e}")

        time.sleep(3)
        verify_no_duplicate(api_client, token, child_order_no, total_amount)

    finally:
        _cleanup_resources(api_client, token, region_id, fee_id, desk_id)


# ============================================================
#  用例4: 极短间隔连续 submit（非同一 payOrderId）
# ============================================================
@pytest.mark.payment
@mark_priority(0)
@capture_failure
def test_04_rapid_submit(api_client, auth_context):
    """
    风险: 两笔不同的 payOrderId，极短间隔连续 submit，第二笔可能绕过状态检查
    预期: 只有第一笔成功，第二笔应被拒绝
    """
    info("=" * 60)
    info("  用例4: 极短间隔连续 submit - 两笔不同 payOrderId 快速提交")
    info("=" * 60)
    token, _, golfer_no, child_order_no, total_amount, region_id, fee_id, desk_id = _setup_ready_to_pay(api_client, auth_context)

    try:
        # 创建第1笔支付单
        pay_order_id_1 = create_payment(api_client, token, child_order_no, total_amount, golfer_no)

        # 尝试创建第2笔（系统可能拒绝：同一子订单只允许一笔未支付订单）
        pay_order_id_2 = None
        try:
            time.sleep(1)
            pay_order_id_2 = create_payment(api_client, token, child_order_no, total_amount, golfer_no)
            info(f"  ⚠️ 第2笔支付单也创建成功! {pay_order_id_2}")
        except Exception as e:
            info(f"  第2笔 create 被拒绝(预期内): {e}")
            info(f"  系统不允许同一子订单存在多笔未支付订单，改为重复 submit 第1笔")

        if pay_order_id_2:
            # 两笔都创建成功，连续快速 submit
            try:
                submit_payment(api_client, token, pay_order_id_1, child_order_no, total_amount, golfer_no)
                info(f"      第1笔 submit 成功")
            except Exception as e:
                info(f"      第1笔 submit 失败: {e}")
            try:
                submit_payment(api_client, token, pay_order_id_2, child_order_no, total_amount, golfer_no)
                info(f"      ⚠️ 第2笔 submit 也成功! 需校验是否重复扣款")
            except Exception as e:
                info(f"      第2笔 submit 失败(预期内): {e}")
        else:
            # 只有1笔支付单，重复 submit 同一个 ID
            try:
                submit_payment(api_client, token, pay_order_id_1, child_order_no, total_amount, golfer_no)
                info(f"      第1次 submit 成功")
            except Exception as e:
                info(f"      第1次 submit 失败: {e}")
            try:
                submit_payment(api_client, token, pay_order_id_1, child_order_no, total_amount, golfer_no)
                info(f"      ️ 第2次 submit 也成功! 需校验是否重复扣款")
            except Exception as e:
                info(f"      第2次 submit 失败(预期内): {e}")

        time.sleep(3)
        verify_no_duplicate(api_client, token, child_order_no, total_amount)

    finally:
        _cleanup_resources(api_client, token, region_id, fee_id, desk_id)


# ============================================================
#  用例5: 结账未完成就 create（race condition）
# ============================================================
@pytest.mark.payment
@mark_priority(0)
@capture_failure
def test_05_create_during_checkout(api_client, auth_context):
    """
    风险: closeDesk(close=false) 还未完成时，并发调用 payment/create
    此时订单状态可能仍是1(已开台)，create 可能绕过状态检查
    预期: create 应等待结账完成或被拒绝
    """
    info("=" * 60)
    info("  用例5: 结账中并发 create - closeDesk 未完成时调用 payment/create")
    info("=" * 60)
    token, _, golfer_no, child_order_no_unused, total_amount, region_id, fee_id, desk_id = _setup_ready_to_pay(api_client, auth_context)

    try:
        # 多进程并发: closeDesk + create
        base_url = config.host + "/fast"
        url_close = f"{base_url}/merchant-api/store/desk/orders/closeDesk"
        url_create = f"{base_url}/merchant-api/store/desk/orders/payment/create"
        headers = {"Content-Type": "application/json", "Authorization": token}

        close_payload = {"orderNo": child_order_no_unused, "close": False, "filter": {"storeNo": STORE_NO}}
        create_payload = {"orderNo": child_order_no_unused, "paymentPrice": total_amount,
                          "needPrintBill": False, "golferNo": golfer_no}

        fire = multiprocessing.Event()
        result_queue = multiprocessing.Queue()

        p_close = multiprocessing.Process(
            target=_close_worker,
            args=(url_close, close_payload, headers, fire, result_queue),
            name="close-desk",
        )
        p_create = multiprocessing.Process(
            target=_create_worker,
            args=(url_create, create_payload, headers, fire, result_queue, 1),
            name="create-payment",
        )

        p_close.start()
        p_create.start()

        time.sleep(0.5)
        info(f"  发令！closeDesk 和 create 同时发出...")
        fire.set()

        p_close.join(timeout=30)
        p_create.join(timeout=30)

        # 收集结果
        close_result = {}
        create_result = {}
        while not result_queue.empty():
            r = result_queue.get()
            if r.get("type") == "close":
                close_result["data"] = {"code": r["code"], "msg": r["msg"], "data": r["data"]}
            else:
                create_result["data"] = {"code": r["code"], "msg": r["msg"], "data": r["data"]}

        create_code = create_result.get("data", {}).get("code", 0)
        close_code = close_result.get("data", {}).get("code", 0)
        info(f"  closeDesk code={close_code}, create code={create_code}")

        if create_code == 200:
            info(f"      ️ 结账未完成时 create 成功，需校验是否重复")
            pay_id = create_result["data"].get("data")
            if pay_id:
                try:
                    submit_payment(api_client, token, pay_id, child_order_no_unused, total_amount, golfer_no)
                    info(f"      ️ submit 也成功!")
                except Exception as e:
                    info(f"      submit 失败(预期内): {e}")
        else:
            info(f"      ✓ 结账未完成时 create 被拒绝")

        time.sleep(3)
        verify_no_duplicate(api_client, token, child_order_no_unused, total_amount)

    finally:
        _cleanup_resources(api_client, token, region_id, fee_id, desk_id)


# ============================================================
#  用例6: 双会员余额支付 - A支付 B关闭页面
# ============================================================
@pytest.mark.payment
@mark_priority(0)
@capture_failure
def test_06_two_golfers_pay_vs_cancel(api_client, auth_context):
    """
    Bug场景: 同一桌台，两个会员都打开支付页面
    A用户点击支付，B用户同一时间关闭支付页面
    预期: 只有A扣款，B不应扣款
    实际Bug: 两个会员都被扣款
    """
    info("=" * 60)
    info("  用例6: 双会员余额支付 - A支付 + B关闭页面")
    info("=" * 60)
    token, _, _, child_order_no, total_amount, region_id, fee_id, desk_id = _setup_ready_to_pay(api_client, auth_context)

    try:
        # 查询两个会员（从配置读取手机号）
        phones = config.business_data.get("golferPhones", ["13538506002"])
        if len(phones) < 2:
            raise FlowError(f"config.yaml golferPhones 需至少2个手机号，当前只有{len(phones)}个")
        golfer_nos = []
        for phone in phones[:2]:
            response = api_client.post(
                "/merchant-api/store/golfer/pageV2",
                {"storeNo": STORE_NO, "pageNo": 1, "pageSize": 10,
                 "searchName": phone, "filter": {"storeNo": STORE_NO}},
                token, f"查询会员{phone}"
            )
            g_list = response.get_data("list", default=[])
            if g_list:
                g_no = g_list[0].get("golferNo")
                g_name = g_list[0].get("golferName")
                g_balance = g_list[0].get("totalBalance", 0)
                golfer_nos.append(g_no)
                info(f"  会员: {phone} → golferNo={g_no}, 姓名={g_name}, 余额={g_balance}元")
            else:
                info(f"  未找到手机号={phone}的会员!")
                raise FlowError(f"未找到会员: {phone}")

        golfer_a, golfer_b = golfer_nos[0], golfer_nos[1]
        info(f"  会员A({golfer_a}) 将支付，会员B({golfer_b}) 将关闭页面")

        # 第1步: A先创建支付单（串行，避免"点击过快"）
        info(f"  第1步: A创建支付单...")
        response_a = api_client.post(
            "/merchant-api/store/desk/orders/payment/create", {
                "orderNo": child_order_no, "paymentPrice": total_amount,
                "needPrintBill": False, "golferNo": golfer_a
            }, token, "A创建支付单", strict=False
        )

        if response_a.code != 200:
            info(f"  A创建支付单失败，测试终止")
            return
        pay_data_a = response_a.get_data()
        pay_id_a = pay_data_a.get("payOrderId") if isinstance(pay_data_a, dict) else pay_data_a
        info(f"      A的payOrderId={pay_id_a}")

        # 间隔1秒
        time.sleep(1)

        # 第2步: B创建支付单（串行）
        info(f"  第2步: B创建支付单...")
        response_b = api_client.post(
            "/merchant-api/store/desk/orders/payment/create", {
                "orderNo": child_order_no, "paymentPrice": total_amount,
                "needPrintBill": False, "golferNo": golfer_b
            }, token, "B创建支付单", strict=False
        )

        if response_b.code != 200:
            info(f"  B创建支付单失败: {response_b.msg}")
            # B创建失败，只测A单独支付
            info(f"  B未生成支付单，直接提交A的支付...")
            extra_obj = {"orderType": "桌台订单", "givePrice": "0", "storeNo": STORE_NO,
                         "couponName": "", "orderNo": child_order_no,
                         "price": str(total_amount), "couponPrice": "0", "TfkGivenPrice": "0"}
            api_client.post("/merchant-api/pay/order/submit", {
                "id": pay_id_a, "channelCode": "czk",
                "channelExtras": {"flow_type": "1",
                    "extra": json.dumps(extra_obj, ensure_ascii=False),
                    "golfer_no": golfer_a, "channelCode": "czk"},
                "filter": {"storeNo": STORE_NO}
            }, token, "A单独submit", strict=False)
            time.sleep(3)
            _verify_two_golfers(api_client, token, child_order_no)
            return

        pay_data_b = response_b.get_data()
        pay_id_b = pay_data_b.get("payOrderId") if isinstance(pay_data_b, dict) else pay_data_b
        info(f"      B的payOrderId={pay_id_b}")

        # 第3步: A提交支付 + B关闭支付页面（多进程并行）
        info(f"  第3步: A提交支付 + B关闭页面（多进程并行）...")
        base_url = config.host + "/fast"
        url_submit = f"{base_url}/merchant-api/pay/order/submit"
        url_cancel = f"{base_url}/merchant-api/store/desk/orders/cancelPay"
        headers = {"Content-Type": "application/json", "Authorization": token}

        extra_obj = {"orderType": "桌台订单", "givePrice": "0", "storeNo": STORE_NO,
                     "couponName": "", "orderNo": child_order_no,
                     "price": str(total_amount), "couponPrice": "0", "TfkGivenPrice": "0"}
        submit_payload = {
            "id": pay_id_a, "channelCode": "czk",
            "channelExtras": {"flow_type": "1",
                "extra": json.dumps(extra_obj, ensure_ascii=False),
                "golfer_no": golfer_a, "channelCode": "czk"},
            "filter": {"storeNo": STORE_NO},
        }
        cancel_payload = {"orderNo": child_order_no, "filter": {"storeNo": STORE_NO}}

        fire = multiprocessing.Event()
        result_queue = multiprocessing.Queue()

        p_submit = multiprocessing.Process(
            target=_submit_worker,
            args=(url_submit, submit_payload, headers, fire, result_queue),
            name="a-submit",
        )
        p_cancel = multiprocessing.Process(
            target=_cancel_worker,
            args=(url_cancel, cancel_payload, headers, fire, result_queue),
            name="b-cancel",
        )

        p_submit.start()
        p_cancel.start()

        time.sleep(0.5)
        info(f"  发令！A提交支付 + B关闭页面同时发出...")
        fire.set()

        p_submit.join(timeout=30)
        p_cancel.join(timeout=30)

        # 收集结果
        result_a = {}
        result_b = {}
        while not result_queue.empty():
            r = result_queue.get()
            if r.get("type") == "cancel":
                result_b["cancel"] = {"code": r["code"], "msg": r["msg"]}
            else:
                result_a["submit"] = {"code": r["code"], "msg": r["msg"]}

        info(f"  A结果: {result_a}")
        info(f"  B结果: {result_b}")

        time.sleep(3)
        _verify_two_golfers(api_client, token, child_order_no)

    finally:
        _cleanup_resources(api_client, token, region_id, fee_id, desk_id)


# ============================================================
#  用例7: 双会员高并发submit - 检测同一payOrderId重复扣款
# ============================================================
@pytest.mark.payment
@mark_priority(0)
@capture_failure
def test_07_two_golfers_concurrent_submit(api_client, auth_context):
    """多进程并发 submit 测试 - 检测余额异常扣款"""
    info("=" * 60)
    info("  用例7: 双会员高并发submit - 检测余额异常扣款")
    info("=" * 60)

    ctx = _setup_two_golfers(api_client, auth_context)
    token = ctx["token"]
    golfer_no_a = ctx["golfer_no_a"]
    child_order_no = ctx["child_order_no"]
    total_amount = ctx["total_amount"]
    region_id = ctx["region_id"]
    fee_id = ctx["fee_id"]
    desk_id = ctx["desk_id"]
    balance_a_before = ctx["balance_a_before"]
    balance_b_before = ctx["balance_b_before"]
    phones = config.business_data.get("golferPhones", ["13538506002"])
    phone_b = phones[1]

    info(f"  应付金额={total_amount}元")
    info(f"  会员A初始余额={balance_a_before}元, 会员B初始余额={balance_b_before}元")

    try:

        base_url = config.host + "/fast"
        url_submit = f"{base_url}/merchant-api/pay/order/submit"
        pay_order_id = create_payment(api_client, token, child_order_no, total_amount, golfer_no=None)
        info(f"  payOrderId={pay_order_id}")

        # ---- 多进程并发 submit（模拟 JMeter 线程组） ----
        extra_obj = {
            "orderType": "桌台订单",
            "givePrice": "0",
            "storeNo": STORE_NO,
            "couponName": "",
            "orderNo": child_order_no,
            "price": str(total_amount),
            "couponPrice": "0",
            "TfkGivenPrice": "0",
        }
        submit_payload = {
            "id": pay_order_id,
            "channelCode": "tfk",
            "channelExtras": {
                "flow_type": "1",
                "extra": json.dumps(extra_obj, ensure_ascii=False),
                "golfer_no": golfer_no_a,
                "channelCode": "tfk",
            },
            "filter": {"storeNo": STORE_NO},
        }

        CONCURRENCY = 1000  # 并发数
        fire = multiprocessing.Event()
        result_queue = multiprocessing.Queue()
        processes = []
        headers = {"Content-Type": "application/json", "Authorization": token}

        info(f"  启动 {CONCURRENCY} 个进程，payload 完全一致...")
        for i in range(CONCURRENCY):
            p = multiprocessing.Process(
                target=_submit_worker,
                args=(url_submit, submit_payload, headers, fire, result_queue),
                name=f"submit-{i+1}",
            )
            processes.append(p)

        # 先启动所有进程（此时都阻塞在 fire.wait()）
        for p in processes:
            p.start()

        # 确认所有进程都已就绪
        time.sleep(0.5)

        info(f"  发令！{CONCURRENCY} 个进程同时发出 submit 请求...")
        fire.set()  # 同一时刻释放所有进程

        # 等待所有进程完成
        for p in processes:
            p.join(timeout=30)

        # 收集结果
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        success_count = sum(1 for r in results if r.get("code") == 200)
        fail_count = len(results) - success_count
        info(f"  结果: 成功{success_count}次, 失败{fail_count}次, 总计{len(results)}次")
        for idx, r in enumerate(results):
            info(f"    [{idx+1}] code={r.get('code')}, msg={r.get('msg')}")

        # 等待服务端处理完成
        time.sleep(3)

        # 校验支付记录
        pay_data = api_client.post(
            "/merchant-api/store/desk/orders/pay",
            {"orderNo": child_order_no, "golferNo": "", "filter": {"storeNo": STORE_NO}},
            token, "校验支付记录"
        )
        payment_list = pay_data.get_data("paymentList", default=[])
        success_pays = [p for p in payment_list if p.get("paymentStatus") == "success"]
        info(f"  支付记录: 共{len(payment_list)}笔, 成功{len(success_pays)}笔")
        for p in success_pays:
            info(f"    - {p.get('payTypeName')} {p.get('paymentPrice')}元, golferNo={p.get('golferNo')}")

        # 校验余额
        balance_a_after = get_member_balance(api_client, token, phones[0], "会员A")
        balance_b_after = get_member_balance(api_client, token, phone_b, "会员B")
        deducted_a = round(balance_a_before - balance_a_after, 2) if balance_a_after is not None else 0
        deducted_b = round(balance_b_before - balance_b_after, 2) if balance_b_after is not None else 0
        total_deducted = round(deducted_a + deducted_b, 2)
        info(f"  余额变动:")
        info(f"    A: {balance_a_before} -> {balance_a_after}, 扣减={deducted_a}元")
        info(f"    B: {balance_b_before} -> {balance_b_after}, 扣减={deducted_b}元")
        info(f"    总扣款={total_deducted}元, 应付={round(total_amount, 2)}元")

        bug_found = False
        if len(success_pays) > 1:
            info(f"  ❌ Bug复现! 支付记录有{len(success_pays)}笔成功!")
            bug_found = True
        elif success_count > 1:
            info(f"   Bug复现! submit 成功{success_count}次!")
            bug_found = True

        if bug_found:
            raise FlowError("并发扣款Bug复现!")
        else:
            info(f"  ✓ 正常: 支付记录{len(success_pays)}笔, submit成功{success_count}次")

    finally:
        _cleanup_resources(api_client, token, region_id, fee_id, desk_id)
