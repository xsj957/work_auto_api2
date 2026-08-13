# 灯光控制系统规则详解

## 灯控业务流程

```
计时开台（clock open）
    ↓
手动卡钟（clock calorie）←→ 暂停/恢复（pause/recover）
    ↓
计时关台（clock close）
    ↓
生成订单 → 支付 → 完成
```

## 灯控功能列表

| 功能 | 代码标识 | 说明 |
|------|----------|------|
| 计时开台 | clock open | 开始计费，灯光自动开启 |
| 手动卡钟 | clock calorie | 暂停/恢复计时 |
| 计时关台 | clock close | 结束计费并生成订单 |
| 暂停/恢复 | pause/recover | 暂停灯控或恢复 |
| 转台 | turn desk | 将订单转移到另一个桌台 |
| 并台 | combine | 合并多个桌台的订单 |
| 小程序控制 | miniprogram | 通过小程序远程控制灯光 |
| 待客状态 | pending | 桌台处于待客准备状态 |

## 灯控测试场景

### 基础流程测试

1. **计时开台 → 手动卡钟 → 计时关台**
   - 验证计费准确性
   - 验证灯光状态同步

2. **暂停/恢复流程**
   - 暂停期间不计费
   - 恢复后继续计费

### 复杂场景测试

3. **转台流程**
   - 订单从桌台 A 转移到桌台 B
   - 验证台费计算连续性

4. **并台流程**
   - 多个桌台订单合并
   - 验证金额汇总正确性

5. **小程序控制**
   - 远程开台/关台
   - 验证小程序与后台状态同步

6. **待客状态**
   - 桌台预热准备
   - 验证状态流转

## 灯控 Fixture

### 单桌台 fixture

```python
lighting_resources = {
    'region_no': '区域编号',
    'fee_no': '台费编号',
    'desk_no': '桌台编号',
    'desk_id': '桌台ID',
    'fee_id': '台费ID',
    'region_id': '区域ID'
}
```

### 双桌台 fixture

```python
lighting_resources_2 = {
    'region_no': '区域编号',
    'fee1_no': '台费1编号',
    'fee2_no': '台费2编号',
    'desk1_no': '桌台1编号',
    'desk2_no': '桌台2编号',
    # ... 其他ID
}
```

## 灯控测试文件

| 文件 | 测试场景 |
|------|----------|
| `test_clock_calorie.py` | 计时开台 → 卡钟 → 关台 |
| `test_light_control.py` | 基础灯光控制 |
| `test_pause_workflow.py` | 暂停/恢复流程 |
| `test_recover_workflow.py` | 恢复流程 |
| `test_recover_desk.py` | 桌台恢复 |
| `test_turn_workflow.py` | 转台流程 |
| `test_combine_workflow.py` | 并台流程 |
| `test_miniprogram.py` | 小程序控制 |
| `test_pending_workflow.py` | 待客状态 |

## 灯控相关 API

| API | 说明 |
|-----|------|
| `/merchant-api/store/desk/orders/createClockOpen` | 计时开台 |
| `/merchant-api/store/desk/orders/createClockCalorie` | 手动卡钟 |
| `/merchant-api/store/desk/orders/createClockClose` | 计时关台 |
| `/merchant-api/store/desk/orders/pause` | 暂停 |
| `/merchant-api/store/desk/orders/recover` | 恢复 |
| `/merchant-api/store/desk/orders/turnDesk` | 转台 |
| `/merchant-api/store/desk/orders/combine` | 并台 |
