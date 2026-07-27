# -*- coding: utf-8 -*-
"""
配置管理模块
============
读取和提供配置信息。
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any


class Config:
    """配置类"""

    def __init__(self, config_file: str = None):
        """
        初始化配置

        Args:
            config_file: 配置文件路径
        """
        if config_file is None:
            # 默认配置文件路径
            config_file = Path(__file__).parent.parent / "config" / "config.yaml"

        self.config_file = Path(config_file)
        self._config = {}
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键（支持点分隔，如 "business_data.login.username"）
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

            if value is None:
                return default

        return value

    @property
    def host(self) -> str:
        """获取 API 主机地址"""
        return self.get("host", "")

    @property
    def business_data(self) -> Dict[str, Any]:
        """获取业务数据配置"""
        return self.get("business_data", {})

    @property
    def payment_test(self) -> Dict[str, Any]:
        """获取支付测试配置"""
        return self.get("payment_test", {})


# 全局配置实例
config = Config()
