# -*- coding: utf-8 -*-
"""
全局缓存模块
============
提供进程内内存缓存，所有模块共享同一个缓存实例。

解决了之前 core/context.py、fixtures/auth_fixtures.py、core/api_client.py
各自维护独立 _cache dict 导致缓存不一致的问题。
"""

_cache: dict = {}


def get_cache(key: str, default=None):
    """获取缓存值"""
    return _cache.get(key, default)


def update_cache(key: str, value):
    """更新缓存值"""
    _cache[key] = value


def clear_cache():
    """清空所有缓存（用于测试隔离）"""
    _cache.clear()
