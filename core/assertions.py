# -*- coding: utf-8 -*-
"""
链式断言工具
============
提供流畅的断言语法，支持多种验证规则。

使用示例：
    response = client.post("/api/users", data)

    assert_response(response)\
        .code_is(200)\
        .msg_contains("成功")\
        .data_has_fields("user_id", "name")\
        .data_field_equals("status", "active")\
        .validate()
"""

from typing import Any, Dict, List, Optional
import json


class ResponseValidator:
    """
    响应验证器（链式调用）

    支持多种验证规则，可以链式调用，最后调用 validate() 执行验证。

    使用示例：
        validator = ResponseValidator(response)
        validator.code_is(200).msg_contains("成功").validate()

        # 或者使用便捷函数
        assert_response(response).code_is(200).validate()
    """

    def __init__(self, response: Dict[str, Any]):
        """
        初始化验证器

        Args:
            response: API 响应字典
        """
        self.response = response
        self._errors: List[str] = []

    def code_is(self, expected_code: int) -> 'ResponseValidator':
        """
        验证 code 字段等于期望值

        Args:
            expected_code: 期望的 code 值

        Returns:
            self（支持链式调用）

        使用示例：
            validator.code_is(200)
        """
        actual_code = self.response.get("code")
        if actual_code != expected_code:
            self._errors.append(
                f"code 验证失败: 期望={expected_code}, 实际={actual_code}"
            )
        return self

    def code_is_not(self, unexpected_code: int) -> 'ResponseValidator':
        """
        验证 code 字段不等于某个值

        Args:
            unexpected_code: 不应该等于的 code 值

        Returns:
            self（支持链式调用）
        """
        actual_code = self.response.get("code")
        if actual_code == unexpected_code:
            self._errors.append(
                f"code 不应该等于 {unexpected_code}"
            )
        return self

    def msg_contains(self, keyword: str) -> 'ResponseValidator':
        """
        验证 msg 字段包含关键词

        Args:
            keyword: 关键词

        Returns:
            self（支持链式调用）

        使用示例：
            validator.msg_contains("成功")
        """
        msg = self.response.get("msg", "")
        if keyword not in msg:
            self._errors.append(
                f"msg 验证失败: 未包含关键词 '{keyword}', 实际 msg='{msg}'"
            )
        return self

    def msg_equals(self, expected_msg: str) -> 'ResponseValidator':
        """
        验证 msg 字段等于期望值

        Args:
            expected_msg: 期望的 msg 值

        Returns:
            self（支持链式调用）
        """
        actual_msg = self.response.get("msg", "")
        if actual_msg != expected_msg:
            self._errors.append(
                f"msg 验证失败: 期望='{expected_msg}', 实际='{actual_msg}'"
            )
        return self

    def data_has_fields(self, *fields: str) -> 'ResponseValidator':
        """
        验证 data 字段包含指定的字段

        Args:
            *fields: 字段名列表

        Returns:
            self（支持链式调用）

        使用示例：
            validator.data_has_fields("user_id", "name", "status")
        """
        data = self.response.get("data", {})
        if not isinstance(data, dict):
            self._errors.append(
                f"data 验证失败: 期望是字典类型, 实际={type(data).__name__}"
            )
            return self

        missing = [f for f in fields if f not in data]
        if missing:
            self._errors.append(
                f"data 字段验证失败: 缺少字段 {missing}"
            )
        return self

    def data_field_equals(self, field: str, expected: Any) -> 'ResponseValidator':
        """
        验证 data 中某字段的值等于期望值

        Args:
            field: 字段名
            expected: 期望值

        Returns:
            self（支持链式调用）

        使用示例：
            validator.data_field_equals("status", "active")
        """
        data = self.response.get("data", {})
        if not isinstance(data, dict):
            self._errors.append(
                f"data 验证失败: 期望是字典类型, 实际={type(data).__name__}"
            )
            return self

        actual = data.get(field)
        if actual != expected:
            self._errors.append(
                f"data.{field} 验证失败: 期望={expected}, 实际={actual}"
            )
        return self

    def data_field_not_equals(self, field: str, unexpected: Any) -> 'ResponseValidator':
        """
        验证 data 中某字段的值不等于某个值

        Args:
            field: 字段名
            unexpected: 不应该等于的值

        Returns:
            self（支持链式调用）
        """
        data = self.response.get("data", {})
        if not isinstance(data, dict):
            return self

        actual = data.get(field)
        if actual == unexpected:
            self._errors.append(
                f"data.{field} 不应该等于 {unexpected}"
            )
        return self

    def data_is_list(self, min_length: int = None, max_length: int = None) -> 'ResponseValidator':
        """
        验证 data 是列表类型，并可选验证长度

        Args:
            min_length: 最小长度（可选）
            max_length: 最大长度（可选）

        Returns:
            self（支持链式调用）

        使用示例：
            validator.data_is_list(min_length=1)
        """
        data = self.response.get("data")
        if not isinstance(data, list):
            self._errors.append(
                f"data 验证失败: 期望是列表类型, 实际={type(data).__name__}"
            )
            return self

        if min_length is not None and len(data) < min_length:
            self._errors.append(
                f"data 列表长度验证失败: 最小长度={min_length}, 实际={len(data)}"
            )

        if max_length is not None and len(data) > max_length:
            self._errors.append(
                f"data 列表长度验证失败: 最大长度={max_length}, 实际={len(data)}"
            )

        return self

    def data_is_dict(self) -> 'ResponseValidator':
        """
        验证 data 是字典类型

        Returns:
            self（支持链式调用）
        """
        data = self.response.get("data")
        if not isinstance(data, dict):
            self._errors.append(
                f"data 验证失败: 期望是字典类型, 实际={type(data).__name__}"
            )
        return self

    def data_is_not_null(self) -> 'ResponseValidator':
        """
        验证 data 不为 None

        Returns:
            self（支持链式调用）
        """
        data = self.response.get("data")
        if data is None:
            self._errors.append("data 验证失败: data 为 None")
        return self

    def data_is_null(self) -> 'ResponseValidator':
        """
        验证 data 为 None

        Returns:
            self（支持链式调用）
        """
        data = self.response.get("data")
        if data is not None:
            self._errors.append(f"data 验证失败: 期望为 None, 实际={data}")
        return self

    def status_code_is(self, expected_status: int) -> 'ResponseValidator':
        """
        验证 HTTP 状态码

        Args:
            expected_status: 期望的 HTTP 状态码

        Returns:
            self（支持链式调用）

        使用示例：
            validator.status_code_is(200)
        """
        # 注意：这需要 ApiResponse 对象，不是普通字典
        if hasattr(self.response, 'status_code'):
            actual_status = self.response.status_code
            if actual_status != expected_status:
                self._errors.append(
                    f"HTTP 状态码验证失败: 期望={expected_status}, 实际={actual_status}"
                )
        return self

    def json_schema(self, schema: Dict) -> 'ResponseValidator':
        """
        使用 JSON Schema 验证响应

        Args:
            schema: JSON Schema 字典

        Returns:
            self（支持链式调用）

        注意：需要安装 jsonschema 库
        """
        try:
            import jsonschema
            jsonschema.validate(instance=self.response, schema=schema)
        except ImportError:
            self._errors.append("jsonschema 库未安装，无法执行 JSON Schema 验证")
        except jsonschema.ValidationError as e:
            self._errors.append(f"JSON Schema 验证失败: {e.message}")
        return self

    def validate(self) -> bool:
        """
        执行验证

        如果有错误，抛出 AssertionError；否则返回 True。

        Returns:
            bool: 验证通过返回 True

        Raises:
            AssertionError: 验证失败时抛出

        使用示例：
            validator.code_is(200).validate()
        """
        if self._errors:
            error_msg = "\n".join([f"  - {err}" for err in self._errors])
            raise AssertionError(f"响应验证失败:\n{error_msg}")
        return True

    def get_errors(self) -> List[str]:
        """
        获取所有错误信息（不抛出异常）

        Returns:
            List[str]: 错误列表

        使用示例：
            errors = validator.get_errors()
            if errors:
                print(errors)
        """
        return self._errors.copy()

    def is_valid(self) -> bool:
        """
        检查是否有效（不抛出异常）

        Returns:
            bool: 没有错误返回 True

        使用示例：
            if validator.is_valid():
                print("验证通过")
        """
        return len(self._errors) == 0


# ================================================================
#  便捷函数
# ================================================================

def assert_response(response) -> ResponseValidator:
    """
    创建响应验证器（便捷函数）

    支持 ApiResponse 对象和 dict 两种输入。

    Args:
        response: API 响应（ApiResponse 或 dict）

    Returns:
        ResponseValidator: 验证器实例

    使用示例：
        assert_response(response).code_is(200).validate()
    """
    # ApiResponse 对象 → 取原始 dict
    if hasattr(response, 'raw_response'):
        response = response.raw_response
    return ResponseValidator(response)


def validate_response(response, expected_code: int = 200) -> bool:
    """
    快速验证响应（便捷函数）

    支持 ApiResponse 对象和 dict 两种输入。

    Args:
        response: API 响应（ApiResponse 或 dict）
        expected_code: 期望的 code 值

    Returns:
        bool: 验证通过返回 True

    Raises:
        AssertionError: 验证失败时抛出

    使用示例：
        validate_response(response, expected_code=200)
    """
    return assert_response(response).code_is(expected_code).validate()
