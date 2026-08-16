# Python 协程（asyncio）教程

> 以项目中 `test_duplicate_payment.py` 的高并发 submit 测试为例，从零教你理解和使用协程。

---

## 一、为什么需要协程？

### 场景：10000 次 HTTP 请求

假设你要对 `/pay/order/submit` 接口发送 10000 次请求，测试服务端是否能防住重复支付。

**方案 A：串行（不用协程）**
```python
for i in range(10000):
    response = requests.post(url, json=payload)  # 每次耗时 100ms
# 总耗时：10000 × 100ms = 1000 秒 ≈ 17 分钟
```
每次请求都在"等"网络响应，CPU 在空转。就像你打电话订餐，打完一个等对方确认，再打下一个。

**方案 B：多线程**
```python
from concurrent.futures import ThreadPoolExecutor

def send_request(i):
    response = requests.post(url, json=payload)

with ThreadPoolExecutor(max_workers=100) as pool:
    pool.map(send_request, range(10000))
# 总耗时：约 10~30 秒（取决于服务端）
```
100 个线程同时打电话。但每个线程占用 ~8MB 内存，10000 线程 = 80GB 内存，直接 OOM。

**方案 C：协程（asyncio）✅**
```python
async def send_request(session, i):
    async with session.post(url, json=payload) as resp:
        return await resp.json()

# 10000 个协程只占用几 MB 内存
results = await asyncio.gather(*[send_request(session, i) for i in range(10000)])
# 总耗时：约 3~10 秒
```
10000 个协程跑在 1 个线程上，内存占用极小。就像你同时给 10000 个人发短信，不用等回复，发完统一看结果。

### 三种并发方式对比

| 维度 | 串行 | 多线程 | 协程（asyncio） |
|------|------|--------|-----------------|
| 速度 | 最慢 | 快 | 最快（IO密集型） |
| 内存 | 最小 | 最大（每线程 ~8MB） | 小（每协程 ~几KB） |
| 适合场景 | 简单脚本 | 混合 CPU+IO | **纯 IO 密集型**（HTTP/数据库/文件） |
| 代码复杂度 | 最低 | 中 | 中（需要 async/await） |
| 本项目使用 | `api_client.post()` | — | `_async_submit()` 高并发测试 |

> **核心区别**：HTTP 请求 99% 的时间在等网络 IO。协程在等待时会自动切换去做别的事，不浪费 CPU。

---

## 二、30 秒理解 async/await

### 两个关键字

```python
async def 函数名():     # 定义一个协程函数（返回值变成"协程对象"）
    result = await 另一个协程()   # 等待另一个协程完成，期间去做别的事
```

### 规则

1. `async def` 定义的函数**不会立即执行**，返回一个"协程对象"
2. 必须用 `await` 或 `asyncio.run()` 来触发执行
3. `await` 只能在 `async def` 内部使用
4. 遇到 `await` 时，当前协程"暂停"，事件循环去执行其他协程

```python
# ❌ 错误：直接调用 async 函数不会执行
async def hello():
    print("hello")

hello()  # 什么都没发生，只返回一个协程对象，还有一个 RuntimeWarning

# ✅ 正确：用 asyncio.run() 启动
asyncio.run(hello())  # 输出: hello
```

---

## 三、拆解项目代码：从 0 到 10000 并发

下面以 `test_duplicate_payment.py` 的 `test_07` 为例，逐层讲解。

### 第 1 层：最基本的协程 — `_async_submit`

```python
# 文件: testcase/payment/test_duplicate_payment.py

async def _async_submit(session, url, payload, headers, fire):
    """异步并发 submit 协程。等待 fire 信号后同时发出请求。"""
    await fire.wait()                                    # ① 等待发令枪
    try:
        async with session.post(url, json=payload,       # ② 异步发 HTTP 请求
                                headers=headers, ssl=False) as resp:
            return await _safe_parse_response(resp)      # ③ 异步读响应
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        return {"code": -1, "msg": f"网络异常({type(e).__name__}): {str(e)[:150]}"}
```

**逐行解读**：

| 行 | 代码 | 含义 |
|----|------|------|
| ① | `await fire.wait()` | 等待一个"发令枪"信号。所有协程都停在这里，直到有人按下开关 |
| ② | `async with session.post(...)` | aiohttp 的异步 HTTP 请求。`async with` 确保请求完成后自动关闭连接 |
| ③ | `await _safe_parse_response(resp)` | 异步读取响应体并解析。等待期间 CPU 去做别的事 |

**关键点**：整个函数里没有任何 `time.sleep()` 或 `requests.post()` 这种"阻塞"调用。所有 IO 操作都是 `await` 的，所以等待网络时不会卡住其他协程。

### 第 2 层：发令枪模式 — `asyncio.Event`

```python
# 想象一下运动会赛跑：
# 10 个运动员站在起跑线上（10 个协程创建完毕）
# 裁判举枪（fire = asyncio.Event()）
# "砰！"（fire.set()）
# 10 个人同时起跑（10 个协程同时发出 HTTP 请求）

fire = asyncio.Event()       # 裁判举枪（初始状态：未就绪）

async def runner(name):
    await fire.wait()        # 运动员等待发令
    print(f"{name} 起跑！")

# 创建 10 个运动员
tasks = [runner(f"运动员{i}") for i in range(10)]

# 发令！
fire.set()                   # "砰！"所有 await fire.wait() 同时通过
```

**为什么需要发令枪？**

如果不加 `fire.wait()`，10000 个协程会**依次创建依次执行**，第一个请求都回来了最后一个还没发出去。加了发令枪后，所有协程先"排队站好"，然后同时发出去，真正模拟并发。

### 第 3 层：异步 HTTP 客户端 — `aiohttp.ClientSession`

```python
# requests 是同步的（阻塞）
import requests
response = requests.post(url, json=data)  # 这里会卡住，等网络响应

# aiohttp 是异步的（非阻塞）
import aiohttp
async with aiohttp.ClientSession() as session:
    async with session.post(url, json=data) as response:
        data = await response.json()      # 等待期间去做别的事
```

**`ClientSession` 的核心参数**（来自 test_07）：

```python
conn = aiohttp.TCPConnector(ssl=False, limit=0)
# ssl=False        → 不验证 SSL 证书（UAT 环境证书可能无效）
# limit=0          → 不限制并发连接数（默认 100，10000 并发需要放开）

timeout = aiohttp.ClientTimeout(total=15)
# total=15         → 单次请求最多 15 秒，超时自动取消

async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
    # session 在整个测试期间复用，内部维护连接池
    # 不需要每次请求都建立新的 TCP 连接（HTTP Keep-Alive）
```

### 第 4 层：收集结果 — `asyncio.gather`

```python
# 把 10000 个协程交给事件循环，等它们全部完成
results = await asyncio.gather(*tasks, return_exceptions=True)

# *tasks 是 Python 的解包语法：
# tasks = [task1, task2, task3, ...]
# *tasks = task1, task2, task3, ...
# gather(task1, task2, task3, ...) → 并发执行，返回结果列表

# return_exceptions=True → 某个协程抛异常不会中断其他协程
# 异常会作为结果列表中的一个元素返回（而不是向上抛出）
```

**对比**：
```python
# ❌ 不用 gather，串行执行
results = []
for task in tasks:
    results.append(await task)  # 一个接一个等，失去并发意义

# ✅ 用 gather，并发执行
results = await asyncio.gather(*tasks)  # 同时执行，全部完成后返回
```

### 第 5 层：在 pytest 中运行异步代码 — `_run_async`

pytest 测试函数是**同步的**（`def test_xxx`），但协程需要**异步环境**。`_run_async` 是桥梁：

```python
def _run_async(coro):
    """在同步上下文中运行异步协程（兼容 pytest 已有事件循环）。"""
    try:
        loop = asyncio.get_running_loop()     # 检查是否已在异步环境中
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # 情况 A：已有事件循环在跑（比如 pytest-asyncio 环境）
        # 开一个新线程来跑，避免"不能嵌套事件循环"的错误
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        # 情况 B：没有事件循环（普通 pytest 环境）
        # 直接创建一个新的事件循环
        return asyncio.run(coro)
```

**用法**：
```python
# 在同步的 pytest 测试函数中调用异步代码
def test_something():
    async def do_async_stuff():
        # ... 异步代码 ...
        pass
    
    results = _run_async(do_async_stuff())  # 桥接同步→异步
```

---

## 四、完整流程图：test_07 的 10000 并发

```
test_07_two_golfers_concurrent_submit (同步 pytest 函数)
│
├── 1. Web 端准备（同步，用 api_client）
│   ├── 创建区域 / 台费 / 桌台
│   ├── 绑定两个会员
│   ├── 计时开台 → 等待计费 → 关台
│   └── 创建支付单 → 得到 payOrderId
│
├── 2. 构造并发请求参数
│   ├── submit_payload = {id: payOrderId, channelCode: "tfk", ...}
│   └── headers = {Authorization: token, ...}
│
├── 3. _run_async(_do_stress())   ← 进入异步世界
│   │
│   └── async def _do_stress():
│       │
│       ├── fire = asyncio.Event()            # ① 准备发令枪
│       ├── conn = TCPConnector(limit=0)       # ② 不限连接数
│       ├── session = ClientSession(...)       # ③ 创建 HTTP 会话
│       │
│       ├── tasks = [                          # ④ 创建 10000 个协程
│       │     _async_submit(session, ..., fire)
│       │     for _ in range(10000)
│       │   ]
│       │   // 此时 10000 个协程都暂停在 await fire.wait()
│       │
│       ├── await asyncio.sleep(0.5)           # ⑤ 等半秒，确保所有协程就绪
│       │
│       ├── fire.set()                         # ⑥ "砰！" 发令！
│       │   // 10000 个协程同时被唤醒，同时发出 HTTP 请求
│       │
│       └── return await asyncio.gather(       # ⑦ 等所有协程完成
│               *tasks, return_exceptions=True
│           )
│
├── 4. 回到同步世界，分析结果
│   ├── success_count = 统计 code==200 的数量
│   ├── _summarize_results(results)            # 分类汇总
│   └── 校验余额是否正确扣款
│
└── 5. 清理资源（同步）
    ├── 删除桌台 / 台费 / 区域
    └── 完成
```

**时间线**：
```
0.0s   创建 10000 个协程，全部等待 fire
0.5s   fire.set() → 10000 个协程同时发出 HTTP 请求
0.5s ~ 3s   服务端处理中，协程在等待响应（CPU 空闲）
3s ~ 19s    响应陆续返回（服务端过载，有的快有的慢）
~19s   所有协程完成，gather 返回
```

---

## 五、自己动手：给小程序支付加一个并发测试

现在你已经理解了协程的基础，来看怎么在 `test_miniprogram_payment.py` 中复用这些能力。

### 需求：模拟多个用户同时用小程序支付同一桌台

```python
# 在 test_miniprogram_payment.py 末尾添加

import asyncio
import aiohttp
import json
from utils.debug_utils import info


async def _async_miniprogram_submit(session, url, payload, xcx_token, fire):
    """小程序端并发 submit 协程（使用 app-api 前缀 + xcx_token）"""
    await fire.wait()
    headers = {"Content-Type": "application/json", "Authorization": xcx_token}
    try:
        async with session.post(url, json=payload, headers=headers, ssl=False) as resp:
            raw = await resp.read()
            if not raw:
                return {"code": -resp.status, "msg": f"HTTP{resp.status} 空响应"}
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass
            text = raw.decode("utf-8", errors="replace")[:200]
            return {"code": -resp.status, "msg": f"HTTP{resp.status}: {text}"}
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        return {"code": -1, "msg": f"网络异常({type(e).__name__}): {str(e)[:150]}"}


@pytest.mark.regression
@pytest.mark.payment
@mark_priority(1)
@capture_failure
def test_miniprogram_concurrent_submit(api_client, auth_context):
    """小程序端并发 submit - 模拟多用户同时支付，检测重复扣款"""
    info("=" * 60)
    info("   小程序端并发支付测试")
    info("=" * 60)

    token = auth_context.token
    xcx_token = config.business_data.get("xcx_token", "")
    if not xcx_token:
        pytest.skip("小程序Token未配置")

    # ── Arrange: Web 端准备资源（和正常支付流程一样）──
    # ... 创建区域/台费/桌台/开台/绑定会员/关台 ...
    # ... 得到 child_order_no, total_amount, golfer_no ...
    # ... 创建支付单得到 pay_order_id ...

    # ── Act: 小程序端并发 submit ──
    CONCURRENCY = 100  # 100 个并发（比 test_07 少一些，因为小程序场景并发没那么大）

    submit_payload = {
        "id": pay_order_id,
        "channelCode": "tfk",
        "channelExtras": {
            "flow_type": "1",
            "extra": json.dumps({...}, ensure_ascii=False),
            "golfer_no": golfer_no,
        },
        "filter": {"storeNo": STORE_NO},
    }

    # 注意：小程序端用 app-api 前缀 + xcx_token
    base_url = config.host + "/fast"
    url_submit = f"{base_url}/app-api/pay/order/submit"  # ← 注意是 app-api

    async def _do_stress():
        fire = asyncio.Event()
        conn = aiohttp.TCPConnector(ssl=False, limit=0)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
            tasks = [
                _async_miniprogram_submit(session, url_submit, submit_payload, xcx_token, fire)
                for _ in range(CONCURRENCY)
            ]
            await asyncio.sleep(0.5)
            info(f"  发令！{CONCURRENCY} 个协程同时发出小程序 submit 请求...")
            fire.set()
            return await asyncio.gather(*tasks, return_exceptions=True)

    results = _run_async(_do_stress())
    results = [r for r in results if not isinstance(r, Exception)]

    success_count = sum(1 for r in results if r.get("code") == 200)
    info(f"  结果: 成功{success_count}次, 总计{len(results)}次")

    # ── Assert: 校验只扣款一次 ──
    time.sleep(3)
    # ... 校验余额、支付记录 ...
```

---

## 六、核心 API 速查表

| API | 作用 | 示例 |
|-----|------|------|
| `async def f()` | 定义协程函数 | `async def fetch(): ...` |
| `await coro()` | 等待协程完成 | `data = await resp.json()` |
| `asyncio.Event()` | 事件信号（发令枪） | `fire = asyncio.Event()` |
| `await event.wait()` | 等待事件触发 | `await fire.wait()` |
| `event.set()` | 触发事件（开枪） | `fire.set()` |
| `asyncio.gather(*tasks)` | 并发执行多个协程 | `await asyncio.gather(*[f() for _ in range(10)])` |
| `asyncio.sleep(n)` | 异步等待 n 秒（不阻塞） | `await asyncio.sleep(0.5)` |
| `asyncio.run(coro)` | 启动事件循环并运行协程 | `asyncio.run(main())` |
| `aiohttp.ClientSession()` | 异步 HTTP 客户端 | `async with aiohttp.ClientSession() as s:` |
| `aiohttp.TCPConnector(limit=0)` | 不限并发连接数 | `conn = aiohttp.TCPConnector(limit=0)` |
| `aiohttp.ClientTimeout(total=15)` | 请求超时 15 秒 | `timeout = aiohttp.ClientTimeout(total=15)` |

---

## 七、常见踩坑

### 坑 1：在同步代码里直接调用 async 函数

```python
# ❌ 错误
def test_xxx():
    result = _async_submit(...)  # 返回协程对象，不会执行！

# ✅ 正确
def test_xxx():
    result = _run_async(_async_submit(...))  # 用桥接函数启动
```

### 坑 2：在 async 函数里用同步阻塞调用

```python
# ❌ 错误：requests 是同步的，会阻塞整个事件循环
async def bad():
    response = requests.post(url, json=data)  # 10000 个协程排队等这一个请求

# ✅ 正确：aiohttp 是异步的
async def good():
    async with session.post(url, json=data) as response:
        data = await response.json()
```

### 坑 3：`time.sleep()` 阻塞事件循环

```python
# ❌ 错误：time.sleep 阻塞整个线程，所有协程都停了
async def bad():
    time.sleep(1)

# ✅ 正确：asyncio.sleep 只暂停当前协程
async def good():
    await asyncio.sleep(1)
```

### 坑 4：不限制连接数导致服务端过载

```python
# ⚠️ 默认 limit=100，10000 并发时不够
conn = aiohttp.TCPConnector()  # 默认 100

# ✅ 压测场景放开限制
conn = aiohttp.TCPConnector(limit=0)  # 0 = 不限制
```

### 坑 5：协程里忘写 `await`

```python
# ❌ 错误：没 await，fire.wait() 返回协程对象，不等待
async def bad():
    fire.wait()
    print("立刻执行了，没等发令枪！")

# ✅ 正确
async def good():
    await fire.wait()
    print("等到发令枪后才执行")
```

### 坑 6：`asyncio.gather` 一个失败全部取消

```python
# ❌ 默认行为：某个协程抛异常 → 其他协程全部被取消
results = await asyncio.gather(*tasks)

# ✅ 加 return_exceptions=True：异常作为结果返回，不中断其他协程
results = await asyncio.gather(*tasks, return_exceptions=True)
```

---

## 八、学习路径建议

1. **入门**：跑通 `python -c "import asyncio; asyncio.run(hello())"`
2. **理解**：读懂 `_async_submit` 每一行
3. **实践**：把 `test_07` 的 `CONCURRENCY` 改成 10，跑一遍看日志
4. **进阶**：尝试在 `test_miniprogram_payment.py` 里加一个并发测试
5. **深入**：理解 `asyncio.Event`、`asyncio.Lock`、`asyncio.Queue` 的用途

### 推荐资源

- [Python 官方 asyncio 文档](https://docs.python.org/3/library/asyncio.html)
- [aiohttp 文档](https://docs.aiohttp.org/)
- [Real Python: Async IO in Python](https://realpython.com/async-io-python/)
