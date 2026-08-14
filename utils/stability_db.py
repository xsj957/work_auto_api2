# -*- coding: utf-8 -*-
"""
稳定性测试 - 数据库查询工具
===========================
查询 infra_api_access_log 表，提供两类数据：
1. 测试用例调用的所有 API 接口（API 调用明细）
2. 灯控推送成功记录（数据库断言）

数据库断言逻辑：
- 根据每轮测试的开始/结束时间查询
- 灯控记录只断言"推送成功"的记录（排除 websocket 错误上报）
"""

import atexit
import json
from datetime import datetime

import pymysql
from dbutils.pooled_db import PooledDB

from utils.config import config

# 数据库连接配置（必须在 config.yaml 的 mysql_db 中配置）
_db_cfg = config.get("mysql_db", {})
DB_HOST = _db_cfg.get("host", "")
DB_PORT = _db_cfg.get("port", 3306)
DB_USER = _db_cfg.get("user", "")
DB_PASSWORD = _db_cfg.get("password", "")
DB_NAME = _db_cfg.get("database", "xczg")

# 灯控相关 API 路径
LIGHT_API_PATTERNS = [
    "%switchLight%",
    "%regionSwitchLight%",
    "%tempOpenLight%",
    "%tempCloseLight%",
]

# 排除的 operate 关键字（websocket 错误上报不算有效灯控推送）
EXCLUDE_OPERATES = ["websocket"]

# 连接池（全局单例，避免每轮重建连接）
_pool = None


def _close_pool():
    """程序退出时关闭连接池"""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


atexit.register(_close_pool)


def _get_pool():
    """获取或创建连接池（单例）"""
    global _pool
    if _pool is None:
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=5,
            mincached=1,
            maxcached=3,
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
    return _pool


def get_connection():
    """从连接池获取连接（用完后必须 close 归还池中）"""
    return _get_pool().connection()


def _format_time(t):
    """统一时间格式"""
    if isinstance(t, datetime):
        return t.strftime("%Y-%m-%d %H:%M:%S")
    return str(t)


def _parse_request_params(raw):
    """
    解析 request_params 字段
    Returns: (params_dict, body_dict)
    """
    try:
        params = json.loads(raw) if raw else {}
        body = json.loads(params.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        params, body = {}, {}
    return params, body


def _parse_record(row, is_light_query=False):
    """
    解析单条 API 记录

    Args:
        row: 数据库行
        is_light_query: 是否为灯控查询（用于过滤 websocket 错误上报）

    Returns:
        dict or None
    """
    params, body = _parse_request_params(row.get("request_params", ""))

    # 灯控查询时过滤 websocket 错误上报
    if is_light_query:
        operate = str(body.get("operate", ""))
        if any(kw in operate for kw in EXCLUDE_OPERATES):
            return None

    result_code = row.get("result_code", 0)
    http_success = result_code == 200

    # 灯控记录：推送可能失败（body.operate 含"失败"），即使 HTTP 200
    is_success = http_success
    if is_light_query and http_success:
        operate = str(body.get("operate", ""))
        if "失败" in operate:
            is_success = False

    return {
        "id": row.get("id"),
        "url": row.get("request_url", ""),
        "method": row.get("request_method", ""),
        "operate_name": row.get("operate_name", ""),
        "operate_module": row.get("operate_module", ""),
        "params": params,
        "body": body,
        "response_body": row.get("response_body"),
        "result_code": result_code,
        "result_msg": row.get("result_msg", ""),
        "duration_ms": row.get("duration", 0),
        "user_ip": row.get("user_ip", ""),
        "create_time": _format_time(row.get("create_time")),
        "is_success": is_success,
    }


# ================================================================
#  1. 全量 API 查询（用于 API 调用明细）
# ================================================================

def query_all_api_records(start_time, end_time, store_no=None,
                          exclude_short=True):
    """
    查询时间范围内所有 API 调用记录（测试用例实际调用的接口）

    Args:
        start_time: 开始时间
        end_time: 结束时间
        store_no: 门店编号（可选）
        exclude_short: 是否排除短日志路径（查询类接口）

    Returns:
        list[dict]: API 记录列表
    """
    start_str = _format_time(start_time)
    end_str = _format_time(end_time)

    conn = get_connection()
    try:
        cursor = conn.cursor()

        query = """
            SELECT id, request_url, request_method, operate_name, operate_module,
                   request_params, response_body, result_code, result_msg,
                   duration, user_ip, create_time
            FROM infra_api_access_log
            WHERE create_time BETWEEN %s AND %s
            AND is_deleted = 0
        """
        params = [start_str, end_str]
        if store_no:
            query += " AND request_params LIKE %s"
            params.append(f"%{store_no}%")

        query += " ORDER BY create_time ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        records = []
        for row in rows:
            record = _parse_record(row, is_light_query=False)
            if record:
                records.append(record)

        return records

    finally:
        conn.close()


# ================================================================
#  2. 灯控推送记录查询（用于数据库断言）
# ================================================================

def query_light_records(start_time, end_time, store_no=None):
    """
    查询指定时间范围内的灯控推送记录（仅有效推送，排除 websocket 错误上报）

    Returns:
        list[dict]: 灯控记录列表，每条包含推送操作详情
    """
    start_str = _format_time(start_time)
    end_str = _format_time(end_time)

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # URL 过滤条件（% 在 SQL LIKE 中需要双写）
        url_conditions = " OR ".join(
            f"request_url LIKE %s" for _ in LIGHT_API_PATTERNS
        )
        url_params = [p.strip("%") for p in LIGHT_API_PATTERNS]
        url_params = [f"%{p}%" for p in url_params]

        query = f"""
            SELECT id, request_url, operate_type, operate_name, operate_module,
                   request_params, response_body, result_code, result_msg,
                   duration, user_ip, create_time
            FROM infra_api_access_log
            WHERE create_time BETWEEN %s AND %s
            AND ({url_conditions})
            AND is_deleted = 0
        """
        params = [start_str, end_str] + url_params
        if store_no:
            query += " AND request_params LIKE %s"
            params.append(f"%{store_no}%")

        query += " ORDER BY create_time ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        records = []
        for row in rows:
            record = _parse_record(row, is_light_query=True)
            if record:
                # 附加推送状态描述
                record["push_desc"] = _get_push_desc(record)
                records.append(record)

        return records

    finally:
        conn.close()


def _get_push_desc(record):
    """
    生成灯控推送状态描述

    Returns:
        str: 如 "推送 区域开关灯 成功" / "推送 临时开灯 失败"
    """
    body = record.get("body", {})
    operate = str(body.get("operate", ""))
    op_name = record.get("operate_name", "")
    http_success = record.get("is_success", False)

    if operate and "推送" in operate:
        # 提取目标动作：去掉引号和多余文字
        # 例："推送 '临时开灯'灯光操作" → "临时开灯"
        # 例："推送 '临时关灯'灯光操作失败" → "临时关灯"
        target = operate.replace("推送", "").replace("'", "").replace('"', "")
        target = target.replace("灯光操作失败", "").replace("灯光操作", "").strip()

        # 推送状态优先从 operate 文本判断，其次从 HTTP 状态码
        if "操作失败" in operate or "失败" in operate:
            status = "失败"
        else:
            status = "成功" if http_success else "失败"

        if target:
            return f"推送 {target} {status}"

    # 兜底：使用 operate_name
    if op_name:
        status = "成功" if http_success else "失败"
        return f"{op_name} {status}"

    return "未知操作"


# ================================================================
#  3. 数据库断言
# ================================================================

def assert_light_records(start_time, end_time, store_no=None,
                         expected_min_count=1):
    """
    数据库断言：验证时间范围内存在有效的灯控推送成功记录

    Returns:
        tuple: (passed: bool, records: list, message: str)
            records: 返回全部灯控记录（成功+失败），不只看成功的
    """
    records = query_light_records(start_time, end_time, store_no)
    success_records = [r for r in records if r["is_success"]]

    if len(success_records) >= expected_min_count:
        return (
            True,
            records,  # 返回全部记录
            f"数据库断言通过: {len(success_records)}/{len(records)} 条灯控推送成功"
            f"（期望 >= {expected_min_count}）"
        )
    else:
        return (
            False,
            records,  # 返回全部记录
            f"数据库断言失败: 仅 {len(success_records)}/{len(records)} 条灯控推送成功"
            f"（期望 >= {expected_min_count}）"
        )


def get_light_summary(records):
    """
    生成灯控记录摘要（用于报告展示）

    Returns:
        dict: {total, success, failed, by_url, by_operation}
    """
    summary = {
        "total": len(records),
        "success": sum(1 for r in records if r["is_success"]),
        "failed": sum(1 for r in records if not r["is_success"]),
        "by_operation": {},
    }

    for r in records:
        desc = r.get("push_desc", r.get("operate_name", "未知"))
        if desc not in summary["by_operation"]:
            summary["by_operation"][desc] = {"total": 0, "success": 0}
        summary["by_operation"][desc]["total"] += 1
        if r["is_success"]:
            summary["by_operation"][desc]["success"] += 1

    return summary
