# PROJECT.md - 卓铭桌台管理系统接口自动化测试

> WorkBuddy 项目上下文文件，每次进入该项目自动加载

## 仓库信息

- **仓库地址**：`git@github.com:xsj957/work_auto_api2.git`
- **GitHub 主页**：https://github.com/xsj957/work_auto_api2
- **项目路径**：`E:\work\work_auto_api2-main`

## 项目概述

卓铭桌台管理系统接口自动化测试框架，测试目标为商户端 SaaS 平台（https://uat.supervisionsstore.com），覆盖桌台管理、支付流程、灯光控制等业务场景。

技术栈：pytest + pluggy + Playwright + POM

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
- 步骤标题格式：`{中文名} | {HTTP方法} {路径}`
- 响应数据通过 `allure.attach` 附加为 TEXT/JSON
- **docstring 第一行自动成为 Allure 标题**

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

### 14. 小程序端 vs 商户后台（Web）接口

小程序端和商户后台的**支付接口路径、请求体、响应结构完全相同**，差异如下：

| 维度 | 商户后台（Web） | 小程序端（App） |
|------|-----------------|-----------------|
| 路径前缀 | `merchant-api` | `app-api` |
| Token | 登录实时获取 | `xcx_token`（抓包获取，写入 config） |
| Base URL | `{host}/fast/merchant-api/...` | `{host}/fast/app-api/...` |

**混合调用模式**：Web 端创建资源（region/fee/desk）+ 开台绑定会员 → 小程序端执行支付操作。只需切换路径前缀和 token，接口路径和参数不变。

**配置注意**：PROD 环境 `app_host` 不要带 `/store` 后缀，否则 app-api 接口返回 404。

## 核心架构

### Fixture 架构

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

- `conftest.py` 只负责 pytest hooks + fixture 导入注册，不含 fixture 定义
- 所有 fixture 定义在 `fixtures/` 目录下，业务逻辑在 `utils/test_helpers.py`
- API 响应日志黑名单：`core/api_client.py` 中 `_SHORT_LOG_PATHS` 集合内的路径只记摘要
- 日志文件命名：`logs/YYYYMMDD/YYYYMMDDHHMMSS.log`，会话启动时自动清理非今日目录

## 配置

- 测试环境通过 `config/config.yaml` 顶层 `env` 字段切换（`UAT` / `PROD`）
- `config.py` 启动时读取 `env`，自动将 `environments[env]` 下的配置合并到顶层
- 新增环境：在 `environments` 下添加对应 key，再在 `env` 字段引用即可
- 通知渠道：`notification_type`（0=关闭, 1=钉钉, 2=微信, 3=邮件, 4=飞书）

## 业务模块概览

**需要详细业务规则时读取对应文档：**

| 模块 | 文档路径 |
|------|----------|
| 支付规则 | `docs/business/payment_rules.md` |
| 优惠券规则（含组合场景） | `docs/business/coupon_rules.md` |
| 会员管理 | `docs/business/member_rules.md` |
| 桌台管理 | `docs/business/desk_management_rules.md` |
| 灯光控制 | `docs/business/lighting_control_rules.md` |

### 支付方式

系统支持 6 种支付方式，分为 3 大类：
- **线下收款**（系统不追踪）：`cash` 现金、`wx_offline` 微信线下扫码
- **拉卡拉支付**（系统集成）：线下二维码、线上小程序微信支付
- **余额支付**（会员账户）：`czk` 储值卡/通用卡、`tfk` 台费卡

### 桌台管理系统

资源层级：**区域 → 台费 → 桌台**
- 区域管理、台费管理、桌台管理（状态：空闲 → 使用中 → 已结账）
- 动态命名：`{前缀}_{时分秒}{1位随机}{worker}`，桌台名称上限 15 字

### 灯光控制系统

- 计时开台 → 手动卡钟 → 计时关台
- 暂停/恢复、转台、并台、小程序控制、待客状态

### 订单管理

- 开台订单 → 订单状态流转 → 子订单 → 台费计算
- 状态：空闲 → 开台 → 计费中 → 结账 → 已支付 → 完成

### 会员管理

- 会员信息：ID、姓名、手机号、等级、余额（通用卡 + 台费卡）
- 操作：详情、储值、发券、调余额、黑名单、新增、修改等级、导入

### 优惠券管理

- 类型：满减券、现金券、折扣券
- 配置：基本信息、使用设置（用券时间/可用日期/有效期）、适用范围、库存
- 状态：开启 / 关闭
- 操作：新增、启用、停用、删除、发放

## 数据库关键信息

### 数据库连接

- 主机：121.40.243.17:3306
- 用户：linjiakun
- 密码：通过环境变量 `DB_PASSWORD` 传入
- 相关库：supervisions（视频业务）、xczg（桌台管理）、xczg_test（测试环境）

### xczg 库 — 分库分表

主表按 `_0`、`_1`、`_2` 分片：

| 主表 | 分片表 | 说明 |
|------|--------|------|
| store_desk_orders | _0/_1/_2 | 桌台订单 |
| store_desk_orders_fee | _0/_1/_2 | 订单费用记录 |
| store_desk_orders_desk | _0/_1/_2 | 订单桌台记录 |
| store_desk_orders_coupon | _0/_1/_2 | 订单优惠券记录 |
| store_desk_orders_golfer | _0/_1/_2 | 订单球手记录 |
| store_desk_orders_payment | _0/_1/_2 | 订单支付记录 |
| store_desk_orders_product | _0/_1/_2 | 订单商品记录 |
| store_desk_orders_serve | _0/_1/_2 | 订单服务记录 |

### 🔴 并台/转台唯一键冲突（已知服务端 Bug）

```sql
UNIQUE KEY uk_order_active_fee (order_no, only_one_active)
```

每个订单 `(order_no)` 只能有一条 `only_one_active=1` 的费用记录。并台/转台时两个订单的活跃费用记录冲突，服务端需先标记旧记录为非活跃再转移。

### 折扣规则

`discount` 值 = 折后百分比，不是折扣幅度：
- `discount=10` = **1 折**（原价的 10%）
- `discount=50` = 5 折
- `discount=85` = 85 折

### 视频制作状态机（video_client_status.status）

| 值 | 状态 | 说明 |
|----|------|------|
| 0 | 待解锁 | 视频已创建，等待用户解锁/付费 |
| 1 | 已解锁等待上传 | 用户已解锁，等待工控机上传原片 |
| 2 | 原片已上传 | 工控机已上传原片到腾讯云 |
| 3 | 下载中 | App 正在从腾讯云下载原片 |
| 4 | 下载失败 | 原片下载失败 |
| 5 | 本地制作中 | App 正在本地制作视频 |
| 6 | 制作失败 | 本地制作失败 |
| 7 | 制作完成 | 成品视频已生成，可播放 |
| 8 | 已过期 | 视频已过期 |

正常流程：0→1→2→3→5→7；异常：3→4（下载失败）、5→6（制作失败）
