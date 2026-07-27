# -*- coding: utf-8 -*-
"""
日志模块
========
同时输出到控制台和文件（logs/ 目录）。

目录结构（按日期分目录，只保留当天）：
    logs/
      20260727/
        autoapi.log                # 会话级日志
        test_cash_payment.log      # 测试用例级日志

清理规则：
    每次会话启动时自动删除非今日目录。
"""

import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path


def _get_logs_dir() -> Path:
    """获取日志根目录（logs/）"""
    return Path(__file__).parent.parent / "logs"


def _get_today_dir() -> Path:
    """获取今日日志目录（logs/YYYYMMDD/）"""
    today = datetime.now().strftime("%Y%m%d")
    return _get_logs_dir() / today


def cleanup_old_logs():
    """
    清理非今日的日志目录

    每次会话启动时调用，删除 logs/ 下非今日的日期目录。
    """
    log_dir = _get_logs_dir()
    if not log_dir.exists():
        return

    today = datetime.now().strftime("%Y%m%d")
    deleted_count = 0

    for sub_dir in log_dir.iterdir():
        if sub_dir.is_dir() and sub_dir.name != today:
            try:
                shutil.rmtree(sub_dir)
                deleted_count += 1
            except OSError:
                pass

    if deleted_count > 0:
        print(f"[日志] 清理过期目录: {deleted_count} 个")


def get_logger(
    name: str = "test_framework",
) -> logging.Logger:
    """
    获取日志记录器（仅控制台输出）

    文件输出在 switch_test_logger 中按用例创建。

    Args:
        name: 日志记录器名称

    Returns:
        logging.Logger: 日志记录器实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 每次会话启动清理旧日志
    cleanup_old_logs()

    return logger


def _sanitize_filename(name: str) -> str:
    """清理测试名，移除文件名非法字符（如参数化测试的 []）"""
    return re.sub(r'[\[\]]', '_', name)


def _build_log_filename() -> str:
    """
    生成日志文件名（不含扩展名）

    格式：YYYYMMDDHHMMSS（年月日时分秒）
    """
    return datetime.now().strftime("%Y%m%d%H%M%S")


def switch_test_logger(logger: logging.Logger, test_name: str = None) -> logging.Logger:
    """
    切换日志文件到测试用例级别

    关闭当前 logger 的 FileHandler，创建新的 FileHandler，
    文件名格式：YYYYMMDDHHMMSS.log

    Args:
        logger: 当前 logger 实例
        test_name: 未使用，保留参数兼容

    Returns:
        logging.Logger: 同一个 logger（已切换文件 handler）
    """
    safe_name = _build_log_filename()
    today_dir = _get_today_dir()
    today_dir.mkdir(parents=True, exist_ok=True)

    # 关闭旧 FileHandler（Windows 上必须释放文件锁）
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)

    # 创建新 FileHandler
    log_file = today_dir / f"{safe_name}.log"
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# ================================================================
#  全局日志实例（session 级别，pytest_sessionstart 时更新）
# ================================================================

class _SessionLogger:
    """会话级日志包装器，支持 session 启动时动态更新"""

    def __init__(self):
        self._logger = get_logger()

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @logger.setter
    def logger(self, value: logging.Logger):
        self._logger = value


INFO = _SessionLogger()
ERROR = INFO
WARNING = INFO
