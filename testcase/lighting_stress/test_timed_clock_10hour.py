# -*- coding: utf-8 -*-
"""
10 小时定时开台压测（20 张桌台）
==============================
独立于常规灯控测试，单独文件存放。

测试步骤：
1. 手动创建区域 → 台费 → 20 张桌台
2. 记录全部 20 张桌台的 desk_no / desk_name 到日志（方便排查数据库）
3. 逐张定时开台（hour=10.0）
4. 轮询等待全部桌台自动关台（每 5 分钟检查一次）
5. 手动清理全部资源

运行方式：
    # 单独运行（约 10 小时）
    pytest testcase/lighting_stress/test_timed_clock_10hour.py

    # 后台运行 + 日志输出
    nohup pytest testcase/lighting_stress/test_timed_clock_10hour.py \
        > logs/stress_test.log 2>&1 &
"""

import time

import pytest

from core.assertions import assert_response
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority
from utils.test_helpers import (
    POLL_INITIAL_WAIT,
    create_region, verify_region,
    create_fee, verify_fee,
    create_desk, verify_desk,
    cleanup_desk, cleanup_fee, cleanup_region,
    REGION_NAME_PREFIX, FEE_NAME_PREFIX, DESK_NAME_PREFIX,
    _gen_suffix,
)


@pytest.mark.regression
@pytest.mark.lighting
@mark_priority(2)
@capture_failure
def test_timed_clock_10hour_stress(api_client, auth_context):
    """
    10 小时定时开台压测（20 张桌台）

    测试步骤：
    1. 手动创建区域 → 台费 → 20 张桌台
    2. 记录全部 20 张桌台的 desk_no / desk_name 到日志（方便排查数据库）
    3. 逐张定时开台（hour=10.0）
    4. 轮询等待全部桌台自动关台（每 5 分钟检查一次）
    5. 手动清理全部资源

    验证点：
    - 20 张桌台全部定时开台成功
    - 全部桌台在 10 小时 + 60s 偏差内自动关台
    """
    token = auth_context.token
    store_no = auth_context.store_no
    merchant_no = auth_context.merchant_no
    desk_count = 20
    hour = 10.0
    max_deviation = 60
    expected_seconds = int(hour * 3600)
    timeout_sec = expected_seconds + max_deviation
    poll_interval = 300  # 压测场景每 5 分钟查一次，减少 API 调用

    region_id = None
    fee_id = None
    created_desks = []  # [{desk_id, desk_no, desk_name, order_no}, ...]

    try:
        # ── Arrange（准备）：手动创建区域 → 台费 → 20 张桌台 ─
        info(f"{'=' * 60}")
        info(f"  10 小时压测 - 创建 {desk_count} 张桌台")
        info(f"{'=' * 60}")

        # 1. 生成唯一后缀 + 资源名称
        suffix = _gen_suffix()
        region_name = f"{REGION_NAME_PREFIX}_{suffix}"
        fee_name = f"{FEE_NAME_PREFIX}_{suffix}"

        # 2. 创建区域
        region_id = create_region(api_client, token, name=region_name)
        region_no = verify_region(api_client, token, name=region_name)

        # 3. 创建台费
        fee_id = create_fee(api_client, token, name=fee_name)
        fee_no, _ = verify_fee(api_client, token, name=fee_name)

        # 4. 批量创建 20 张桌台
        info(f"  批量创建 {desk_count} 张桌台...")
        for i in range(1, desk_count + 1):
            desk_name = f"{DESK_NAME_PREFIX}_{suffix}_{i}"
            desk_id = create_desk(api_client, token, region_no, fee_no,
                                  fee_name=fee_name, desk_name=desk_name, index=i)
            desk_no, _ = verify_desk(api_client, token, name=desk_name)
            created_desks.append({
                "desk_id": desk_id,
                "desk_no": desk_no,
                "desk_name": desk_name,
                "order_no": None,
            })

        # 5. 记录全部桌台信息到日志（方便排查数据库）
        info(f"{'=' * 60}")
        info(f"  全部桌台信息（共 {desk_count} 张，方便排查数据库）:")
        info(f"  store_no={store_no}, merchant_no={merchant_no}")
        info(f"  region_name={region_name}, region_no={region_no}, region_id={region_id}")
        info(f"  fee_name={fee_name}, fee_no={fee_no}, fee_id={fee_id}")
        info(f"{'─' * 60}")
        for i, desk in enumerate(created_desks, 1):
            info(f"  [{i:2d}] desk_no={desk['desk_no']}, "
                 f"desk_name={desk['desk_name']}, desk_id={desk['desk_id']}")
        info(f"{'=' * 60}")

        # ── Act（执行）：逐张定时开台 ──
        info(f"  开始逐张定时开台... hour={hour}")
        open_time = time.time()

        for i, desk in enumerate(created_desks, 1):
            response = api_client.post(
                "/merchant-api/store/desk/orders/createClockOpen",
                {
                    "deskNo": desk["desk_no"],
                    "hour": hour,
                    "filter": {"storeNo": store_no}
                },
                token, f"定时开台-{i}/{desk_count}"
            )
            assert_response(response).code_is(200).data_is_not_null().validate()
            desk["order_no"] = response.get_data()
            info(f"      [{i:2d}/{desk_count}] 开台成功! "
                 f"desk_name={desk['desk_name']}, order_no={desk['order_no']}")
            time.sleep(1)  # 间隔 1s，避免并发冲突

        info(f"  全部 {desk_count} 张桌台定时开台完成! "
             f"耗时: {int(time.time() - open_time)}s")

        # ── 等待全部自动关台 ──
        info(f"  等待全部桌台自动关台... 期望: {expected_seconds}s, "
             f"超时: {timeout_sec}s, 轮询间隔: {poll_interval}s")
        closed_desks = set()
        last_log_time = 0

        while time.time() - open_time < timeout_sec:
            time.sleep(poll_interval)
            elapsed = int(time.time() - open_time)

            # 查询全部桌台状态
            response = api_client.post(
                "/merchant-api/store/desk/listV3",
                {
                    "filter": {"storeNo": store_no},
                    "storeNo": store_no,
                    "statusList": [1, 2, 3, 5],
                },
                token, f"批量轮询-{elapsed}s"
            )
            all_desks = response.get_data(default=[])

            for desk in created_desks:
                if desk["desk_no"] in closed_desks:
                    continue
                desk_info = next(
                    (d for d in all_desks if d.get("deskNo") == desk["desk_no"]),
                    None
                )
                if desk_info and str(desk_info.get("deskStatus")) == "3":
                    closed_desks.add(desk["desk_no"])
                    info(f"      [{elapsed}s] 桌台已关闭: {desk['desk_name']} "
                         f"({len(closed_desks)}/{desk_count})")

            # 每 30 分钟输出一次进度
            if elapsed - last_log_time >= 1800:
                remaining = desk_count - len(closed_desks)
                info(f"      [{elapsed}s] 进度: {len(closed_desks)}/{desk_count} 已关闭, "
                     f"剩余 {remaining} 张")
                last_log_time = elapsed

            if len(closed_desks) == desk_count:
                break

        # ─ 结果判定 ──
        actual_duration = int(time.time() - open_time)
        deviation = actual_duration - expected_seconds

        if len(closed_desks) == desk_count:
            info(f"      全部 {desk_count} 张桌台已自动关闭! "
                 f"总耗时: {actual_duration}s, 偏差: +{deviation}s (阈值: {max_deviation}s)")
            assert actual_duration <= timeout_sec, \
                f"定时偏差超标! 期望={expected_seconds}s, 实际={actual_duration}s, " \
                f"偏差=+{deviation}s, 阈值=+{max_deviation}s"
            info(f"  10 小时压测 [{desk_count} 张桌台] 测试通过!")
        else:
            remaining = [d for d in created_desks if d["desk_no"] not in closed_desks]
            info(f"      ⚠ {len(remaining)}/{desk_count} 张桌台未自动关闭!")
            for d in remaining:
                info(f"      [未关闭] desk_no={d['desk_no']}, "
                     f"desk_name={d['desk_name']}, order_no={d['order_no']}")
            assert False, \
                f"定时关台失败! {len(remaining)}/{desk_count} 张桌台未自动关闭"

    finally:
        # ── 手动清理全部资源（逆序：desk → fee → region）──
        info(f"  开始清理资源...")
        for desk in created_desks:
            try:
                cleanup_desk(api_client, token, desk["desk_id"])
            except Exception as e:
                info(f"      清理桌台失败: {desk['desk_name']}, {e}")
        try:
            cleanup_fee(api_client, token, fee_id)
        except Exception as e:
            info(f"      清理台费失败: {e}")
        try:
            cleanup_region(api_client, token, region_id)
        except Exception as e:
            info(f"      清理区域失败: {e}")
        info(f"  资源清理完成")
