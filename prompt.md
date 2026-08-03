---
  💡 使用示例

  你只需要这样告诉我：

  帮我新增一个测试用例：

  用例名称：定时开关台
  所属模块：lighting
  优先级：P1
  冒烟测试：否

  接口路径：/merchant-api/store/desk/orders/createClockOpen
  请求参数：
 {"deskNo":"SD202607272313572019","hour":"0.0167","filter":{"storeNo":"732739"}}

  响应参数:

 {"code":200,"data":"ZT00002026080322443657","msg":"成功"}

  期望响应码：200
  期望响应消息包含：成功
  需要提取：order_no = data



  前置依赖：需要新增桌台/台费/区域



  我会自动生成完整的测试代码，符合项目所有规范（AAA 模式、动态命名、断言链、日志、Allure 步骤等）。



最终结果】我需要你交付：

1. 一个完整的 Python 测试文件（test_xxx.py）
  2. 文件放到 testcase/lighting/ 目录下
  3. 包含定时开台不同时间段比如1分钟/3分钟/1小时/10小时
  4. 每个测试方法有完整的 docstring
  5. 代码可以直接 pytest 运行，不需要我再修改