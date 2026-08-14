# -*- coding: utf-8 -*-
"""
测试上下文管理器
================
提供类型安全的测试上下文，集中管理测试数据。

使用示例：
    # 从缓存创建上下文
    ctx = TestContext.from_cache()

    # 访问数据
    token = ctx.token
    merchant_no = ctx.merchant_no

    # 设置自定义数据
    ctx.set("desk_no", "desk_001")
    desk_no = ctx.get("desk_no")
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from utils.cache import get_cache, update_cache


@dataclass
class TestContext:
    """
    测试上下文

    集中管理测试过程中需要的各种数据：
    - 认证信息（token, merchant_no 等）
    - 业务数据（store_no, desk_no 等）
    - 自定义数据（任意键值对）

    特性：
    - 类型安全（dataclass）
    - 支持从缓存加载
    - 支持自定义扩展
    - 易于调试（可打印整个上下文）

    使用示例：
        # 从缓存创建
        ctx = TestContext.from_cache()

        # 访问标准字段
        print(ctx.token)
        print(ctx.merchant_no)

        # 设置自定义数据
        ctx.set("desk_no", "desk_001")

        # 获取自定义数据
        desk_no = ctx.get("desk_no")

        # 打印整个上下文
        print(ctx)
    """

    # 认证信息
    token: str = ""
    merchant_no: str = ""

    # 业务数据
    store_no: str = ""
    user_no: str = ""

    # 自定义数据
    custom: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_cache(cls) -> 'TestContext':
        """
        从缓存创建测试上下文

        Returns:
            TestContext: 包含缓存数据的上下文实例

        使用示例：
            ctx = TestContext.from_cache()
        """
        return cls(
            token=cls._get_cache("merchant_token", ""),
            merchant_no=cls._get_cache("merchantNoZM", ""),
            store_no=cls._get_cache("storeNo", ""),
            user_no=cls._get_cache("userNoZM", ""),
        )

    @classmethod
    def _get_cache(cls, key: str, default: Any = None) -> Any:
        """安全获取缓存值"""
        return get_cache(key, default)

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取自定义数据

        Args:
            key: 数据键
            default: 默认值

        Returns:
            数据值或默认值

        使用示例：
            desk_no = ctx.get("desk_no", "")
        """
        return self.custom.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        设置自定义数据

        Args:
            key: 数据键
            value: 数据值

        使用示例：
            ctx.set("desk_no", "desk_001")
            ctx.set("order_no", "order_123")
        """
        self.custom[key] = value

    def update(self, data: Dict[str, Any]) -> None:
        """
        批量更新自定义数据

        Args:
            data: 数据字典

        使用示例：
            ctx.update({
                "desk_no": "desk_001",
                "order_no": "order_123"
            })
        """
        self.custom.update(data)

    def clear(self) -> None:
        """清空自定义数据"""
        self.custom.clear()

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典

        Returns:
            dict: 包含所有数据的字典

        使用示例：
            data = ctx.to_dict()
        """
        return {
            "token": self.token,
            "merchant_no": self.merchant_no,
            "store_no": self.store_no,
            "user_no": self.user_no,
            "custom": self.custom.copy()
        }

    def __str__(self) -> str:
        """字符串表示（用于调试）"""
        return f"TestContext(token={self.token[:20]}..., merchant_no={self.merchant_no}, store_no={self.store_no}, custom={self.custom})"

    def __repr__(self) -> str:
        """详细表示（用于调试）"""
        return self.__str__()


# ================================================================
#  便捷函数
# ================================================================

def create_context() -> TestContext:
    """
    创建测试上下文（便捷函数）

    Returns:
        TestContext: 从缓存加载的上下文实例

    使用示例：
        ctx = create_context()
    """
    return TestContext.from_cache()
