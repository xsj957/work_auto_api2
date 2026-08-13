# 桌台管理系统规则详解

## 资源层级结构

```
区域（Region）
  └── 台费（Fee）
        └── 桌台（Desk）
```

**创建顺序**：区域 → 台费 → 桌台
**清理顺序**：桌台 → 台费 → 区域（逆序）

## 区域管理

### 区域属性

| 字段 | 说明 |
|------|------|
| regionNo | 区域编号（唯一标识） |
| regionId | 区域 ID |
| regionName | 区域名称 |

### 区域操作

| 操作 | 说明 |
|------|------|
| 创建区域 | 新增测试区域 |
| 查询校验区域 | 验证区域创建成功 |
| 删除区域 | 清理测试数据 |

## 台费管理

### 台费属性

| 字段 | 说明 |
|------|------|
| feeNo | 台费编号 |
| feeId | 台费 ID |
| feeName | 台费名称 |

### 台费规则

- 按时段计费（高峰/低峰不同价格）
- 按小时/分钟计费
- 可配置套餐价格

### 台费操作

| 操作 | 说明 |
|------|------|
| 创建台费 | 新增台费规则 |
| 查询校验台费 | 验证台费创建成功 |
| 删除台费 | 清理测试数据 |

## 桌台管理

### 桌台属性

| 字段 | 说明 |
|------|------|
| deskNo | 桌台编号 |
| deskId | 桌台 ID |
| deskName | 桌台名称 |
| regionNo | 所属区域 |
| feeNo | 关联台费 |

### 桌台状态

| 状态 | 说明 |
|------|------|
| 空闲 | 桌台未使用，可开台 |
| 使用中 | 已开台，计费中 |
| 已结账 | 订单完成，待清理 |

### 桌台操作

| 操作 | 说明 |
|------|------|
| 创建桌台 | 新增桌台，关联区域和台费 |
| 查询校验桌台 | 验证桌台创建成功 |
| 校验桌台空闲 | 确认桌台状态为空闲 |
| 删除桌台 | 清理测试数据 |

## 动态命名规则

创建的资源名称必须动态生成，格式：`{前缀}_{时分秒}{1位随机}{worker}`

```python
# ✅ 正确
suffix = _gen_suffix()  # "14564730" + "0" = 9位
region_name = f"测试区_{suffix}"     # 13字
desk_name = f"测试桌台_{suffix}_1"   # 15字（服务端上限15字）

# ❌ 错误
region_name = "灯控测试区域_20260727140000_12345"  # 超长，会被拒绝
```

**约束**：
- 桌台名称上限 15 字
- 确保每次执行唯一
- 并行安全

## Fixture 架构

### 单桌台 fixture

```
lighting_resources → region → fee → desk
```

适用于：大部分灯控测试（8个）

### 双桌台 fixture

```
lighting_resources_2 → region → fee1 + fee2 → desk1 + desk2
```

适用于：转台、并台测试

**注意**：两个桌台使用不同台费，避免服务端 `uk_order_active_fee` 唯一约束冲突

## 资源管理统一入口

所有资源的创建、验证、清理逻辑**统一在 `utils/test_helpers.py`**

```python
# ✅ 正确
from utils.test_helpers import create_region, verify_region, cleanup_region
region_id = create_region(api_client, token)

# ❌ 错误
response = api_client.post("/merchant-api/store/desk/region/create", {...})
```

### 清理注意事项

- 所有 `cleanup_*` 函数调用时**必须传 strict=False**
- 避免清理失败导致测试误报
