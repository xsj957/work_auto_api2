# 支付规则详解

## 支付方式分类

### 第一类：线下收款（系统不追踪支付状态）

| 代码 | 名称 | 说明 |
|------|------|------|
| `cash` | 现金支付 | 直接收现金，系统只记录"已收款"状态 |
| `wx_offline` | 微信线下支付 | 用户扫商家微信收款码，系统不知道支付详情，只记录已收款 |

**特点**：
- 这两种方式本质上都是"系统外支付"
- 系统只负责标记订单为已支付，不参与实际支付流程
- 不需要绑定会员
- 支付即完成，无回调处理

### 第二类：拉卡拉支付（系统集成）

| 场景 | 名称 | 说明 |
|------|------|------|
| 线下 | 拉卡拉线下支付 | 商户后台关台结账时，系统通过拉卡拉生成二维码，用户扫码支付，系统接收支付回调 |
| 线上 | 拉卡拉线上支付 | 用户在"小超开台"小程序中直接微信支付，系统接收支付回调 |

**特点**：
- 系统通过拉卡拉支付网关集成
- 能实时获取支付状态
- 支持自动对账
- 有支付回调处理流程

### 第三类：余额支付（会员账户扣款）

| 代码 | 名称 | 支付范围 | 需要绑定会员 |
|------|------|----------|--------------|
| `czk` | 储值卡（通用卡）余额支付 | 台费 + 商品 + 服务费 | 是 |
| `tfk` | 台费卡余额支付 | 仅台费 | 是 |

**关键区别**：
- **储值卡（通用卡）**：余额可用于多种费用类型的组合支付
- **台费卡**：余额只能用于支付台费，不能支付商品和服务费
- 余额支付需要先查询会员并绑定到桌台
- 支付时需要额外的 `channelExtras` 参数

## 支付流程

### 标准支付流程

```
1. 计时开台 → 等待计费（至少65秒）
2. 结账（closeDesk）→ 获取子订单号
3. 计算金额（pay）→ 获取应付金额
4. 创建支付单（payment/create）→ 获取 payOrderId
5. 提交支付（pay/order/submit）→ 使用对应的 channelCode
6. 支付后校验 → 确认桌台状态自动关闭
7. 关闭支付会话（cancelPay）
```

### 余额支付特殊流程

```
1. 查询会员（golfer/pageV2）
2. 绑定会员到桌台（desk/addGolfer）
3. 执行标准支付流程 1-7
4. 提交支付时需要 channelExtras 参数：
   {
     "flow_type": "1",
     "extra": {
       "orderType": "桌台订单",
       "givePrice": "0",
       "storeNo": STORE_NO,
       "couponName": "",
       "orderNo": order_no,
       "price": str(payment_price),
       "couponPrice": "0",
       "TfkGivenPrice": "0"
     },
     "golfer_no": golfer_no,
     "channelCode": channel_code
   }
```

## 支付相关字段

### 订单金额字段

| 字段 | 说明 |
|------|------|
| `totalAmount` | 订单总额 |
| `feePrice` | 台费 |
| `productPrice` | 商品金额 |
| `servePrice` | 服务费 |
| `actualPayMoney` | 实付金额 |
| `receivePayMoney` | 已收金额 |
| `noPayMoney` | 未付金额 |

### 支付记录字段

| 字段 | 说明 |
|------|------|
| `paymentList` | 支付记录列表 |
| `payTypeName` | 支付方式名称 |
| `paymentPrice` | 支付金额 |
| `paymentStatus` | 支付状态（success/fail） |
| `paymentStatusName` | 支付状态名称 |
| `payOrderId` | 支付单ID |

## 小程序端 vs 商户后台（Web）接口对比

### 核心原则

小程序端和商户后台的**支付接口路径、请求体、响应结构完全相同**，区别仅在于 **Base URL** 和 **Token**。

### 差异对比

| 维度 | 商户后台（Web） | 小程序端（App） |
|------|-----------------|-----------------|
| Base URL | `{host}/fast/merchant-api/...` | `{host}/fast/app-api/...` |
| 示例 | `https://uat.supervisionsstore.com/fast/merchant-api/store/desk/orders/createClockOpen` | `https://xczg.supervisions.cn/fast/app-api/store/desk/orders/createClockOpenV3` |
| Token | 登录接口实时获取（`auth_token`） | `xcx_token`（抓包获取，长期有效，写入 config.yaml） |
| Token 有效期 | 实时，过期自动重试 | 长期有效，但需手动抓包更新 |
| 接口路径 | `merchant-api` 前缀 | `app-api` 前缀 |
| 请求体 | 相同 | 相同 |
| 响应结构 | 相同 | 相同 |

### 注意事项

1. **PROD 环境 app_host 配置**：`app_host` 不要带 `/store` 后缀，否则 app-api 接口会 404
   ```yaml
   # ✅ 正确
   app_host: https://xczg.supervisions.cn
   # ❌ 错误
   app_host: https://xczg.supervisions.cn/store
   ```
2. **小程序端 token 不可自动获取**：`xcx_token` 只能通过抓包从小程序请求头中获取，写入 `config.yaml` 的 `business_data.xcx_token` 字段
3. **UAT 环境**：`xcx_token` 已在 config.yaml 中配置，有效期 7 天

---

### 混合调用模式（Web 建资源 + 小程序支付）

测试中常用模式：**Web 端创建资源 → 小程序端执行支付操作**

```
Web 端（merchant-api）:
  1. 创建区域/台费/桌台（fixture 自动完成）
  2. 计时开台（createClockOpen）
  3. 绑定会员（addGolfer）
  4. 等待计费 ≥ 65 秒

小程序端（app-api）:
  5. 关台（closeDesk）         ← 与 Web 端相同接口
  6. 计算金额（pay）           ← 与 Web 端相同接口
  7. 创建支付单（payment/create）← 与 Web 端相同接口
  8. 提交支付（pay/order/submit）← 与 Web 端相同接口
  9. 支付后校验
```

**关键**：步骤 5-9 的接口路径在两端完全相同，只需切换 Base URL（`merchant-api` → `app-api`）和 Token（`auth_token` → `xcx_token`）即可。

---

## 注意事项

1. **台费卡支付范围限制**：台费卡只能支付台费，不能支付商品和服务费
2. **储值卡通用性**：储值卡可以支付台费、商品、服务费的任意组合
3. **会员绑定**：余额支付必须先绑定会员到桌台
4. **支付回调**：拉卡拉支付有回调处理，需要等待回调完成
5. **组合支付**：支持多种支付方式组合（如优惠券+台费卡+现金）
