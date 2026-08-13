# -*- coding: utf-8 -*-
"""
灯控稳定性测试运行器
==================
多轮执行 lighting 目录下的测试用例，每轮进行数据库断言，
最终生成按轮次分组的 HTML 报告。

用法:
    python run_stability.py                     # 默认跑 3 轮
    python run_stability.py --rounds 10         # 跑 10 轮
    python run_stability.py --rounds 5 --dir testcase/lighting  # 指定目录
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

from utils.config import config
from utils.stability_db import (
    query_all_api_records,
    query_light_records,
    assert_light_records,
    get_light_summary,
)
from utils.stability_report import generate_html_report
from utils.debug_utils import info


# 门店编号（用于数据库查询过滤）
STORE_NO = config.business_data.get("storeNo", "344917")

# 结果文件路径（每轮写入，最后一轮读取生成报告）
RESULTS_DIR = "reports/stability"
RESULTS_FILE = os.path.join(RESULTS_DIR, "rounds_result.json")
HTML_REPORT = os.path.join(RESULTS_DIR, "stability_report.html")


def run_pytest_once(test_dir, round_num, total_rounds):
    """
    执行一轮 pytest 测试

    Returns:
        dict: 轮次数据（含 tests、start_time、end_time）
    """
    info(f"{'=' * 60}")
    info(f"  第 {round_num}/{total_rounds} 轮测试开始")
    info(f"{'=' * 60}")

    start_time = datetime.now()

    # 执行 pytest（-v 输出含每个用例耗时）
    cmd = [
        sys.executable, "-m", "pytest",
        test_dir,
        "-v",
        "--tb=short",
        f"--junitxml={RESULTS_DIR}/round_{round_num}.xml",
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout_lines = []
        for line in iter(process.stdout.readline, ""):
            line = line.rstrip("\n")
            if line:
                print(f"    {line}", flush=True)
                stdout_lines.append(line)
        process.wait(timeout=3600)
        stdout = "\n".join(stdout_lines)
    except subprocess.TimeoutExpired:
        info(f"  ⚠ 第 {round_num} 轮测试超时（超过 1 小时）")
        stdout = ""

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # 解析测试结果（优先 junitxml）
    junitxml_path = f"{RESULTS_DIR}/round_{round_num}.xml"
    tests = _parse_test_results(stdout, junitxml_path=junitxml_path)

    info(f"  第 {round_num} 轮测试完成: {len(tests)} 个用例, 耗时 {duration:.1f}s")
    for t in tests:
        status = "PASS" if t["passed"] else "FAIL"
        info(f"    [{status}] {t['name']} ({t['duration']:.2f}s)")

    return {
        "round_number": round_num,
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": duration,
        "tests": tests,
    }


def _parse_test_results(stdout, junitxml_path=None):
    """
    解析测试结果（优先 junitxml，fallback 解析 pytest 输出）

    Returns:
        list[dict]: [{"name": str, "passed": bool, "duration": float}, ...]
    """
    tests = []

    # 优先从 junitxml 解析（格式稳定，不受编码影响）
    if junitxml_path and os.path.exists(junitxml_path):
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(junitxml_path)
            root = tree.getroot()
            for tc in root.iter("testcase"):
                name = tc.get("name", "")
                classname = tc.get("classname", "")
                duration = float(tc.get("time", 0))
                # 检查是否有失败/错误子节点
                failed_elem = tc.find("failure")
                error_elem = tc.find("error")
                skipped = tc.find("skipped") is not None
                failed = failed_elem is not None or error_elem is not None

                # 提取失败原因
                failure_reason = ""
                if failed_elem is not None:
                    failure_reason = (failed_elem.get("message", "") + "\n" + (failed_elem.text or "")).strip()
                elif error_elem is not None:
                    failure_reason = (error_elem.get("message", "") + "\n" + (error_elem.text or "")).strip()

                # 简化名称：去掉模块路径，只保留 test_xxx[param]
                short_name = name
                tests.append({
                    "name": short_name,
                    "full_name": f"{classname}.{name}",
                    "passed": not failed and not skipped,
                    "status": "SKIPPED" if skipped else ("FAILED" if failed else "PASSED"),
                    "duration": duration,
                    "failure_reason": failure_reason,
                })
            if tests:
                return tests
        except Exception:
            pass

    # Fallback：解析 pytest -v 文本输出
    for line in stdout.split("\n"):
        line = line.strip()
        # 匹配: ...test_name PASSED (15.23s)  或  FAILED (2.10s)
        m = re.match(r"^(.+)\s+(PASSED|FAILED|SKIPPED)\s+\((\d+\.?\d*)s\)$", line)
        if not m:
            m2 = re.match(r"^(.+)\s+(PASSED|FAILED|SKIPPED)$", line)
            if m2:
                test_name = m2.group(1).strip()
                status = m2.group(2)
                short_name = test_name.split("::")[-1] if "::" in test_name else test_name
                tests.append({
                    "name": short_name,
                    "full_name": test_name,
                    "passed": status == "PASSED",
                    "status": status,
                    "duration": 0.0,
                    "failure_reason": "",
                })
            continue

        test_name = m.group(1).strip()
        status = m.group(2)
        duration = float(m.group(3))

        short_name = test_name.split("::")[-1] if "::" in test_name else test_name
        tests.append({
            "name": short_name,
            "full_name": test_name,
            "passed": status == "PASSED",
            "status": status,
            "duration": duration,
            "failure_reason": "",
        })

    return tests


def _distribute_api_records(api_records, tests, round_start_str):
    """
    按时间窗口把 API 记录分配到每个测试用例

    逻辑：根据 pytest 输出的用例耗时，计算每个用例的起止时间，
    然后把该时间段内的 API 记录归入对应用例。

    Args:
        api_records: 全部 API 记录（按时间升序）
        tests: 测试用例列表（按执行顺序，含 duration）
        round_start_str: 轮次开始时间 "YYYY-MM-DD HH:MM:SS"

    Returns:
        list[dict]: 每个测试用例增加 api_calls 字段
    """
    if not api_records or not tests:
        for t in tests:
            t["api_calls"] = []
        return tests

    # 解析轮次开始时间
    round_start = datetime.strptime(round_start_str, "%Y-%m-%d %H:%M:%S")

    # 计算每个用例的起止时间（基于 pytest 输出耗时）
    current_offset = 0.0
    for t in tests:
        t["_start_dt"] = round_start + __import__("datetime").timedelta(seconds=current_offset)
        current_offset += t["duration"]
        t["_end_dt"] = round_start + __import__("datetime").timedelta(seconds=current_offset)

    # 分配 API 记录到每个用例
    api_idx = 0
    for t in tests:
        t["api_calls"] = []
        t_start = t["_start_dt"]
        t_end = t["_end_dt"]

        while api_idx < len(api_records):
            rec = api_records[api_idx]
            rec_time_str = rec.get("create_time", "")
            try:
                rec_dt = datetime.strptime(rec_time_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                api_idx += 1
                continue

            # API 记录在用例时间窗口内
            if t_start <= rec_dt < t_end:
                t["api_calls"].append(rec)
                api_idx += 1
            elif rec_dt < t_start:
                # 记录在第一个用例之前，归入第一个用例
                if t == tests[0]:
                    t["api_calls"].append(rec)
                    api_idx += 1
                else:
                    api_idx += 1
            else:
                # 记录在当前用例之后，留给下一个用例
                break

    # 剩余记录归入最后一个用例
    while api_idx < len(api_records):
        tests[-1]["api_calls"].append(api_records[api_idx])
        api_idx += 1

    # 清理临时字段
    for t in tests:
        t.pop("_start_dt", None)
        t.pop("_end_dt", None)

    return tests


def run_db_assertion(round_data):
    """
    对一轮测试进行数据库断言

    Returns:
        dict: 更新后的 round_data
    """
    start_time = round_data["start_time"]
    end_time = round_data["end_time"]

    info(f"  数据库断言: 查询 {start_time} ~ {end_time} 的灯控记录...")

    # 1. 查询测试用例调用的所有 API
    api_records = query_all_api_records(start_time, end_time, store_no=STORE_NO)
    info(f"  API 调用: {len(api_records)} 条")

    # 2. 按用例分配 API 记录
    tests = round_data.get("tests", [])
    _distribute_api_records(api_records, tests, start_time)
    info(f"  API 分配完成: {len(tests)} 个用例")
    for t in tests:
        info(f"    {t['name']}: {len(t['api_calls'])} 条 API 调用")

    # 3. 查询灯控推送记录（数据库断言）
    records = query_light_records(start_time, end_time, store_no=STORE_NO)

    # 4. 数据库断言
    passed, success_records, message = assert_light_records(
        start_time, end_time, store_no=STORE_NO, expected_min_count=1
    )

    # 5. 统计摘要
    summary = get_light_summary(records)

    info(f"  {message}")
    if summary["by_operation"]:
        for op, stats in summary["by_operation"].items():
            info(f"    {op}: {stats['success']}/{stats['total']} 成功")

    round_data["api_records"] = api_records
    round_data["db_records"] = records
    round_data["db_assertion"] = {
        "passed": passed,
        "message": message,
    }
    round_data["db_summary"] = summary

    return round_data


def main():
    parser = argparse.ArgumentParser(description="灯控稳定性测试运行器")
    parser.add_argument(
        "--rounds", "-n",
        type=int,
        default=3,
        help="稳定性测试轮次（默认 3 轮）"
    )
    parser.add_argument(
        "--dir", "-d",
        type=str,
        default="testcase/lighting",
        help="测试目录（默认 testcase/lighting）"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=HTML_REPORT,
        help="HTML 报告输出路径"
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="从上次中断的轮次继续执行（读取 rounds_result.json）"
    )
    parser.add_argument(
        "--report-detail",
        type=int,
        default=10,
        help="报告中保留完整 API 明细的最近轮次数（默认 10，历史轮次只保留摘要）"
    )
    args = parser.parse_args()

    total_rounds = args.rounds
    test_dir = args.dir
    output_path = args.output
    resume = args.resume
    report_detail = args.report_detail

    info(f"{'=' * 60}")
    info(f"  灯控稳定性测试")
    info(f"  测试目录: {test_dir}")
    info(f"  测试轮次: {total_rounds}")
    info(f"  门店编号: {STORE_NO}")
    if resume:
        info(f"  恢复模式: 从断点继续")
    info(f"{'=' * 60}")

    # 确保结果目录存在
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # ── 恢复模式：读取已完成的轮次 ──
    rounds_data = []
    start_round = 1
    if resume and os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                rounds_data = json.load(f)
            start_round = len(rounds_data) + 1
            info(f"  已恢复 {len(rounds_data)} 轮历史数据，从第 {start_round} 轮继续")
        except (json.JSONDecodeError, Exception) as e:
            info(f"  ⚠ 恢复文件损坏，重新开始: {e}")
            rounds_data = []

    # ── 多轮执行 ─
    failed_rounds = []
    for i in range(start_round, total_rounds + 1):
        try:
            # 1. 执行一轮测试
            round_data = run_pytest_once(test_dir, i, total_rounds)

            # 2. 数据库断言 + API 分配
            round_data = run_db_assertion(round_data)

            rounds_data.append(round_data)

        except Exception as e:
            # 单轮失败不中断，记录失败信息后继续
            error_msg = str(e)[:200]
            info(f"  ⚠ 第 {i} 轮异常: {error_msg}")
            rounds_data.append({
                "round_number": i,
                "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": 0,
                "tests": [],
                "api_records": [],
                "db_records": [],
                "db_assertion": {"passed": False, "message": f"轮次执行异常: {error_msg}"},
                "db_summary": {"total": 0, "success": 0, "failed": 0, "by_operation": {}},
                "error": error_msg,
            })
            failed_rounds.append(i)

        # 3. 每轮完成后立即写入磁盘（原子写入）
        tmp_file = RESULTS_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(rounds_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, RESULTS_FILE)  # 原子替换，防止写入中途崩溃

        passed = rounds_data[-1].get("db_assertion", {}).get("passed", False)
        status = "PASS" if passed else "FAIL"
        info(f"  第 {i}/{total_rounds} 轮完成 [{status}]")
        if i < total_rounds:
            time.sleep(1)  # 轮间间隔缩短为 1s

    # 清理临时 junitxml（避免磁盘爆满）
    for xml_file in [f for f in os.listdir(RESULTS_DIR) if f.startswith("round_") and f.endswith(".xml")]:
        try:
            os.remove(os.path.join(RESULTS_DIR, xml_file))
        except OSError:
            pass

    # ── 生成 HTML 报告 ──
    info(f"{'=' * 60}")
    info(f"  全部 {total_rounds} 轮测试完成，生成报告...")
    report_path = generate_html_report(rounds_data, output_path, detail_rounds=report_detail)
    info(f"  报告已生成: {report_path}")
    info(f"  中间数据: {RESULTS_FILE}")
    info(f"{'=' * 60}")

    # 汇总
    total_tests = sum(len(r.get("tests", [])) for r in rounds_data)
    passed_tests = sum(
        1 for r in rounds_data
        for t in r.get("tests", [])
        if t.get("passed", False)
    )
    passed_rounds = sum(
        1 for r in rounds_data
        if r.get("db_assertion", {}).get("passed", False)
    )

    info(f"  总结:")
    info(f"    通过轮次: {passed_rounds}/{total_rounds}")
    info(f"    通过测试: {passed_tests}/{total_tests}")
    info(f"{'=' * 60}")

    return 0 if passed_rounds == total_rounds else 1


if __name__ == "__main__":
    sys.exit(main())
