# -*- coding: utf-8 -*-
"""
测试运行入口
============
一键运行测试并打开 Allure 报告。
每次执行自动归档到 reports/archive/YYYYMMDD_HHMMSS/，历史报告永不丢失。

用法：
    python run.py                  # 运行全部测试 + 打开报告
    python run.py --no-report      # 只运行测试，不打开报告
    python run.py --smoke          # 只运行 smoke 测试
    python run.py --payment        # 只运行支付模块测试
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent
REPORT_DIR = ROOT / "reports" / "allure-results"
ARCHIVE_DIR = ROOT / "reports" / "archive"
HTML_DIR = ROOT / "reports" / "html"
HISTORY_DIR = HTML_DIR / "history"  # allure 趋势数据


def write_allure_report_files():
    """
    生成 Allure 报告辅助文件
    ========================
    1. environment.properties — 环境信息（显示在报告首页）
    2. categories.json — 失败分类（区分服务器错误 / 业务校验失败 / 环境问题）
    """
    from utils.config import config

    # ---- environment.properties ----
    env_props = [
        "Environment=UAT",
        f"BaseURL={config.host}",
        f"AppURL={config.get('app_host', config.host)}",
        "TestFramework=Pytest+Allure",
        f"Tester={config.get('tester_name', '接口探')}",
        f"ProjectName={config.get('project_name', '卓铭桌台管理系统')}",
    ]
    env_path = REPORT_DIR / "environment.properties"
    env_path.write_text("\n".join(env_props) + "\n", encoding="utf-8")

    # ---- categories.json ----
    categories = [
        {
            "name": "服务器内部错误",
            "matchedStatuses": ["broken"],
            "messageRegex": ".*code=500.*",
        },
        {
            "name": "业务校验失败",
            "matchedStatuses": ["failed"],
            "messageRegex": ".*code=400.*",
        },
        {
            "name": "环境问题（网络/连接）",
            "matchedStatuses": ["broken"],
            "messageRegex": ".*(ConnectionError|Timeout|SSLError|RequestException).*",
        },
        {
            "name": "断言失败",
            "matchedStatuses": ["failed"],
            "messageRegex": ".*(AssertionError|assert|断言失败).*",
        },
    ]
    import json
    cat_path = REPORT_DIR / "categories.json"
    cat_path.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  [OK] 报告辅助文件已生成: environment.properties + categories.json")


def main():
    parser = argparse.ArgumentParser(description="运行测试并生成 Allure 报告")
    parser.add_argument("--no-report", action="store_true", help="只运行测试，不打开报告")
    parser.add_argument("--smoke", action="store_true", help="只运行 smoke 测试")
    parser.add_argument("--payment", action="store_true", help="只运行支付模块测试")
    parser.add_argument("--lighting", action="store_true", help="只运行灯光模块测试")
    parser.add_argument("-k", type=str, default="", help="pytest -k 表达式，如 -k cash_payment")
    args = parser.parse_args()

    # 1. 清理上次 allure-results，避免历史数据混入
    if REPORT_DIR.exists():
        shutil.rmtree(REPORT_DIR, ignore_errors=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 1.1 保留上次报告的历史趋势数据（用于趋势图表）
    if HISTORY_DIR.exists():
        shutil.copytree(HISTORY_DIR, REPORT_DIR / "history")
        print(f"  [OK] 已加载历史趋势数据")

    # 1.2 生成报告辅助文件（environment.properties + categories.json）
    write_allure_report_files()

    # 2. 构建 pytest 命令
    cmd = [sys.executable, "-m", "pytest", f"--alluredir={REPORT_DIR}", "-v"]

    if args.smoke:
        cmd += ["-m", "smoke"]
    elif args.payment:
        cmd.append(str(ROOT / "testcase" / "payment"))
    elif args.lighting:
        cmd.append(str(ROOT / "testcase" / "lighting"))

    if args.k:
        cmd += ["-k", args.k]

    # 3. 运行测试
    print("=" * 60)
    print("运行测试...")
    print("=" * 60)
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print(f"\n测试有失败项（退出码: {result.returncode}）")

    # 4. 归档本次结果 + 生成静态 HTML
    if not args.no_report:
        # 4.1 归档 allure-results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = ARCHIVE_DIR / timestamp
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        if any(REPORT_DIR.iterdir()):
            shutil.copytree(REPORT_DIR, archive_path)
            print(f"\n  [OK] 本次结果已归档: {archive_path}")
        else:
            print("\n  [WARN] allure-results 为空，跳过归档")

        # 4.2 生成静态 HTML 报告
        print("\n" + "=" * 60)
        print("生成 Allure 报告...")
        print("=" * 60)
        allure_cmd = shutil.which("allure") or shutil.which("allure.bat")
        if not allure_cmd:
            print("  [WARN]  allure 命令未找到！请安装 Allure CLI：")
            print("     npm install -g allure-commandline")
            print("  或手动生成报告：")
            print(f"     allure generate {REPORT_DIR} -o {HTML_DIR} --clean")
        else:
            # 生成静态 HTML（永久保留，history 趋势自动延续）
            subprocess.run(
                [allure_cmd, "generate", str(REPORT_DIR),
                 "-o", str(HTML_DIR), "--clean"],
                cwd=str(ROOT),
            )
            print(f"  [OK] 静态报告: {HTML_DIR / 'index.html'}")
            print(f"  [OK] 趋势数据已更新: {HISTORY_DIR}")


if __name__ == "__main__":
    main()
