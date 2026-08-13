# -*- coding: utf-8 -*-
"""
定时开关台测试
============
测试定时开台 → 自动关台流程，以及定时中重复开台的异常场景

测试场景：
1. 1 分钟定时开台 → 等待自动关台
2. 3 分钟定时开台 → 等待自动关台
3. 1 小时定时开台 → 等待自动关台
4. 异常场景：定时开台 1 分钟 → 等待 55 秒 → 重复开台 → 验证报错

业务流程（正常）:
  前置资源创建(region → fee → desk) → 验证桌台空闲(status=3)
  → 定时开台(createClockOpen + hour) → 验证桌台使用中(status=2)
  → 等待定时器到期 → 验证桌台自动关闭(status=3)
  → 自动清理资源(desk → fee → region)

业务流程（异常）:
  前置资源创建 → 定时开台 1 分钟 → 等待 55 秒
  → 重复开台 → 验证报错（code != 200）
  → 等待定时器到期 → 自动清理资源

接口清单:
  - POST /merchant-api/store/desk/orders/createClockOpen  定时开台
  - POST /merchant-api/store/desk/listV3                  查询桌台状态（系统调度接口）
  - POST /merchant-api/store/desk/orders/closeDesk         关台

自动化改造：
- 自动创建区域/台费/桌台（fixture teardown 自动清理）
- 开台后验证采用 "硬性等待 + 轮询" 组合模式（listV3 为系统调度接口）
- 不再依赖 config.yaml 中的预配桌台数据
"""

import time

import pytest

from core.assertions import assert_response
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority
from utils.test_helpers import POLL_INITIAL_WAIT, POLL_INTERVAL


# ================================================================
#  参数化数据
# ================================================================

TIMED_CLOCK_CASES = [
    # (hour, label, max_deviation)
    pytest.param(0.0167, "1分钟", 15, id="1min"),       # 1min + 15s
    pytest.param(0.05, "3分钟", 20, id="3min"),         # 3min + 20s
    pytest.param(1.0, "1小时", 30, id="1hour"),        # 1hour + 30s
]


# ================================================================
#  参数化测试（1min / 3min / 1hour）
# ================================================================

@pytest.mark.regression
@pytest.mark.lighting
@mark_priority(1)
@capture_failure
@pytest.mark.parametrize("hour,label,max_deviation", TIMED_CLOCK_CASES)
def test_timed_clock_open(api_client, auth_context, lighting_resources, hour, label, max_deviation):
    """
    定时开台 → 等待自动关台

    测试步骤：
    1. 自动创建区域/台费/桌台（fixture）
    2. 验证桌台空闲（deskStatus=3）
    3. 定时开台（createClockOpen + hour 参数）
    4. 验证桌台使用中（deskStatus=2）
    5. 等待定时器到期，轮询验证桌台自动关闭（deskStatus=3）
    6. 自动清理资源（fixture teardown）

    验证点：
    - 开台响应 code == 200, data 非空（返回 orderNo）
    - 开台后桌台状态 = 2（使用中）
    - 定时到期后桌台状态 = 3（自动关闭）
    - 实际耗时 <= 定时时长 + 最大偏差阈值
    """
    token = auth_context.token
    store_no = auth_context.store_no
    desk_no = lighting_resources['desk_no']
    desk_name = lighting_resources['desk_name']
    expected_seconds = int(hour * 3600)
    timeout_sec = expected_seconds + max_deviation

    # Arrange（准备）：验证桌台空闲
    info(f"测试参数: hour={hour}, label={label}, max_deviation={max_deviation}s, desk_no={desk_no}")
    response = api_client.post(
        "/merchant-api/store/desk/listV3",
        {
            "filter": {"storeNo": store_no, "deskName": desk_name},
            "storeNo": store_no,
            "statusList": [1, 2, 3, 5],
        },
        token, "验证桌台空闲"
    )
    desk_list = response.get_data(default=[])
    desk_info = next((d for d in desk_list if d.get("deskName") == desk_name), None)
    assert desk_info is not None, f"未找到桌台: {desk_name}"
    assert str(desk_info.get("deskStatus")) == "3", \
        f"开台前桌台状态异常! 期望=3(空闲), 实际={desk_info.get('deskStatus')}"

    # Act（执行）：定时开台（记录开台时刻，用于计算实际耗时）
    info(f"定时开台... hour={hour}")
    open_time = time.time()
    response = api_client.post(
        "/merchant-api/store/desk/orders/createClockOpen",
        {
            "deskNo": desk_no,
            "hour": hour,
            "filter": {"storeNo": store_no}
        },
        token, f"定时开台-{label}"
    )

    # Assert（断言）：开台响应
    assert_response(response).code_is(200).data_is_not_null().validate()
    order_no = response.get_data()
    info(f"      定时开台成功! orderNo={order_no}")

    # 验证桌台使用中（硬性等待 + 轮询，listV3 为系统调度接口）
    info(f"等待 {POLL_INITIAL_WAIT}s，等待系统调度同步...")
    time.sleep(POLL_INITIAL_WAIT)
    response = api_client.post(
        "/merchant-api/store/desk/listV3",
        {
            "filter": {"storeNo": store_no, "deskName": desk_name},
            "storeNo": store_no,
            "statusList": [1, 2, 3, 5],
        },
        token, "验证桌台使用中"
    )
    desk_list = response.get_data(default=[])
    desk_info = next((d for d in desk_list if d.get("deskName") == desk_name), None)
    assert desk_info is not None, f"开台后未找到桌台: {desk_name}"
    assert str(desk_info.get("deskStatus")) == "2", \
        f"开台后桌台状态异常! 期望=2(使用中), 实际={desk_info.get('deskStatus')}"

    # 等待自动关台（轮询直到 deskStatus="3" 或超时）
    info(f"等待自动关台... 期望: {expected_seconds}s, 最大偏差: {max_deviation}s, 超时: {timeout_sec}s")
    auto_closed = False

    while time.time() - open_time < timeout_sec:
        time.sleep(POLL_INTERVAL)
        elapsed = int(time.time() - open_time)

        response = api_client.post(
            "/merchant-api/store/desk/listV3",
            {
                "filter": {"storeNo": store_no, "deskName": desk_name},
                "storeNo": store_no,
                "statusList": [1, 2, 3, 5],
            },
            token, f"轮询桌台状态-{elapsed}s"
        )
        desk_list = response.get_data(default=[])
        desk_info = next((d for d in desk_list if d.get("deskName") == desk_name), None)

        if desk_info:
            current_status = str(desk_info.get("deskStatus"))
            info(f"      [{elapsed}s] deskStatus={current_status}")

            if current_status == "3":
                auto_closed = True
                break

    # 结果判定
    actual_duration = int(time.time() - open_time)
    deviation = actual_duration - expected_seconds

    if auto_closed:
        info(f"      桌台已自动关闭! 实际耗时: {actual_duration}s, 偏差: +{deviation}s (阈值: {max_deviation}s)")
        info(f"      [桌台信息] desk_no={desk_no}, desk_name={desk_name}, order_no={order_no}")
        assert actual_duration <= timeout_sec, \
            f"定时偏差超标! 期望={expected_seconds}s, 实际={actual_duration}s, " \
            f"偏差=+{deviation}s, 阈值=+{max_deviation}s"
        info(f"定时开台 [{label}] 测试通过")
    else:
        info(f"      ⚠ 桌台未自动关闭! 已等待 {actual_duration}s")
        info(f"      [排查信息] desk_no={desk_no}, desk_name={desk_name}, "
             f"order_no={order_no}, store_no={store_no}")
        assert False, \
            f"定时关台失败! 已等待 {actual_duration}s, 桌台未自动关闭"


# ================================================================
#  异常场景
# ================================================================

@pytest.mark.regression
@pytest.mark.lighting
@mark_priority(1)
@capture_failure
def test_duplicate_open_error(api_client, auth_context, lighting_resources):
    """
    定时开台 → 等待55秒 → 重复开台 → 验证报错

    测试步骤：
    1. 自动创建区域/台费/桌台（fixture）
    2. 定时开台（1 分钟）
    3. 等待 55 秒（定时器仍在计时中）
    4. 再次调用开台接口
    5. 验证报错响应（code != 200）
    6. 等待定时器到期，桌台自动关闭
    7. 自动清理资源（fixture teardown）

    验证点：
    - 首次开台响应 code == 200
    - 重复开台响应 code != 200（报错）
    """
    token = auth_context.token
    store_no = auth_context.store_no
    desk_no = lighting_resources['desk_no']

    # 1. 定时开台（1 分钟）
    info("定时开台(异常场景前置)... hour=0.0167")
    response = api_client.post(
        "/merchant-api/store/desk/orders/createClockOpen",
        {
            "deskNo": desk_no,
            "hour": 0.0167,
            "filter": {"storeNo": store_no}
        },
        token, "定时开台-异常前置"
    )
    assert_response(response).code_is(200).data_is_not_null().validate()
    order_no = response.get_data()
    info(f"      定时开台成功! orderNo={order_no}")

    # 2. 等待 55 秒（定时器仍在计时中）
    info("等待55秒...")
    time.sleep(55)

    # 3. 再次调用开台接口（预期报错）
    info("重复开台(预期报错)...")
    response = api_client.post(
        "/merchant-api/store/desk/orders/createClockOpen",
        {
            "deskNo": desk_no,
            "hour": 0.0167,
            "filter": {"storeNo": store_no}
        },
        token, "重复开台-预期报错",
        strict=False
    )

    # 4. 验证报错响应
    error_code = response.get("code")
    error_msg = response.get("msg", "")
    info(f"      重复开台响应: code={error_code}, msg={error_msg}")
    assert error_code != 200, \
        f"重复开台预期报错但成功了! code={error_code}, msg={error_msg}"
    info(f"      重复开台报错正常! code={error_code}, msg={error_msg}")

    # 5. 等待定时器到期（确保 fixture 能正常清理）
    info("等待定时器到期...")
    start_time = time.time()
    while time.time() - start_time < 80:
        time.sleep(POLL_INTERVAL)
        elapsed = int(time.time() - start_time)

        response = api_client.post(
            "/merchant-api/store/desk/listV3",
            {
                "filter": {"storeNo": store_no,
                           "deskName": lighting_resources['desk_name']},
                "storeNo": store_no,
                "statusList": [1, 2, 3, 5],
            },
            token, f"等待自动关台-{elapsed}s"
        )
        desk_list = response.get_data(default=[])
        desk_info = next(
            (d for d in desk_list
             if d.get("deskName") == lighting_resources['desk_name']),
            None
        )
        if desk_info and str(desk_info.get("deskStatus")) == "3":
            info(f"      桌台已自动关闭! 耗时 {elapsed}s")
            break

    info("重复开台异常测试通过")
