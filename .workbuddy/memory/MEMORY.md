# work_auto_api2 项目记忆

> 从 CLAUDE.md 提取的关键业务逻辑和测试规范

## 项目强制规范

### 日志
- 只允许 info / warning / error，**禁止 debug**
- `ERROR = WARNING = INFO`（同一 `_SessionLogger` 实例）

### 资源管理
- 创建/验证/清理统一在 `utils/test_helpers.py`
- 支付专属逻辑在 `utils/payment_helpers.py`
- 禁止在其他文件重复编写

### Fixture
- 统一在根 `conftest.py` 注册，无中间层
- fixture 定义在 `fixtures/` 目录
- 装饰器顺序：`@pytest.mark.smoke` → `@pytest.mark.lighting/payment` → `@mark_priority(N)` → `@capture_failure`
- `cleanup_*` 必须传 `strict=False`
- autouse fixture 只放 conftest.py

### 测试数据
- 从 `config/config.yaml` 读取，**禁止硬编码**业务 ID
- 每个测试自动创建资源（region → fee → desk），teardown 清理
- 动态命名：`{前缀}_{时分秒}{1位随机}{worker}`，桌台名称上限 15 字

### 编码规范
- UTF-8 编码，文件头 `# -*- coding: utf-8 -*-`
- AAA 模式（Arrange → Act → Assert）
- 禁止 bare except
- 导入顺序：标准库 → 第三方 → 项目模块

### Allure
- 用 `allure.step` context manager
- 标题：`{中文名} | {HTTP方法} {路径}`
- docstring 第一行自动成为 Allure 标题

### API 客户端
- `APIClient.post(path, data, token, step_name, ...)` — step_name 是第4个位置参数
- `_SHORT_LOG_PATHS` 黑名单路径只记摘要

## 接口差异

| 维度 | Web（商户后台） | App（小程序端） |
|------|-----------------|-----------------|
| 路径前缀 | `merchant-api` | `app-api` |
| Token | 登录实时获取 | `xcx_token`（抓包） |

**混合模式**：Web 创建资源 + 开台绑定会员 → App 执行支付操作

**⚠️ PROD 环境 `app_host` 不要带 `/store` 后缀**

## 支付方式

| 类别 | 方式 | 说明 |
|------|------|------|
| 线下收款 | `cash` / `wx_offline` | 系统不追踪 |
| 拉卡拉 | 线下二维码 / 线上小程序 | 系统集成 |
| 余额 | `czk`（储值卡）/ `tfk`（台费卡） | 会员账户 |

## 业务模块文档索引

| 模块 | 文档路径 |
|------|----------|
| 支付规则 | `docs/business/payment_rules.md` |
| 优惠券规则 | `docs/business/coupon_rules.md` |
| 会员管理 | `docs/business/member_rules.md` |
| 桌台管理 | `docs/business/desk_management_rules.md` |
| 灯光控制 | `docs/business/lighting_control_rules.md` |

## 环境配置

- 环境切换：`config/config.yaml` 顶层 `env` 字段（UAT / PROD）
- 通知渠道：`notification_type`（0=关闭, 1=钉钉, 2=微信, 3=邮件, 4=飞书）
- 日志文件：`logs/YYYYMMDD/YYYYMMDDHHMMSS.log`
