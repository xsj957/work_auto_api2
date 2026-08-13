# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库信息

- **仓库地址**：`git@github.com:xsj957/work_auto_api2.git`
- **作者邮箱**：13538506002@163.com
- **GitHub 主页**：https://github.com/xsj957/work_auto_api2

## 项目概述

卓铭桌台管理系统接口自动化测试框架，测试目标为商户端 SaaS 平台（https://uat.supervisionsstore.com），覆盖桌台管理、支付流程、灯光控制等业务场景。

## 运行测试

```bash
pytest                                          # 运行全部测试
pytest testcase/payment/                        # 运行支付模块测试
pytest testcase/payment/test_payment_flow.py::TestPaymentFlow::test_cash_payment  # 单个测试
pytest -m smoke                                 # 仅 smoke 测试
pytest --alluredir=reports/allure-results       # 生成 Allure 报告
allure serve reports/allure-results             # 查看报告
python run.py                                   # 运行全部测试 + 生成报告
python run.py --smoke                           # 仅 smoke 测试 + 生成报告
python run.py --lighting                        # 仅灯控测试 + 生成报告
python run.py --payment                         # 仅支付测试 + 生成报告
```

## 强制规范（必须遵守）

### 1. 日志级别

只允许 **info / warning / error** 三个级别，**不允许出现 debug 级别**。

```python
# ✅ 正确
from utils.debug_utils import info, capture_failure
info("开台成功! orderNo={order_no}")

# ❌ 错误
from utils.debug_utils import debug
debug("开台成功")
```

### 2. 资源管理（区域/台费/桌台）

所有资源的创建、验证、清理逻辑**统一在 `utils/test_helpers.py`**，不允许在任何其他文件中重复编写。

```python
# ✅ 正确 — 调用统一函数
from utils.test_helpers import create_region, verify_region, cleanup_region
region_id = create_region(api_client, token)

# ❌ 错误 — 自己写一遍创建逻辑
response = api_client.post("/merchant-api/store/desk/region/create", {...})
```

支付专属逻辑在 `utils/payment_helpers.py`，它从 test_helpers 导入共享函数。

### 3. Fixture 注册

所有 fixture **统一在根 `conftest.py`** 注册，不存在 `fixtures/conftest.py` 中间层。

```
conftest.py                    ← 根级，注册所有 fixture + pytest hooks
fixtures/auth_fixtures.py      ← 认证 fixture（api_client, auth_context 等）
fixtures/resource_fixtures.py  ← 资源 fixture（test_region, test_fee, test_desk 等）
```

测试文件**不需要** `from fixtures.conftest import ...`，pytest 自动从 conftest.py 发现 fixture。

### 4. 测试数据

- 测试数据从 `config/config.yaml` 的 `business_data` 或 `payment_test` 读取
- **不允许硬编码** desk_no、region_no、fee_no 等业务 ID
- 每个测试从 0 到 1 自动创建所需资源（region → fee → desk），teardown 自动清理，**不残留测试数据**

```python
# ✅ 正确 — 使用 fixture 自动创建
def test_clock_calorie(api_client, auth_context, lighting_resources):
    desk_no = lighting_resources['desk_no']

# ❌ 错误 — 硬编码预配桌台
desk_no = config.business_data['desks']['clock']
```

### 5. 动态命名

创建的资源名称必须动态生成，格式：`{前缀}_{时分秒}{1位随机}{worker}`，确保每次执行唯一、并行安全。

```python
# ✅ 正确 — 动态生成
suffix = _gen_suffix()  # "14564730" + "0" = 9位
region_name = f"测试区_{suffix}"     # 13字
desk_name = f"测试桌台_{suffix}_1"   # 15字（服务端上限15字）

# ❌ 错误 — 固定名称或超长名称
region_name = "灯控测试区域_20260727140000_12345"  # 超长，会被拒绝
```

### 6. 测试用例结构

使用 **AAA 模式**（Arrange → Act → Assert），每个测试方法包含清晰的三个阶段注释。

```python
def test_clock_calorie_flow(self, api_client, auth_context, lighting_resources):
    """计时开台 → 手动卡钟 → 计时关台"""
    # Arrange（准备）
    token = auth_context.token
    desk_no = lighting_resources['desk_no']

    # Act（执行）
    response = api_client.post("/merchant-api/store/desk/orders/createClockOpen", ...)

    # Assert（断言）
    assert_response(response).code_is(200).validate()
```

### 7. 导入顺序

```python
# 1. 标准库
import time

# 2. 第三方库
import pytest

# 3. 项目模块
from core.assertions import assert_response
from utils.config import config
from utils.debug_utils import info, capture_failure
from utils.markers import mark_priority
```

### 8. 文件编码

所有 Python 文件使用 UTF-8 编码，文件开头添加：
```python
# -*- coding: utf-8 -*-
```

### 9. Allure 报告

- 使用 `allure.step` context manager 展示步骤（不要用装饰器模板，避免 repr 引号问题）
- 步骤标题格式：`{中文名} | {HTTP方法} {路径}`，例如 `计时开台 | POST /merchant-api/store/desk/orders/createClockOpen`
- 响应数据通过 `allure.attach` 附加为 TEXT/JSON
- **docstring 第一行自动成为 Allure 标题**（conftest.py 的 `pytest_runtest_setup` 提取）

### 10. 异常处理

**禁止 bare except**，必须指定异常类型：
```python
# ❌ 错误
except:
    pass

# ✅ 正确
except (json.JSONDecodeError, ValueError) as e:
    info(f"解析失败: {e}")
```

### 11. Fixture 装饰器顺序

```python
@pytest.mark.smoke          # 或 regression
@pytest.mark.lighting       # 或 payment
@mark_priority(0)           # P0-P3，数字越小优先级越高
@capture_failure            # 最内层
def test_xxx(self, ...):
```

### 12. 资源清理

- 所有 `cleanup_*` 函数调用时**必须传 strict=False**，避免清理失败导致测试误报
- **autouse fixture 只放 conftest.py**，utils/ 下的 autouse fixture 不会被自动加载

### 13. API 客户端关键参数

- `APIClient.post(path, data, token, step_name, ...)` — **step_name 是第4个位置参数**
- `step_name` 用于日志前缀和 Allure 步骤标题，必须填写
- **ERROR = WARNING = INFO**（同一 `_SessionLogger` 实例），区分级别仅语义用途

## 核心架构

### 目录结构

```
conftest.py              # 根级配置：sys.path 注入、pytest hooks、日志、fixture 聚合
config/config.yaml       # 环境配置、业务数据、通知设置
core/
  api_client.py          # APIClient：HTTP 封装、自动日志、严格/宽松模式、响应时间监控
  assertions.py          # 链式断言：assert_response(resp).code_is(200).msg_contains("成功").validate()
  data_loader.py         # YAML 数据驱动：DataLoader.parametrize() 将 YAML 转为 pytest.mark.parametrize
  decorators.py          # 装饰器：@retry, @with_timing, @skip_if, @robust_test
  context.py             # TestContext：认证上下文数据类
fixtures/
  auth_fixtures.py       # 认证 fixtures（session 级）：api_client, auth_token, auth_context
  resource_fixtures.py   # 资源 fixtures（function 级）：test_region, test_fee, test_desk, test_resources
testcase/                # 测试用例目录（非 tests/）
  payment/               # 支付测试
  lighting/              # 灯控测试
utils/
  config.py              # Config 单例，加载 config.yaml，支持 config.get("business_data.login.username")
  data_factory.py        # 测试数据工厂：random_phone(), desk_name() 等
  log_control.py         # 日志引擎：按日期分目录（logs/YYYYMMDD/），自动清理非今日日志
  markers.py             # Marker 注册和优先级管理
  debug_utils.py         # 日志工具：info() / capture_failure 装饰器
  test_helpers.py        # 统一资源管理（灯控+支付共用）：创建/验证/清理 region/fee/desk
  payment_helpers.py     # 支付专属逻辑（从 test_helpers 导入共享函数）
```

### 关键模式

**Fixture 架构（前置/后置数据管理）**：

```
session 级（全局前置，整个会话只执行一次）
  ├── api_client      → APIClient 实例（fixtures/auth_fixtures.py）
  ├── auth_token       → 登录 token（自动重试 3 次，指数退避）
  └── auth_context     → TestContext（token + merchant_no + store_no）

function 级（每个测试独立前置/后置）
  ├── lighting_resources    → 单桌台：region → fee → desk（8 个灯控测试使用）
  └── lighting_resources_2  → 双桌台：region → fee1 + fee2 → desk1 + desk2（转台/并台）
       注意：两个桌台使用不同台费，避免服务端 uk_order_active_fee 唯一约束冲突

teardown 顺序（pytest 自动逆序清理）：desk → fee → region
```

`conftest.py` 只负责 pytest hooks + fixture 导入注册，不含 fixture 定义。
所有 fixture 定义在 `fixtures/` 目录下，业务逻辑在 `utils/test_helpers.py`。

**API 响应日志黑名单**：`core/api_client.py` 中 `_SHORT_LOG_PATHS` 集合内的路径只记摘要（code/msg/耗时），不 dump 完整 data。新增查询类接口需在此添加。

**日志文件命名**：按日期分目录 `logs/YYYYMMDD/`，文件名格式 `YYYYMMDDHHMMSS.log`（年月日时分秒）。会话启动时自动清理非今日目录。

## 配置

- 测试环境通过 `config/config.yaml` 顶层 `env` 字段切换（`UAT` / `PROD`）
- `config.py` 启动时读取 `env`，自动将 `environments[env]` 下的 `host` / `app_host` / `ssl_verify` / `business_data` / `payment_test` 合并到顶层，代码中访问方式不变（如 `config.host`、`config.business_data`）
- 新增环境：在 `environments` 下添加对应 key，再在 `env` 字段引用即可；若 `env` 引用了不存在的 key，启动时会抛 `ValueError`
- 业务数据（登录账号、门店号、桌台 ID 等）在 `environments[env].business_data` 中配置
- 通知渠道通过 `notification_type` 控制（0=关闭, 1=钉钉, 2=微信, 3=邮件, 4=飞书）

## 业务模块概览

**需要详细业务规则时 @ 对应文档：**

| 模块 | 文档路径 |
|------|----------|
| 支付规则 | `@docs/business/payment_rules.md` |
| 优惠券规则（含组合场景） | `@docs/business/coupon_rules.md` |
| 会员管理 | `@docs/business/member_rules.md` |
| 桌台管理 | `@docs/business/desk_management_rules.md` |
| 灯光控制 | `@docs/business/lighting_control_rules.md` |

### 支付方式

系统支持 6 种支付方式，分为 3 大类：
- **线下收款**（系统不追踪）：`cash` 现金、`wx_offline` 微信线下扫码
- **拉卡拉支付**（系统集成）：线下二维码、线上小程序微信支付
- **余额支付**（会员账户）：`czk` 储值卡/通用卡、`tfk` 台费卡

详见 → `@docs/business/payment_rules.md`

### 桌台管理系统

资源层级：**区域 → 台费 → 桌台**

- 区域管理、台费管理、桌台管理（状态：空闲 → 使用中 → 已结账）
- 动态命名：`{前缀}_{时分秒}{1位随机}{worker}`，桌台名称上限 15 字

详见 → `@docs/business/desk_management_rules.md`

### 灯光控制系统

- 计时开台 → 手动卡钟 → 计时关台
- 暂停/恢复、转台、并台、小程序控制、待客状态

详见 → `@docs/business/lighting_control_rules.md`

### 订单管理

- 开台订单 → 订单状态流转 → 子订单 → 台费计算
- 状态：空闲 → 开台 → 计费中 → 结账 → 已支付 → 完成

### 会员管理

- 会员信息：ID、姓名、手机号、等级、余额（通用卡 + 台费卡）
- 操作：详情、储值、发券、调余额、黑名单、新增、修改等级、导入

详见 → `@docs/business/member_rules.md`

### 优惠券管理

- 类型：满减券、现金券、折扣券
- 配置：基本信息、使用设置（用券时间/可用日期/有效期）、适用范围、库存
- 状态：开启 / 关闭
- 操作：新增、启用、停用、删除、发放

详见 → `@docs/business/coupon_rules.md`
