# -*- coding: utf-8 -*-
"""
YAML 数据加载器
===============
从 YAML 文件加载测试数据，支持 pytest.mark.parametrize 集成。

使用示例：
    # 加载测试用例
    test_cases = DataLoader.load_test_cases("data/payment/test_cash_payment.yaml")

    # 生成 parametrize 装饰器
    @DataLoader.parametrize("data/payment/test_cash_payment.yaml")
    def test_cash_payment(self, test_case):
        ...
"""

# 1. 标准库
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

# 2. 第三方库
import yaml
import pytest


class DataLoader:
    """
    YAML 数据加载器

    特性：
    - 从 YAML 文件加载测试用例
    - 支持单个用例或多个用例
    - 自动生成 parametrize 装饰器
    - 支持测试用例 ID（用于报告）

    使用示例：
        # 方式1：直接加载
        test_cases = DataLoader.load_test_cases("data/test.yaml")
        for case in test_cases:
            print(case['case_id'], case['test_data'])

        # 方式2：parametrize 装饰器
        @DataLoader.parametrize("data/test.yaml")
        def test_something(self, test_case):
            ...

        # 方式3：带自定义 ID
        @DataLoader.parametrize("data/test.yaml", id_field="case_id")
        def test_something(self, test_case):
            ...
    """

    @staticmethod
    def load_test_cases(yaml_file: str) -> List[Dict[str, Any]]:
        """
        从 YAML 文件加载测试用例

        Args:
            yaml_file: YAML 文件路径

        Returns:
            List[Dict]: 测试用例列表

        Raises:
            FileNotFoundError: 文件不存在
            yaml.YAMLError: YAML 格式错误

        使用示例：
            test_cases = DataLoader.load_test_cases("data/test.yaml")
        """
        # 解析文件路径
        if not os.path.isabs(yaml_file):
            # 相对路径：从项目根目录开始
            project_root = Path(__file__).parent.parent
            yaml_file = project_root / yaml_file

        yaml_file = str(yaml_file)

        if not os.path.exists(yaml_file):
            raise FileNotFoundError(f"YAML 文件不存在: {yaml_file}")

        # 读取 YAML 文件
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if data is None:
            return []

        # 支持两种格式：
        # 1. 列表格式：[{case_id: ..., test_data: ...}, ...]
        # 2. 字典格式：{test_cases: [{...}, ...]}
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # 查找 test_cases 字段
            if 'test_cases' in data:
                return data['test_cases']
            # 兼容其他字段名
            elif 'cases' in data:
                return data['cases']
            else:
                # 假设整个字典就是一个测试用例
                return [data]
        else:
            return []

    @staticmethod
    def load_yaml(yaml_file: str) -> Any:
        """
        加载任意 YAML 文件

        Args:
            yaml_file: YAML 文件路径

        Returns:
            Any: YAML 内容

        使用示例：
            config = DataLoader.load_yaml("config/settings.yaml")
        """
        if not os.path.isabs(yaml_file):
            project_root = Path(__file__).parent.parent
            yaml_file = project_root / yaml_file

        yaml_file = str(yaml_file)

        if not os.path.exists(yaml_file):
            raise FileNotFoundError(f"YAML 文件不存在: {yaml_file}")

        with open(yaml_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    @staticmethod
    def parametrize(yaml_file: str, id_field: str = None,
                    ids: bool = True) -> Callable:
        """
        从 YAML 文件生成 parametrize 装饰器

        Args:
            yaml_file: YAML 文件路径
            id_field: 用作测试 ID 的字段名（默认使用 case_id）
            ids: 是否生成测试 ID（默认 True）

        Returns:
            pytest.mark.parametrize: parametrize 装饰器

        使用示例：
            # 基本用法
            @DataLoader.parametrize("data/test.yaml")
            def test_something(self, test_case):
                desk_no = test_case['desk_no']
                ...

            # 自定义 ID 字段
            @DataLoader.parametrize("data/test.yaml", id_field="name")
            def test_something(self, test_case):
                ...

            # 不生成 ID
            @DataLoader.parametrize("data/test.yaml", ids=False)
            def test_something(self, test_case):
                ...
        """
        test_cases = DataLoader.load_test_cases(yaml_file)

        # 提取测试数据
        params = []
        for case in test_cases:
            # 如果用例包含 test_data 字段，提取它
            if 'test_data' in case:
                # 保留原始用例信息，方便调试
                test_data = case['test_data'].copy()
                test_data['_case_info'] = {
                    'case_id': case.get('case_id', ''),
                    'description': case.get('description', '')
                }
                params.append(test_data)
            else:
                params.append(case)

        # 生成测试 ID
        test_ids = None
        if ids and test_cases:
            # 优先使用指定的 id_field
            if id_field:
                test_ids = [
                    case.get(id_field, f"case_{i}")
                    for i, case in enumerate(test_cases)
                ]
            # 否则使用 case_id
            else:
                test_ids = [
                    case.get('case_id', f"case_{i}")
                    for i, case in enumerate(test_cases)
                ]

        # 空数据防护：empty parametrize 会导致 pytest 报错
        if not params:
            import warnings
            warnings.warn(f"YAML 文件无测试数据: {yaml_file}，测试将被跳过", stacklevel=2)
            return pytest.mark.skip(reason=f"YAML 无测试数据: {yaml_file}")

        return pytest.mark.parametrize("test_case", params, ids=test_ids)

    @staticmethod
    def get_test_case_by_id(yaml_file: str, case_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 case_id 获取特定测试用例

        Args:
            yaml_file: YAML 文件路径
            case_id: 测试用例 ID

        Returns:
            Dict: 测试用例，未找到返回 None

        使用示例：
            case = DataLoader.get_test_case_by_id("data/test.yaml", "case_001")
        """
        test_cases = DataLoader.load_test_cases(yaml_file)
        for case in test_cases:
            if case.get('case_id') == case_id:
                return case
        return None

    @staticmethod
    def filter_test_cases(yaml_file: str, **conditions) -> List[Dict[str, Any]]:
        """
        根据条件过滤测试用例

        Args:
            yaml_file: YAML 文件路径
            **conditions: 过滤条件（字段名=值）

        Returns:
            List[Dict]: 符合条件的测试用例列表

        使用示例：
            cases = DataLoader.filter_test_cases(
                "data/test.yaml",
                channel="cash",
                expected_amount=20.0
            )
        """
        test_cases = DataLoader.load_test_cases(yaml_file)
        filtered = []

        for case in test_cases:
            match = True
            for key, value in conditions.items():
                # 支持嵌套字段（如 test_data.channel）
                if '.' in key:
                    parts = key.split('.')
                    obj = case
                    for part in parts:
                        if isinstance(obj, dict):
                            obj = obj.get(part)
                        else:
                            obj = None
                            break
                    if obj != value:
                        match = False
                        break
                else:
                    if case.get(key) != value:
                        match = False
                        break

            if match:
                filtered.append(case)

        return filtered


# ================================================================
#  便捷函数
# ================================================================

def load_yaml(file_path: str) -> Any:
    """
    加载 YAML 文件（便捷函数）

    Args:
        file_path: 文件路径

    Returns:
        Any: YAML 内容
    """
    return DataLoader.load_yaml(file_path)


def parametrize_from_yaml(yaml_file: str, **kwargs):
    """
    从 YAML 生成 parametrize（便捷函数）

    Args:
        yaml_file: YAML 文件路径
        **kwargs: 其他参数

    Returns:
        pytest.mark.parametrize: parametrize 装饰器
    """
    return DataLoader.parametrize(yaml_file, **kwargs)
