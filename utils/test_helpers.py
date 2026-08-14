# -*- coding: utf-8 -*-
"""
测试资源公共辅助函数（统一）
==========================
灯控测试和支付测试共用同一套资源管理逻辑：
- 动态名称生成（时间戳 + 随机后缀，每次调用时生成，避免同名冲突）
- 资源创建/验证/清理（region → fee → desk）
- 轮询等待（资源创建后系统调度同步）
- 开台/关台封装

命名规则：统一使用 config.payment_test 中的 base_name 前缀。
"""

import json
import os
import random
import time
from datetime import datetime

from utils.config import config
from utils.debug_utils import info
from utils.log_control import WARNING
from core.api_client import find_by_name

# ================================================================
#  配置常量
# ================================================================

_biz = config.business_data
_pt = config.payment_test

STORE_NO = _biz["storeNo"]
MERCHANT_NO = _biz.get("merchantNo", "")

# 名称前缀（从 config 读取，灯控和支付共用）
REGION_NAME_PREFIX = _pt['region']['base_name']   # "测试区"
FEE_NAME_PREFIX = _pt['fee']['base_name']          # "测试费"
DESK_NAME_PREFIX = _pt['desk']['base_name']        # "测试桌台"

# 台费模板参数
FEE_PRICE = _pt['fee']['price']
FEE_TIME = _pt['fee']['time']
MAX_PAUSE_TIME = _pt['fee']['max_pause_time']
MIN_PAUSE_INTERVAL = _pt['fee']['min_pause_interval']
MIN_TIME = _pt['fee']['min_time']
CAN_PAUSE = _pt['fee']['can_pause']
LOW_CONSUME_TYPE = _pt['fee']['low_consume_type']
UNIT_TIME = _pt['fee']['unit_time']
OVER_UNIT_TIME = _pt['fee']['over_unit_time']

# 桌台模板参数
DESK_TYPE = _pt['desk']['type']
DESK_STATUS_INIT = _pt['desk']['status']
USER_DISCOUNT = _pt['desk'].get('user_discount', 100)
CAN_CLOCK = _pt['desk'].get('can_clock', 1)
CLOCK_CASHIER = _pt['desk'].get('clock_cashier', 1)
CLOCK_MINI_PROGRAM = _pt['desk'].get('clock_mini_program', 1)
IS_SYNC_SETTING = _pt['desk'].get('is_sync_setting', "1")
IS_CLOSE = _pt['desk'].get('is_close', 0)
IS_ACCOUNT = _pt['desk'].get('is_account', 0)
IS_ORDER = _pt['desk'].get('is_order', 0)
IS_STAND = _pt['desk'].get('is_stand', 0)
IS_RESERVE = _pt['desk'].get('is_reserve', 0)
ACTIVE_KEY = _pt['desk'].get('active_key', 1)
CAN_BALANCE = _pt['desk'].get('can_balance', 1)

# 轮询配置（稳定性测试连续执行时服务端同步较慢，需要更长等待）
_POLL_CFG = _pt.get('polling', {})
POLL_INITIAL_WAIT = _POLL_CFG.get('initial_wait', 8)
POLL_INTERVAL = _POLL_CFG.get('interval', 3)
POLL_MAX_ATTEMPTS = _POLL_CFG.get('max_attempts', 8)
POLL_TIMEOUT = _POLL_CFG.get('timeout', 35)


# ================================================================
#  异常类
# ================================================================

class TestFlowError(Exception):
    """测试流程异常（灯控和支付共用）"""
    pass


# ================================================================
#  动态名称
# ================================================================

def _gen_suffix():
    """生成唯一后缀（6位时间戳 + 2位随机 + worker ID），控制总长度"""
    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")[-1]
    return datetime.now().strftime("%H%M%S") + str(random.randint(10, 99)) + worker


# ================================================================
#  轮询工具
# ================================================================

def poll_until_found(query_fn, name, description="资源"):
    """
    轮询查询直到找到目标资源。

    流程：先等待 POLL_INITIAL_WAIT 秒 → 调用 query_fn → 未找到则每隔 POLL_INTERVAL
    秒重试，最多重试 POLL_MAX_ATTEMPTS 次，总耗时不超过 POLL_TIMEOUT 秒。
    """
    start = time.time()

    info(f"  等待 {POLL_INITIAL_WAIT}s，等待系统调度同步...")
    time.sleep(POLL_INITIAL_WAIT)

    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        elapsed = time.time() - start
        if elapsed > POLL_TIMEOUT:
            raise TestFlowError(
                f"{description}轮询超时: {name}，已等待 {elapsed:.0f}s "
                f"(超过 {POLL_TIMEOUT}s 限制)"
            )

        info(f"  轮询 {attempt}/{POLL_MAX_ATTEMPTS}: 查找{description} {name}...")
        result = query_fn()

        if result:
            return result

        info(f"      未找到，{POLL_INTERVAL}s 后重试...")
        time.sleep(POLL_INTERVAL)

    raise TestFlowError(
        f"{description}轮询失败: {name}，已重试 {POLL_MAX_ATTEMPTS} 次"
    )


# ================================================================
#  资源创建函数
# ================================================================

def create_region(api_client, token, merchant_no=None, name=None):
    """创建区域，返回 region_id"""
    _name = name or f"{REGION_NAME_PREFIX}_{_gen_suffix()}"
    _merchant = merchant_no or MERCHANT_NO
    payload = {
        "regionName": _name,
        "regionSort": 1,
        "regionStatus": 1,
        "regionType": "1",
        "storeNo": STORE_NO,
        "merchantNo": _merchant,
    }
    info(f"  新增区域... 名称: {_name}")
    response = api_client.post(
        "/merchant-api/store/desk/region/create", payload, token, "新增区域"
    )
    region_id = response.get_data()
    info(f"      区域创建成功! ID={region_id}")
    return region_id


def verify_region(api_client, token, name):
    """查询校验区域，返回 region_no"""
    response = api_client.post(
        "/merchant-api/store/desk/region/list",
        {"filter": {"storeNo": STORE_NO}}, token, "查询区域"
    )
    region_list = response.get_data(default=[])
    region = find_by_name(region_list, "regionName", name)
    if not region:
        raise TestFlowError(f"未找到区域: {name}")
    region_no = region.get("regionNo", "")
    info(f"      区域校验通过! regionNo={region_no}")
    return region_no


def create_fee(api_client, token, merchant_no=None, name=None):
    """创建台费，返回 fee_id"""
    _name = name or f"{FEE_NAME_PREFIX}_{_gen_suffix()}"
    _merchant = merchant_no or MERCHANT_NO
    payload = {
        "feeStatus": "1",
        "feePrice": FEE_PRICE,
        "maxPauseTime": MAX_PAUSE_TIME,
        "minTime": MIN_TIME,
        "feeName": _name,
        "minPauseInterval": MIN_PAUSE_INTERVAL,
        "feeTime": FEE_TIME,
        "merchantNo": _merchant,
        "weekRuleVO": {"rules": []},
        "dayRuleVO": {"rules": []},
        "isOpen": True,
        "canPause": CAN_PAUSE,
        "unitTime": UNIT_TIME,
        "overUnitTime": OVER_UNIT_TIME,
        "lowConsumeType": LOW_CONSUME_TYPE,
        "lowConsumeTime": "",
        "lowConsumeTraining": "",
        "trainingRuleVO": {"type": 0, "discount": "", "price": ""},
        "storeNo": STORE_NO,
        "filter": {"storeNo": STORE_NO},
    }
    info(f"  新增台费... 名称: {_name}, 价格: {FEE_PRICE}元/{FEE_TIME}分钟")
    response = api_client.post(
        "/merchant-api/store/desk/fee/create", payload, token, "新增台费"
    )
    fee_id = response.get_data()
    info(f"      台费创建成功! ID={fee_id}")
    return fee_id


def verify_fee(api_client, token, name):
    """查询校验台费，返回 (fee_no, fee_id)"""
    payload = {"filter": {"storeNo": STORE_NO}, "pageNo": 1, "pageSize": 10}
    response = api_client.post(
        "/merchant-api/store/desk/fee/page", payload, token, "查询台费"
    )
    fee_list = response.get_data("list", default=[])
    fee = find_by_name(fee_list, "feeName", name)
    if not fee:
        raise TestFlowError(f"未找到台费: {name}")
    fee_no = fee.get("feeNo", "")
    fee_id = fee.get("id")
    info(f"      台费校验通过! feeNo={fee_no}, ID={fee_id}")
    return fee_no, fee_id


def create_desk(api_client, token, region_no, fee_no, fee_name, desk_name=None, index=1):
    """
    创建桌台，返回 desk_id。

    Args:
        index: 桌台序号（1-based），用于随机抖动避免并行冲突
        desk_name: 桌台名称（可选，不传则自动生成）
    """
    if desk_name is None:
        desk_name = f"{DESK_NAME_PREFIX}_{_gen_suffix()}_{index}"

    # 随机抖动 1-3 秒，避免并行时同时请求导致"更新额度失败"
    time.sleep(random.uniform(1, 3))

    payload = {
        "isSyncSetting": IS_SYNC_SETTING,
        "isClose": IS_CLOSE,
        "deskType": DESK_TYPE,
        "isAccount": IS_ACCOUNT,
        "deviceNo": None,
        "deviceName": "",
        "feeNo": fee_no,
        "deviceSn": None,
        "deviceRoute": None,
        "userDiscount": USER_DISCOUNT,
        "userDiscountShow": USER_DISCOUNT,
        "canClock": CAN_CLOCK,
        "clockCashier": CLOCK_CASHIER,
        "clockMiniProgram": CLOCK_MINI_PROGRAM,
        "deskStatus": DESK_STATUS_INIT,
        "regionNo": region_no,
        "storeNo": STORE_NO,
        "deskName": desk_name,
        "isOrder": IS_ORDER,
        "isStand": IS_STAND,
        "activeKey": ACTIVE_KEY,
        "powerfulDevice": {},
        "canBalance": CAN_BALANCE,
        "feeFeeName": fee_name,
        "isReserve": IS_RESERVE,
        "filter": {"storeNo": STORE_NO},
    }
    info(f"  新增桌台... 名称: {desk_name}")
    response = api_client.post(
        "/merchant-api/store/desk/create", payload, token, f"新增桌台{index}"
    )
    desk_id = response.get_data()
    info(f"      桌台{index}创建成功! ID={desk_id}")
    return desk_id


def verify_desk(api_client, token, name):
    """查询校验桌台，返回 (desk_no, desk_id)"""
    payload = {
        "filter": {"storeNo": STORE_NO, "deskName": name},
        "op": {"deskName": "LIKE"},
    }
    response = api_client.post(
        "/merchant-api/store/desk/list", payload, token, "查询桌台"
    )
    desk_list = response.get_data(default=[])
    desk = find_by_name(desk_list, "deskName", name)
    if not desk:
        raise TestFlowError(f"未找到桌台: {name}")
    desk_no = desk.get("deskNo", "")
    desk_id = desk.get("id")
    info(f"      桌台校验通过! deskNo={desk_no}, ID={desk_id}")
    return desk_no, desk_id


def verify_desk_idle(api_client, token, name):
    """listV3 校验桌台空闲（轮询直到找到）"""
    payload = {
        "filter": {"storeNo": STORE_NO, "deskName": name},
        "storeNo": STORE_NO,
        "statusList": [1, 2, 3, 5],
        "pageNo": 1,
        "pageSize": 50,
    }

    def _query():
        response = api_client.post(
            "/merchant-api/store/desk/listV3", payload, token, "listV3"
        )
        desk_list = response.get_data(default=[])
        return find_by_name(desk_list, "deskName", name)

    desk = poll_until_found(_query, name, description="桌台")
    status = desk.get("deskStatus")
    if status == "3":
        info(f"      桌台状态校验通过! 状态=3(关闭), 空闲无订单")
    elif status == "2":
        info(f"      桌台已开台，先执行关台...")
        close_desk(api_client, token, desk.get("orderNo"))
        time.sleep(2)
    else:
        raise TestFlowError(f"桌台状态异常! status={status}")
    return desk


# ================================================================
#  清理函数
# ================================================================

def cleanup_desk(api_client, token, desk_id, strict=False):
    """删除桌台"""
    if not desk_id:
        return
    info(f"  清理桌台: ID={desk_id}")
    try:
        api_client.post(
            "/merchant-api/store/desk/del",
            {"ids": [desk_id]},
            token=token, step_name="删除测试桌台", strict=strict
        )
        info(f"      桌台已删除")
    except Exception as e:
        WARNING.logger.warning(f"      清理桌台失败: {e}")


def cleanup_fee(api_client, token, fee_id, strict=False):
    """删除台费"""
    if not fee_id:
        return
    info(f"  清理台费: ID={fee_id}")
    try:
        api_client.post(
            "/merchant-api/store/desk/fee/del",
            {"ids": [fee_id]},
            token=token, step_name="删除测试台费", strict=strict
        )
        info(f"      台费已删除")
    except Exception as e:
        WARNING.logger.warning(f"      清理台费失败: {e}")


def cleanup_region(api_client, token, region_id, strict=False):
    """删除区域"""
    if not region_id:
        return
    info(f"  清理区域: ID={region_id}")
    try:
        api_client.post(
            "/merchant-api/store/desk/region/del",
            {"ids": [region_id]},
            token=token, step_name="删除测试区域", strict=strict
        )
        info(f"      区域已删除")
    except Exception as e:
        WARNING.logger.warning(f"      清理区域失败: {e}")


# ================================================================
#  开台/关台封装
# ================================================================

def open_clock(api_client, token, desk_no):
    """计时开台，返回 order_no"""
    info(f"  计时开台... deskNo={desk_no}")
    response = api_client.post(
        "/merchant-api/store/desk/orders/createClockOpen",
        {"deskNo": desk_no, "filter": {"storeNo": STORE_NO}},
        token, "计时开台"
    )
    order_no = response.get_data()
    if isinstance(order_no, dict):
        order_no = order_no.get("orderNo", order_no)
    info(f"      开台成功! orderNo={order_no}")
    return order_no


def close_desk(api_client, token, order_no, close=True):
    """关台"""
    info(f"  关台... orderNo={order_no}, close={close}")
    response = api_client.post(
        "/merchant-api/store/desk/orders/closeDesk",
        {
            "orderNo": order_no,
            "close": close,
            "filter": {"storeNo": STORE_NO},
        },
        token, "关台"
    )
    info(f"      关台成功!")
    return response


# ================================================================
#  会员查询
# ================================================================

def get_golfer_no(api_client, token, phone):
    """
    根据手机号查询会员，返回 golferNo

    Args:
        api_client: API 客户端
        token: 登录 token
        phone: 会员手机号

    Returns:
        golferNo: 会员编号（查询失败返回 None）
    """
    info(f"  查询会员... phone={phone}")
    response = api_client.post(
        "/merchant-api/store/golfer/pageV2",
        {
            "storeNo": STORE_NO,
            "pageNo": 1,
            "pageSize": 10,
            "searchName": phone,
            "filter": {"storeNo": STORE_NO}
        },
        token, "查询会员"
    )
    data = response.get_data(default={})
    member_list = data.get("list", []) if isinstance(data, dict) else []
    if member_list:
        golfer_no = member_list[0].get("golferNo")
        golfer_name = member_list[0].get("golferName", "")
        info(f"      查询成功! golferNo={golfer_no}, name={golfer_name}")
        return golfer_no
    info(f"      未找到会员: {phone}")
    return None


# ================================================================
#  一键创建/清理（fixture 使用）
# ================================================================

def create_test_resources(api_client, token):
    """
    一键创建完整资源链：region → fee → desk（单桌台）
    返回 dict: {region_id, region_no, region_name, fee_id, fee_no, fee_name,
                desk_id, desk_no, desk_name}
    """
    suffix = _gen_suffix()
    region_name = f"{REGION_NAME_PREFIX}_{suffix}"
    fee_name = f"{FEE_NAME_PREFIX}_{suffix}"
    desk_name = f"{DESK_NAME_PREFIX}_{suffix}_1"

    # 1. 创建区域
    region_id = create_region(api_client, token, name=region_name)
    region_no = verify_region(api_client, token, name=region_name)

    # 2. 创建台费
    fee_id = create_fee(api_client, token, name=fee_name)
    fee_no, _ = verify_fee(api_client, token, name=fee_name)

    # 3. 创建桌台
    desk_id = create_desk(api_client, token, region_no, fee_no,
                          fee_name=fee_name, desk_name=desk_name)
    desk_no, _ = verify_desk(api_client, token, name=desk_name)

    # 4. 校验桌台空闲
    verify_desk_idle(api_client, token, name=desk_name)

    return {
        "region_id": region_id,
        "region_no": region_no,
        "region_name": region_name,
        "fee_id": fee_id,
        "fee_no": fee_no,
        "fee_name": fee_name,
        "desk_id": desk_id,
        "desk_no": desk_no,
        "desk_name": desk_name,
    }


def create_test_resources_2(api_client, token):
    """
    一键创建双桌台资源：region → fee → desk1 + desk2
    返回 dict: {region_id, region_no, region_name,
                fee_id, fee_no, fee_name,
                desk1_id, desk1_no, desk1_name,
                desk2_id, desk2_no, desk2_name}

    两个桌台绑定同一个台费（与手动操作一致）
    """
    suffix = _gen_suffix()
    region_name = f"{REGION_NAME_PREFIX}_{suffix}"
    fee_name = f"{FEE_NAME_PREFIX}_{suffix}"
    desk1_name = f"{DESK_NAME_PREFIX}_{suffix}_1"
    desk2_name = f"{DESK_NAME_PREFIX}_{suffix}_2"

    # 1. 创建区域
    region_id = create_region(api_client, token, name=region_name)
    region_no = verify_region(api_client, token, name=region_name)

    # 2. 创建一个台费（两个桌台共用）
    fee_id = create_fee(api_client, token, name=fee_name)
    fee_no, _ = verify_fee(api_client, token, name=fee_name)

    # 3. 创建桌台1
    desk1_id = create_desk(api_client, token, region_no, fee_no,
                           fee_name=fee_name, desk_name=desk1_name, index=1)
    desk1_no, _ = verify_desk(api_client, token, name=desk1_name)
    verify_desk_idle(api_client, token, name=desk1_name)

    # 4. 创建桌台2
    desk2_id = create_desk(api_client, token, region_no, fee_no,
                           fee_name=fee_name, desk_name=desk2_name, index=2)
    desk2_no, _ = verify_desk(api_client, token, name=desk2_name)
    verify_desk_idle(api_client, token, name=desk2_name)

    return {
        "region_id": region_id,
        "region_no": region_no,
        "region_name": region_name,
        "fee_id": fee_id,
        "fee_no": fee_no,
        "fee_name": fee_name,
        "desk1_id": desk1_id,
        "desk1_no": desk1_no,
        "desk1_name": desk1_name,
        "desk2_id": desk2_id,
        "desk2_no": desk2_no,
        "desk2_name": desk2_name,
    }


def cleanup_test_resources(api_client, token, resources):
    """逆序清理资源：desk → fee → region（支持单桌台和双桌台）"""
    # 支持 desk_id（单桌台）和 desk1_id（双桌台）两种键名
    desk_id = resources.get("desk_id") or resources.get("desk1_id")
    cleanup_desk(api_client, token, desk_id)
    if "desk2_id" in resources:
        cleanup_desk(api_client, token, resources.get("desk2_id"))

    # 支持单台费（fee_id）和双台费（fee1_id, fee2_id）
    if "fee_id" in resources:
        cleanup_fee(api_client, token, resources.get("fee_id"))
    if "fee1_id" in resources:
        cleanup_fee(api_client, token, resources.get("fee1_id"))
    if "fee2_id" in resources:
        cleanup_fee(api_client, token, resources.get("fee2_id"))

    cleanup_region(api_client, token, resources.get("region_id"))
