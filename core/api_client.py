# -*- coding: utf-8 -*-
"""
核心 API 客户端
==============
统一的 HTTP 请求封装，支持：
1. 自动断言（code 检查）
2. 请求/响应日志记录
3. 接口响应时间监控（集成 rt_collector）
4. 严格模式/宽松模式切换

使用示例：
    client = APIClient()
    response = client.post("/merchant-api/store/desk/list", {"storeNo": "344917"}, token=auth_token)
"""

# 1. 标准库
import json
import time
import warnings
from typing import Optional, Dict, Any
from dataclasses import dataclass

# 2. 第三方库
import requests
from urllib3.exceptions import InsecureRequestWarning

# 关闭 SSL 警告
warnings.filterwarnings("ignore", category=InsecureRequestWarning)
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# 3. 项目模块
from utils.log_control import INFO, ERROR, WARNING
from utils.config import config

# 尝试导入 allure（可选）
try:
    import allure
    HAS_ALLURE = True
except ImportError:
    HAS_ALLURE = False


# ================================================================
#  配置
# ================================================================
BASE_URL = config.host + "/fast"
TIMEOUT = 30
VERIFY_SSL = config.get("ssl_verify", False)  # 从 config.yaml 读取，默认 False（兼容 UAT）

# 查询类接口黑名单：命中的路径只记响应摘要，不 dump 完整 data
# 注意：匹配时剥掉 /merchant-api 或 /app-api 前缀，所以这里只写业务路径
_SHORT_LOG_PATHS = frozenset({
    "/store/desk/region/list",
    "/store/desk/fee/page",
    "/store/desk/list",
    "/store/desk/listV3",
    "/store/golfer/pageV2",
})


# ================================================================
#  响应数据类
# ================================================================
@dataclass
class ApiResponse:
    """API 响应数据封装"""
    code: int
    msg: str
    data: Any
    status_code: int
    elapsed_ms: float  # 响应时间（毫秒）
    raw_response: Dict[str, Any]

    @classmethod
    def from_response(cls, response: requests.Response, elapsed_ms: float) -> 'ApiResponse':
        """从 requests.Response 创建 ApiResponse"""
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError):
            data = {}

        return cls(
            code=data.get("code", 0),
            msg=data.get("msg", ""),
            data=data.get("data"),
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            raw_response=data
        )

    def is_success(self) -> bool:
        """判断请求是否成功"""
        return self.code == 200

    def get_data(self, key: str = None, default: Any = None) -> Any:
        """获取响应数据

        用法：
            get_data()          → 返回整个 data 字段（None 时返回 None）
            get_data(default=[])→ data 为 None 时返回 default
            get_data("field")   → 返回 data["field"]（data 非 dict 时返回 default）
            get_data("field", default=0) → 同上，指定默认值
        """
        if key is None:
            # 无 key：返回整个 data，为 None 时使用 default
            return self.data if self.data is not None else default
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        # data 不是 dict（可能是 list/str/int），按 key 取不到，返回 default
        return default


# ================================================================
#  API 客户端类
# ================================================================
class APIClient:
    """
    API 客户端

    特性：
    - 自动记录请求/响应日志
    - 自动记录响应时间
    - 支持严格模式（自动断言）和宽松模式
    - 集成 Allure 报告（可选）

    使用示例：
        client = APIClient()

        # 严格模式（默认）：code != 200 时抛出异常
        response = client.post("/api/users", {"name": "test"}, token=token)

        # 宽松模式：返回原始响应，不抛异常
        response = client.post("/api/users", {"name": "test"}, strict=False)
    """

    def __init__(self, base_url: str = None, timeout: int = TIMEOUT):
        """
        初始化 API 客户端

        Args:
            base_url: API 基础 URL（默认使用 config.host + "/fast"）
            timeout: 默认超时时间（秒）
        """
        self.base_url = base_url or BASE_URL
        self.timeout = timeout
        self.session = requests.Session()
        self.log = INFO.logger

    def post(self, path: str, data: Dict = None, token: str = None,
             step_name: str = "", expect_code: int = 200,
             timeout: int = None, strict: bool = True,
             **kwargs) -> ApiResponse:
        """
        发送 POST 请求

        Args:
            path: API 路径（如 "/merchant-api/store/desk/list"）
            data: 请求体
            token: 认证 token
            step_name: 步骤名称（用于日志）
            expect_code: 期望的响应 code
            timeout: 超时时间（秒）
            strict: True=严格模式（code != expect_code 时抛异常）
            **kwargs: 其他 requests.post 参数

        Returns:
            ApiResponse: 响应数据封装

        Raises:
            RuntimeError: strict=True 且 code != expect_code
        """
        return self._request("POST", path, data=data, token=token,
                            step_name=step_name, expect_code=expect_code,
                            timeout=timeout, strict=strict, **kwargs)

    def get(self, path: str, params: Dict = None, token: str = None,
            step_name: str = "", timeout: int = None,
            **kwargs) -> ApiResponse:
        """
        发送 GET 请求

        Args:
            path: API 路径
            params: 查询参数
            token: 认证 token
            step_name: 步骤名称（用于日志）
            timeout: 超时时间（秒）
            **kwargs: 其他 requests.get 参数

        Returns:
            ApiResponse: 响应数据封装
        """
        return self._request("GET", path, params=params, token=token,
                            step_name=step_name, timeout=timeout, **kwargs)

    def _request(self, method: str, path: str, token: str = None,
                 step_name: str = "", expect_code: int = 200,
                 timeout: int = None, strict: bool = True,
                 **kwargs) -> ApiResponse:
        """
        内部请求方法

        Args:
            method: HTTP 方法（POST/GET）
            path: API 路径
            token: 认证 token
            step_name: 步骤名称
            expect_code: 期望的响应 code
            timeout: 超时时间
            strict: 是否严格模式
            **kwargs: 其他请求参数

        Returns:
            ApiResponse: 响应数据封装
        """
        # 构造完整 URL（在 allure.step 外部构造，作为参数传入模板）
        url = self.base_url + path

        # 使用 allure.step context manager 展示步骤
        # 注：allure 的 SafeFormatter 会对模板变量加 repr() 引号，
        # 所以改为 context manager 方式直接传完整字符串
        import contextlib
        if HAS_ALLURE and step_name:
            _step_cm = allure.step(f"{step_name} | {method} {path}")
        else:
            _step_cm = contextlib.nullcontext()

        def _do_request():
            with _step_cm:
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = token

                # 记录请求日志
                self.log.info(f"[{step_name}] {method} {url}")
                if 'data' in kwargs:
                    self.log.info(f"[{step_name}] 请求参数: {json.dumps(kwargs['data'], ensure_ascii=False, indent=2)}")
                if 'params' in kwargs:
                    self.log.info(f"[{step_name}] 查询参数: {json.dumps(kwargs['params'], ensure_ascii=False, indent=2)}")

                # 将 data 转为 json 参数，让 requests 自动 JSON 序列化
                # （data=dict 会发送表单编码，与服务端 application/json 不匹配）
                if 'data' in kwargs:
                    kwargs['json'] = kwargs.pop('data')

                # 发送请求并记录响应时间
                start_time = time.time()
                try:
                    response = self.session.request(
                        method=method,
                        url=url,
                        headers=headers,
                        verify=VERIFY_SSL,
                        timeout=timeout or self.timeout,
                        **kwargs
                    )
                    elapsed_ms = (time.time() - start_time) * 1000

                except requests.exceptions.RequestException as e:
                    elapsed_ms = (time.time() - start_time) * 1000
                    ERROR.logger.error(f"[{step_name}] 请求异常: {e}")

                    if strict:
                        raise RuntimeError(f"[{step_name}] 请求失败: {e}")

                    # 返回错误响应
                    return ApiResponse(
                        code=0,
                        msg=str(e),
                        data=None,
                        status_code=0,
                        elapsed_ms=elapsed_ms,
                        raw_response={"error": str(e)}
                    )

                # 解析响应
                api_response = ApiResponse.from_response(response, elapsed_ms)

                # 性能监控：超过 1000ms 的接口输出详细警告
                if elapsed_ms > 1000:
                    WARNING.logger.warning(
                        f"\n{'=' * 60}\n"
                        f"⚠️  慢接口警告: {step_name}\n"
                        f"{'=' * 60}\n"
                        f"请求方式: {method}\n"
                        f"请求地址: {url}\n"
                        f"响应时间: {elapsed_ms:.2f}ms (超过 1000ms 阈值)\n"
                        f"响应状态: code={api_response.code}, msg={api_response.msg}\n"
                        f"{'=' * 60}\n"
                    )

                # 记录响应日志
                self.log.info(f"[{step_name}] 响应 code={api_response.code}, msg={api_response.msg}, 耗时={elapsed_ms:.2f}ms")
                # 查询类接口只记摘要，不 dump 完整 data（剥掉 /merchant-api、/app-api 前缀再匹配）
                biz_path = path
                for prefix in ("/merchant-api", "/app-api"):
                    if biz_path.startswith(prefix):
                        biz_path = biz_path[len(prefix):]
                        break
                if biz_path not in _SHORT_LOG_PATHS:
                    self.log.info(f"[{step_name}] data={json.dumps(api_response.raw_response.get('data'), ensure_ascii=False, indent=2)}")

                # Allure 附件：响应数据
                if HAS_ALLURE and step_name:
                    # 摘要信息始终附加
                    allure.attach(
                        f"code={api_response.code}, msg={api_response.msg}, 耗时={elapsed_ms:.2f}ms",
                        name=f"[{step_name}] 响应摘要",
                        attachment_type=allure.attachment_type.TEXT
                    )
                    # 非黑名单接口附加完整响应（成功/失败都附加）
                    if biz_path not in _SHORT_LOG_PATHS:
                        allure.attach(
                            json.dumps(api_response.raw_response, ensure_ascii=False, indent=2),
                            name=f"[{step_name}] 完整响应",
                            attachment_type=allure.attachment_type.JSON
                            )

                # 严格模式检查
                if strict and api_response.code != expect_code:
                    ERROR.logger.error(f"[{step_name}] 断言失败! 期望 code={expect_code}, 实际 code={api_response.code}")
                    ERROR.logger.error(f"[{step_name}] 完整响应: {json.dumps(api_response.raw_response, ensure_ascii=False, indent=2)}")
                    raise RuntimeError(f"[{step_name}] 断言失败! code={api_response.code}, msg={api_response.msg}")

                return api_response

        return _do_request()

    def close(self):
        """关闭 session"""
        self.session.close()

    def __enter__(self):
        """支持 with 语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出 with 语句时关闭 session"""
        self.close()


# ================================================================
#  便捷函数（向后兼容）
# ================================================================

def api_post(path: str, body: dict, token: Optional[str] = None,
             step_name: str = "", expect_code: int = 200,
             timeout: int = TIMEOUT, strict: bool = True) -> Dict[str, Any]:
    """
    便捷函数：发送 POST 请求（向后兼容）

    推荐使用 APIClient 类。
    """
    client = APIClient()
    response = client.post(path, data=body, token=token, step_name=step_name,
                          expect_code=expect_code, timeout=timeout, strict=strict)
    return response.raw_response


def api_get(path: str, params: Optional[dict] = None, token: Optional[str] = None,
            step_name: str = "", timeout: int = TIMEOUT) -> Dict[str, Any]:
    """
    便捷函数：发送 GET 请求（向后兼容）

    推荐使用 APIClient 类。
    """
    client = APIClient()
    response = client.get(path, params=params, token=token, step_name=step_name,
                         timeout=timeout)
    return response.raw_response


# ================================================================
#  工具函数
# ================================================================

def find_by_name(item_list: list, name_field: str, target_name: str) -> Optional[Dict]:
    """在列表中按名称字段查找目标项"""
    for item in item_list:
        if item.get(name_field) == target_name:
            return item
    return None


def get_cache_value(cache_name: str, default: Any = None) -> Any:
    """获取缓存值（从内存缓存）"""
    # 使用简单的内存缓存
    if not hasattr(get_cache_value, '_cache'):
        get_cache_value._cache = {}
    return get_cache_value._cache.get(cache_name, default)


def update_cache_value(cache_name: str, value: Any):
    """更新缓存值"""
    if not hasattr(update_cache_value, '_cache'):
        update_cache_value._cache = {}
    update_cache_value._cache[cache_name] = value


def get_store_no() -> str:
    """获取门店编号"""
    return get_cache_value("storeNo", "")


def get_merchant_no() -> str:
    """获取商户编号"""
    return get_cache_value("merchantNoZM", "")


def get_user_no() -> str:
    """获取用户编号"""
    return get_cache_value("userNoZM", "")


def get_token() -> str:
    """获取登录 token"""
    return get_cache_value("merchant_token", "")
