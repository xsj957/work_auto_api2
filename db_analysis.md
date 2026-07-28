# 斯诺克大师国内App v1.0.0 — 数据库结构分析文档

> **分析范围**：supervisions + xczg 数据库，聚焦国内 App 视频制作相关业务表  
> **连接信息**：121.40.243.17:3306 (username: linjiakun)  
> **生成日期**：2026-07-28  
> **数据来源**：直接读取 information_schema 字段注释，所有说明均来自数据库实际定义

---

## 一、数据库概览

| 数据库 | 表数量 | 业务定位 |
|--------|--------|---------|
| **supervisions** | 214 张 | 核心业务库：视频、支付、用户、比赛 |
| **xczg** | 分库分表 | 桌台管理系统：订单、费用、支付记录 |
| **xczg_test** | 测试环境 | 与 xczg 结构相同的测试库 |
| **boss** | 后台管理 | 运营管理后台相关 |

---

## 二、视频业务核心表（supervisions 库）

### 2.1 表关系图

```
video_list (视频目录)
    │
    ├── video_order (视频解锁订单) ←→ video_combo_order (套餐订单)
    │       │                              │
    │       ├── video_coupon_record        └── video_combo (套餐定义)
    │       │
    │       ├── video_source (原片地址)
    │       ├── video_event (播放事件)
    │       ├── video_refund (退款记录)
    │       └── video_client_status (客户端状态)
    │
    └── video_price (定价规则)
```

---

### 2.2 video_list — 视频目录表（1438 条）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | bigint(20) unsigned zerofill | 自增主键，视频 ID |
| competition_id | varchar(36) | 赛 ID |
| inning_id | int | 局 ID |
| frame_index | int | 第几集直播（前台应用没有局 ID，所以存在第几集，从 1 开始） |
| **category** | varchar(255) | **视频分类**：如：精彩集锦 / 单杆30+ / 单杆50+ / 局视频等 |
| content | varchar(300) | 视频内容 |
| **price** | int | **视频价格（单位：分）** |
| **duration** | int | **时长（秒）** |
| create_time | datetime | 创建时间 |
| nickname_a | varchar(255) | 左方昵称 |
| nickname_b | varchar(255) | 右方昵称 |
| buy_times | int | 购买次数 |
| amount | int | 累计收款（单位：分） |
| **status** | int | **视频状态**：0=待解锁, 1=已购买, 2=已删除 |
| last_pay_time | datetime | 最后支付时间 |
| country_id / prov_id / city_id / area_id | int | 国家/省/市/区 ID |
| merchant_address_id | int | 商户地址 ID |
| table_number | varchar(64) | 桌台编号 |
| flag | bigint | 帧码，用于标识同一时刻的多个视频 |
| path | varchar(2600) | 源视频文件在工控机上的存储路径 |
| player | int | 0=左方, 1=右方 |
| live | int | 1=直播连接 |
| replay / replay_duration | int | 回放次数 / 回放视频时长 |
| break_score | int | 最高分 |
| turnover / turnover_duration | int | 失败次数 / 失败时长 |

---

### 2.3 video_order — 视频解锁订单表（1004 条）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | int | 自增主键，订单 ID（当前 1942） |
| user_id | varchar(36) | 用户 ID（关联 ten_user.id） |
| union_id | varchar(100) | 微信 UnionID |
| **video_id** | bigint | **视频 ID（video_list 的 ID）** |
| create_time | datetime | 创建时间 |
| pay_time | datetime | 支付时间 |
| **pay_status** | varchar(255) | **支付状态**：支付成功 / 支付失败 |
| url | varchar(300) | 视频观看地址 |
| wx_orderid | varchar(100) | 传给微信的订单编号 |
| amount | int | 支付金额（分） |
| transaction_id | varchar(40) | 微信支付订单号 |
| surplus | int | 1=多余的，同一用户点击多次购买就会产生多次订单信息 |
| **video_status** | tinyint | **视频状态**：1=工控机已生成, 2=工控机未合成 |
| remark | varchar(255) | 备注 |
| upload_time | datetime | 链接上传时间 |
| left_play_times | int | 剩余播放次数（默认 50） |
| size | int | 视频大小 MB |
| cover | varchar(300) | 封面 |
| duration | int | 时长（秒） |
| combo_order_id | bigint | 套餐订单号 |
| to_club_news | tinyint | 0=不推送, 1=推送到俱乐部动态 |
| is_viewed | tinyint(1) | 是否已观看：0=未观看, 1=已观看 |
| view_time | datetime | 首次观看时间 |
| asked_once | tinyint | 微信是否弹出过询问是否推送到俱乐部动态的对话框：0=未弹出, 1=已经弹过 |
| merchant_address_id | int | 商户地址 ID |
| **pay_channel** | tinyint | **支付渠道**：0=小程序android, 1=小程序ios, 2=app_android, 3=app_ios |
| **refund_status** | tinyint | **退款状态**：0=未退款, 1=已申请退款, 2=已退款, 3=退款失败 |
| bin_url | varchar(128) | 视频 bin 文件的 URL |

**当前数据分布**：
| video_status | pay_status | 数量 |
|-------------|-----------|------|
| 0 | 支付成功 | 879 |
| 0 | 未支付 | 117 |
| 0 | 空 | 6 |
| 0 | 支付失败 | 1 |
| 2 | 未支付 | 1 |

> **⚠️ 注意**：当前数据中 `video_status` 大部分为 0，与数据库注释"1=工控机已生成, 2=工控机未合成"不一致。0 可能是历史遗留值或新增的"待解锁"状态。国内 App 本地制作新增的状态（下载中/制作中/制作完成/制作失败）目前数据库中尚未出现。

---

### 2.4 video_combo — 视频券套餐定义表（3 条）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | int | 自增主键 |
| **price** | int | **价格（单位：分）** |
| **video_count** | int | **视频数量（券张数）** |
| **single_price** | int | **综合单价（分）** |
| **save_money** | int | **节省 X 元（分）** |
| status | int | 状态：1=正常, 0=无效 |
| display_order | int | 按从小到大排列 |
| **month** | int | **套餐有效期（X 个月）** |

**当前数据**：
| ID | price(分) | video_count | single_price(分) | save_money(分) | month |
|----|-----------|-------------|-----------------|---------------|-------|
| 1 | 100 (1元) | 3 | 330 | 2000 | 1 |
| 2 | 101 (约1元) | 12 | 250 | 9000 | 3 |
| 3 | 102 (约1元) | 60 | 200 | 48000 | 12 |

> **⚠️ 数据异常**：price 字段值为 100/101/102 分（约 1 元），与 PRD 文档的 9.9/29.9/118.8 元严重不符。可能是测试环境数据。

---

### 2.5 video_combo_order — 套餐订单表（2484 条）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | bigint | 自增主键 |
| combo_id | int | 套餐 ID |
| video_count | int | 套餐视频数 |
| used_count | int | 视频使用数量 |
| create_time | datetime | 创建时间 |
| pay_time | datetime | 支付时间 |
| pay_status | varchar(255) | 支付状态：支付成功 / 支付失败 |
| wx_orderid | varchar(100) | 传给微信的订单编号 |
| amount | int | 支付金额（单位：分） |
| transaction_id | varchar(40) | 微信支付订单号 |
| user_id | varchar(36) | 用户 ID（关联 ten_user.id） |
| union_id | varchar(100) | 微信 UnionID |
| **video_order_id** | int | **视频订单 ID** |
| **end_time** | datetime | **过期时间（23:59:59 之前）** |
| **channel** | int | **渠道类型**：2=H5, 其他值=小程序 |
| **pay_channel** | tinyint | **支付渠道**：0=android, 1=ios |
| **refund_status** | tinyint | **退款状态**：0=未退款, 1=已申请退款, 2=已退款, 3=退款失败 |

> **️ 注意**：`channel` 字段注释为"2=H5, 其他值=小程序"，**没有 App 的值**。App 端购买记录可能需要后端新增渠道值。`pay_channel` 只有 0/1 两个值（android/ios），与 `video_order.pay_channel` 的 0~3 四个值不同。

---

### 2.6 video_coupon_record — 视频券记录表（377 条）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | bigint | 自增主键，流水 ID |
| user_id | varchar(36) | 用户 ID |
| **coupon_id** | int | **优惠券 ID**：1=套餐的专享优惠券, 2=7天打卡活动的券（暂时没有其他优惠券类型） |
| draw_time | datetime | 领取时间 |
| end_date | datetime | 过期时间 |
| **status** | tinyint | **状态**：0=有效, 1=已使用, 2=已过期 |
| order_id | int | 对应视频订单 ID |

---

### 2.7 video_price — 视频定价规则表（60+ 条）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | int | 自增主键 |
| **category** | int | **视频分类**：1=局视频；30/40/50/60/70/80/90/100/110/120/130/140=对应单杆30+到单杆140+ |
| **base_price** | int | **基础价格（单位：分）** |
| **discount_price** | int | **优惠价格（单位：分）** |
| **discount** | int | **折扣，10 表示 1 折** |
| latest_begin_time | datetime | 最新优惠开始时间 |
| latest_end_time | datetime | 最新优惠结束时间 |
| **apply_times** | int | **最后应用次数**，用于恢复基础价格的操作。恢复时选中一条恢复，则将该批次的所有应用都恢复 |
| **is_regular** | int | **1=固定项目不能编辑，非1=可编辑** |
| create_time / create_user | datetime/varchar | 创建时间 / 创建人 |
| update_time / update_user | datetime/varchar | 更新时间 / 更新人 |

**定价规则**（`is_regular=1` 的常规价格）：
| category | 含义 | base_price(分) | base_price(元) |
|----------|------|---------------|---------------|
| 1 | 局视频 | 1000 | 10 |
| 30 | 单杆 30+ | 300 | 3 |
| 40 | 单杆 40+ | 400 | 4 |
| 50 | 单杆 50+ | 500 | 5 |
| 60 | 单杆 60+ | 600 | 6 |
| 70 | 单杆 70+ | 700 | 7 |
| 80 | 单杆 80+ | 800 | 8 |
| 90 | 单杆 90+ | 900 | 9 |
| 100 | 单杆 100+ | 1000 | 10 |
| 110 | 单杆 110+ | 1200 | 12 |
| 120 | 单杆 120+ | 1400 | 14 |
| 130 | 单杆 130+ | 1600 | 16 |
| 140 | 单杆 140+ | 1800 | 18 |

**折扣规则**（每个分类有多条折扣记录）：
| discount 值 | 含义 |
|------------|------|
| 10 | **1 折** |
| 20 | 2 折 |
| 30 | 3 折 |
| 40 | 4 折 |
| 50 | 5 折 |
| 70 | 7 折 |
| 90 | 9 折 |

> **🔴 重要修正**：`discount=10` 表示 **1 折**（原价的 10%），不是 9 折！折扣值直接代表折后百分比。

---

### 2.8 video_refund — 视频退款表（68 条）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | bigint | 自增主键 |
| create_time | datetime | 创建时间 |
| wx_orderid | varchar(100) | 传给微信的订单编号 |
| transaction_id | varchar(40) | 微信支付订单号 |
| combo_order_id | bigint | 套餐订单号 |
| out_refund_no | varchar(40) | 退款单号 |
| **status** | int | **状态**：0=待审核, 1=审核通过, 2=退款成功, 3=退款失败, 4=初审不通过 |
| auditor | varchar(255) | 审核人 |
| auditTime | datetime | 审核时间 |
| wx_refund_time | datetime | 微信退款回调时间 |
| wx_refund_result | varchar(1000) | 微信回调返回内容 |
| remark | varchar(255) | 备注 |
| amount | int | 退款额（分） |
| user_id | varchar(36) | 提交退款的用户 ID |
| order_id | bigint | 对应视频订单 ID |
| wx_notify_result | varchar(1000) | 退款通知接口收到的返回内容 |

---

### 2.9 video_source — 视频原片表

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | int | 自增主键，原片 ID |
| **order_id** | bigint | **视频 ID（video_list 的 ID）** |
| create_time | datetime | 创建时间 |
| **url_video** | varchar(400) | **视频地址**（腾讯云原片 URL） |
| **url_bin** | varchar(400) | **bin 地址** |

> **⚠️ 注意**：`order_id` 字段注释写的是"视频 ID video_list 的 ID"，而非订单 ID。该表存储工控机上传的原始视频片段地址，是 App 本地制作的源头。

---

### 2.10 video_client_status — 客户端视频状态表 🔴

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | bigint unsigned | 自增主键 |
| video_id | bigint unsigned | 视频 ID（video_list 的 ID） |
| **client_id** | varchar(64) | **客户端唯一标识（手机设备的 UDID）** |
| **status** | tinyint unsigned | **客户端视频状态**（见下表） |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

#### video_client_status.status 完整状态机

| 值 | 状态 | 说明 |
|----|------|------|
| 0 | **待解锁** | 视频已创建，等待用户解锁/付费 |
| 1 | **已解锁等待上传** | 用户已解锁，等待工控机上传原片到腾讯云 |
| 2 | 原片已上传 | 工控机已上传原片到腾讯云 |
| 3 | **下载中** | App 正在从腾讯云下载原片 |
| 4 | **下载失败** | 原片下载失败（网络/文件丢失） |
| 5 | **本地制作中** | App 正在本地制作视频（叠加比分条、头像等） |
| 6 | **制作失败** | 本地制作失败（素材丢失/App 不在前台） |
| 7 | **制作完成** | 成品视频已生成，可播放 |
| 8 | 已过期 | 视频已过期 |

> **🔴 之前文档全部写错**：数据库实际注释为"0-待解锁, 1-已解锁等待上传, 2-原片已上传, 3-下载中, 4-下载失败, 5-本地制作中, 6-制作失败, 7-制作完成, 8-已过期"。没有"审核"相关状态。

---

### 2.11 video_event — 视频播放事件表（138 条，埋点）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | bigint | 自增主键，事件 ID |
| **type** | tinyint | **事件类型**：1=播放 |
| **from_type** | tinyint | **事件来源**：1=工控机, 2=小程序 |
| **from_device** | varchar(128) | **事件来源设备**：工控机=devicesn, 小程序=userId |
| video_id | bigint | 视频来源 ID |
| event_time | datetime | 事件时间 |
| play_count | int | 播放次数 |
| play_ms | bigint | 播放时长（ms） |
| create_time | datetime | 创建时间 |

> **⚠️ 注意**：当前 `from_type` 只有 1（工控机）和 2（小程序），**缺少 App 端的来源值（3）**。国内 App 的埋点需要新增 `from_type=3`。

---

### 2.12 video_promotion — 视频促销活动表

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | int | 自增主键，活动 ID |
| start_time | datetime | 促销活动开始时间 |
| end_time | datetime | 促销活动结束时间 |
| **discount** | int | **折扣，一折就写 10，85 折就写 85** |
| status | int | 1=正常，其他值=停止 |

> **确认**：`discount=10` = 1 折，`discount=85` = 85 折。折扣值 = 折后百分比。

---

### 2.13 pay_order — 支付订单表（535 条）

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | int | 自增主键 |
| amount | int | 金额（单位：分） |
| **channel** | tinyint | **类型**：0=同个人账户间转账, 1=微信支付 |
| csm_group_id / csm_type / csm_user_id | int/tinyint/varchar | 付款方信息 |
| mch_group_id / mch_type / mch_user_id | int/tinyint/varchar | 收款方信息 |
| pay_order_no | varchar(36) | 支付订单号 |
| pay_wx_order_no | varchar(36) | 微信单号 |
| remark | varchar(255) | 备注 |
| **status** | tinyint | **状态**：0=预创建订单, 1=已支付, 2=退款成功, 3=退款中, 4=退款成功, 5=退款失败, 6=扣款失败, 7=超时 |
| time_expire / time_pay / time_start | datetime | 过期/支付/开始时间 |
| name | varchar(255) | 商品名 |

---

### 2.14 pay_cash_order — 现金支付订单表

| 字段 | 类型 | 说明（来自数据库注释） |
|------|------|------|
| id | int | 自增主键 |
| amount | int | 支付现金金额（分） |
| balance | int | 余额 |
| cash_order_no | varchar(36) | 支付订单号 |
| cash_wx_order_no | varchar(36) | 传给微信订单号 |
| remark | varchar(255) | 备注 |
| **status** | tinyint | **订单状态**：0=待支付, 1=等待退款, 2=退款成功, 3=退款失败 |
| **audit** | tinyint | **审核状态**：-1=未审核, 0=拒绝, 1=通过, 2=审核失败 |
| time_expire / time_start | datetime | 过期/开始时间 |
| user_id | varchar(255) | 用户 UnionID |
| nickname | varchar(255) | 微信昵称 |
| open_id | varchar(255) | 用户 OpenID |
| merchant_address_id | varchar(36) | 商户 ID |

---

## 三、桌台订单表（xczg 库）

### 3.1 分库分表结构

xczg 库采用**分库分表**策略，主要表按 `_0`、`_1`、`_2` 分片：

| 主表 | 分片表 | 说明 |
|------|--------|------|
| store_desk_orders | store_desk_orders_0/1/2 | 桌台订单 |
| store_desk_orders_fee | store_desk_orders_fee_0/1/2 | **订单费用记录** |
| store_desk_orders_desk | store_desk_orders_desk_0/1/2 | 订单桌台记录 |
| store_desk_orders_coupon | store_desk_orders_coupon_0/1/2 | 订单优惠券记录 |
| store_desk_orders_golfer | store_desk_orders_golfer_0/1/2 | 订单球手记录 |
| store_desk_orders_payment | store_desk_orders_payment_0/1/2 | 订单支付记录 |
| store_desk_orders_product | store_desk_orders_product_0/1/2 | 订单商品记录 |
| store_desk_orders_serve | store_desk_orders_serve_0/1/2 | 订单服务记录 |

### 3.2 store_desk_orders_fee — 订单费用记录表 🔴

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint unsigned | 主键 |
| **order_no** | varchar(64) | **订单号** |
| store_no | varchar(64) | 门店号 |
| device_sn | varchar(100) | 设备序列号 |
| fee_price | decimal(10,2) | 台费价格 |
| is_share | tinyint unsigned | 是否共享 |
| share_price | decimal(10,2) | 共享价格 |
| fee_time | int unsigned | 台费时间（分钟） |
| golfer_no | varchar(64) | 球手编号 |
| stop_time | int unsigned | 暂停时间 |
| begin_time / end_time | datetime | 开始/结束时间 |
| fee_rule | json | 台费规则 |
| desk_no | varchar(64) | 桌台编号 |
| system_type | varchar(32) | 系统类型 |
| pause_record / pause_count | json/int | 暂停记录 / 暂停次数 |
| sub_no | varchar(100) | 子订单号 |
| reduced_price | decimal(10,2) | 优惠价格 |
| refund_price | decimal(10,2) | 退款价格 |
| open_desk_type | tinyint unsigned | 开台类型 |
| order_type | varchar(32) | 订单类型 |
| settle_time | datetime | 结算时间 |
| discount_price | decimal(10,2) | 折扣价格 |
| src_order_price | decimal(10,2) | 源订单价格 |
| remark | varchar(100) | 备注 |
| sub_final | tinyint unsigned | 子订单最终状态 |
| buying_no | varchar(100) | 购买编号 |
| segment_id / segment_rule_fee_price / segment_rule_fee_time | ... | 分段计费相关字段 |
| segment_stop_time / segment_rule / segment_unit_time | ... | 分段计费相关字段 |
| user_discount | tinyint unsigned | 用户折扣 |
| **only_one_active** | tinyint | **唯一活跃标记** |

#### 🔴 关键唯一键约束

```sql
UNIQUE KEY uk_order_active_fee (order_no, only_one_active)
```

**约束含义**：每个订单 `(order_no)` 只能有**一条** `only_one_active=1` 的费用记录。

**🔴 这是并台/转台测试失败的根本原因**：
- 桌台 1 开台 → 订单 A 有一条 `only_one_active=1` 的费用记录
- 桌台 2 开台 → 订单 B 有一条 `only_one_active=1` 的费用记录
- 并台时，尝试将订单 B 的费用记录转移到订单 A
- 但订单 A 已经有 `only_one_active=1` 的记录 → **违反唯一键约束** → 报错

**服务端应修复方案**：
1. 并台时，先将订单 A 的活跃费用记录标记为 `only_one_active=0`
2. 再将订单 B 的费用记录转移到订单 A 并设置为 `only_one_active=1`
3. 或合并两条费用记录（累加金额）

---

## 四、国内 App 业务数据流分析

### 4.1 视频解锁流程

```
用户点击解锁视频
    │
    ├── 用券解锁 → video_coupon_record.status 更新 (0→1)
    │                  ↓
    │              video_order 创建记录 (pay_status=支付成功)
    │                  ↓
    │              通知工控机上传原片 → video_source 插入记录
    │              video_client_status 更新 (0→1→2)
    │
    └── 付费解锁 → pay_order 创建支付订单 (status=0 预创建)
                       ↓
                   微信支付/IAP 支付
                       ↓
                   pay_order 更新 (status=1 已支付)
                   video_order 更新 (pay_status=支付成功)
                       ↓
                   通知工控机上传原片 → video_source 插入记录
```

### 4.2 视频制作完整状态流转

```
video_client_status.status 完整状态机:

  0 (待解锁)
    ↓ 用户解锁/付费
  1 (已解锁等待上传)
    ↓ 工控机上传原片
  2 (原片已上传)
    ↓ App 开始下载原片
  3 (下载中)
    ├→ 5 (本地制作中) ← 下载成功
    └→ 4 (下载失败) ← 下载失败
  5 (本地制作中)
    ├→ 7 (制作完成) ← 正常完成
    → 6 (制作失败) ← 失败
  8 (已过期) ← 任何阶段超时（48h/90d/缓存清除）

video_order.video_status（数据库注释）:
  1 = 工控机已生成
  2 = 工控机未合成
  ⚠️ 当前数据大量为 0，需与后端确认含义
```

### 4.3 支付渠道区分

```
video_order.pay_channel:
  0 = 小程序 android
  1 = 小程序 ios
  2 = app_android       ← 国内 App 安卓端应写入此值
  3 = app_ios           ← 国内 App iOS 端应写入此值

video_combo_order.pay_channel:
  0 = android
  1 = ios
  ⚠️ 只有两个值，与 video_order 不一致

video_combo_order.channel:
  2 = H5
  其他值 = 小程序
  ⚠️ 没有 App 的渠道值，需后端新增

pay_order.channel:
  0 = 同个人账户间转账
  1 = 微信支付
  ⚠️ 没有 IAP 支付渠道值，需后端新增
```

**⚠️ 测试关注点**：
- App 端购买记录应正确写入 `video_order.pay_channel=2`（android）或 `3`（ios）
- `video_combo_order.channel` 和 `pay_order.channel` 缺少 App 渠道值
- 后台筛选"购买渠道"功能依赖 `video_order.pay_channel` 字段
- 历史数据均为 `pay_channel=0` 或 `1`（小程序）

### 4.4 折扣规则

```
video_price.discount / video_promotion.discount:
  10 = 1 折（原价的 10%）
  20 = 2 折
  50 = 5 折
  85 = 85 折
  90 = 9 折

规则：discount 值 = 折后百分比，不是折扣幅度
```

---

## 五、关键发现与风险点总结

### 6.1 🔴 并台/转台唯一键冲突（服务端 bug）

| 项目 | 详情 |
|------|------|
| **问题** | `uk_order_active_fee` 唯一键约束在 `(order_no, only_one_active)` |
| **影响** | 并台/转台操作时，两个订单的活跃费用记录冲突 |
| **根因** | 服务端未处理费用记录合并逻辑 |
| **建议** | 服务端修复：并台时先标记旧记录为非活跃，再转移新记录 |

### 6.2 🔴 折扣理解错误（已修正）

| 项目 | 详情 |
|------|------|
| **问题** | 文档曾将 `discount=10` 误写为"9 折" |
| **实际** | `discount=10` = **1 折**（原价的 10%），discount 值 = 折后百分比 |
| **影响** | 测试用例中的价格计算逻辑需要修正 |
| **建议** | 所有涉及折扣的测试点以数据库注释为准 |

### 6.3 🔴 video_client_status 完整状态机（新发现）

| 项目 | 详情 |
|------|------|
| **发现** | `video_client_status.status` 有 9 个状态值（0~8） |
| **意义** | 这是 App 本地制作的核心状态跟踪表 |
| **建议** | 测试用例应覆盖完整状态流转：0→1→2→3→5→7（正常）、3→4（下载失败）、5→6（制作失败） |

### 6.4 🟡 video_event 缺少 App 来源值

| 项目 | 详情 |
|------|------|
| **问题** | `from_type` 只有 1（工控机）和 2（小程序） |
| **影响** | App 端播放埋点无法区分来源 |
| **建议** | 后端新增 `from_type=3` 表示 App 端 |

### 6.5 🟡 video_combo_order.channel 缺少 App 值

| 项目 | 详情 |
|------|------|
| **问题** | `channel` 字段注释为"2=H5, 其他值=小程序"，没有 App 值 |
| **影响** | App 端购买视频券的渠道记录不准确 |
| **建议** | 后端新增渠道值表示 App |

### 6.6 🟡 视频券套餐价格数据异常

| 项目 | 详情 |
|------|------|
| **问题** | video_combo 表中 price 字段值为 100/101/102 分（约 1 元） |
| **预期** | PRD 文档要求 9.9 元/29.9 元/118.8 元 |
| **建议** | 确认是测试环境数据还是字段含义不同 |

### 6.7 🟢 定价规则完整

| 项目 | 详情 |
|------|------|
| **发现** | video_price 表包含所有单杆分数段的定价规则 |
| **覆盖** | 局视频 + 单杆 30+~140+ 共 13 个分类，与 PRD 一致 |
| **建议** | App 端读取 `is_regular=1` 的记录作为定价依据 |

---

## 六、数据库与测试点对应关系

| 测试点模块 | 相关数据库表 | 关键验证字段 |
|-----------|-------------|-------------|
| 视频解锁 | video_order, video_list | pay_status, video_status, amount |
| 视频券购买 | video_combo, video_combo_order, video_coupon_record | price, video_count, end_time, status |
| 付费解锁 | video_order, pay_order | pay_channel, amount, pay_status |
| 视频定价 | video_price | category, base_price, discount, is_regular |
| 退款 | video_refund, video_order | status(0~4), refund_status(0~3) |
| 视频制作状态 | video_client_status, video_source | status(0~8), url_video |
| 播放埋点 | video_event | type, from_type, play_count, play_ms |
| 后台渠道筛选 | video_order, video_combo_order | pay_channel, channel |
| 促销活动 | video_promotion | discount(10=1折), status |

---

## 附录：表结构快速参考

### A. supervisions 库视频相关表

| 表名 | 记录数 | 核心用途 |
|------|--------|---------|
| video_list | 1,438 | 视频目录/元数据 |
| video_order | 1,004 | 视频解锁订单 |
| video_combo | 3 | 套餐定义 |
| video_combo_order | 2,484 | 套餐订单 |
| video_coupon_record | 377 | 视频券记录 |
| video_event | 138 | 播放事件埋点 |
| video_price | 60+ | 定价规则 |
| video_refund | 68 | 退款记录 |
| video_source | - | 原片地址 |
| video_client_status | - | 客户端状态（0~8 共 9 个状态） |
| video_promotion | - | 促销活动 |
| pay_order | 535 | 支付订单 |
| pay_refund | 0 | 支付退款 |
| pay_cash_order | - | 现金支付订单 |

### B. xczg 库桌台订单相关表

| 表名 | 核心用途 |
|------|---------|
| store_desk_orders | 桌台订单主表 |
| store_desk_orders_fee | **订单费用记录（含 uk_order_active_fee 唯一键）** |
| store_desk_orders_desk | 订单桌台关联 |
| store_desk_orders_coupon | 订单优惠券记录 |
| store_desk_orders_golfer | 订单球手记录 |
| store_desk_orders_payment | 订单支付记录 |
| store_desk_orders_product | 订单商品记录 |
| store_desk_orders_serve | 订单服务记录 |
