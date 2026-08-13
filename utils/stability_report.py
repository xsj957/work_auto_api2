# -*- coding: utf-8 -*-
"""
稳定性测试 - HTML 报告生成器
===========================
生成按轮次分组的 HTML 测试报告，包含：
- 每轮测试结果（通过/失败）
- 每轮 API 调用明细（请求URL、参数、响应）
- 每轮数据库断言结果
- 总体统计
"""

import json
import os
import re
from datetime import datetime


# ================================================================
#  测试用例英文 → 中文名称映射
# ================================================================
TEST_NAME_CN = {
    "test_clock_calorie_flow": "计时开台+卡钟测试",
    "test_miniprogram_flow": "小程序开台测试",
    "test_aa_golfer_workflow": "追加会员+AA结账测试",
    "test_combine_workflow": "并台流程测试",
    "test_turn_workflow": "转台流程测试",
    "test_pause_workflow": "暂停流程测试",
    "test_pending_workflow": "挂单流程测试",
    "test_recover_desk": "恢复关台测试",
    "test_recover_workflow": "恢复流程测试",
    "test_region_light_on": "区域全开灯测试",
    "test_region_light_off": "区域全关灯测试",
    "test_temp_light": "临时灯控测试",
}


def cn_test_name(raw_name):
    """
    将英文测试名转为中文

    支持参数化后缀：test_temp_light[temp_light_001] → 临时灯控测试 [temp_light_001]
    未命中映射时保留原名
    """
    m = re.match(r"^(\w+?)(\[.*\])?$", raw_name)
    if not m:
        return raw_name
    base = m.group(1)
    suffix = m.group(2) or ""
    cn = TEST_NAME_CN.get(base, base)
    return f"{cn} {suffix}" if suffix else cn


def generate_html_report(rounds_data, output_path, detail_rounds=10):
    """
    生成 HTML 报告

    Args:
        rounds_data: 轮次数据列表
        output_path: HTML 文件输出路径
        detail_rounds: 保留完整 API 明细的最近轮次数（默认 10）
            历史轮次只保留测试摘要 + 灯控断言，不展示 API 明细
    """
    total_rounds = len(rounds_data)
    # 计算哪些轮次需要展示完整 API 明细
    detail_start = max(0, total_rounds - detail_rounds)
    passed_rounds = sum(
        1 for r in rounds_data
        if r.get("db_assertion", {}).get("passed", False)
        and all(t.get("passed", False) for t in r.get("tests", []))
    )
    failed_rounds = total_rounds - passed_rounds

    # 统计所有测试
    total_tests = sum(len(r.get("tests", [])) for r in rounds_data)
    passed_tests = sum(
        1 for r in rounds_data
        for t in r.get("tests", [])
        if t.get("passed", False)
    )
    failed_tests = total_tests - passed_tests

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>灯控稳定性测试报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{
            text-align: center;
            padding: 30px 0;
            color: #1a1a2e;
            font-size: 28px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .summary-card .value {{
            font-size: 36px;
            font-weight: 700;
            margin: 8px 0;
        }}
        .summary-card .label {{
            color: #666;
            font-size: 14px;
        }}
        .pass {{ color: #27ae60; }}
        .fail {{ color: #e74c3c; }}
        .round {{
            background: white;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            overflow: hidden;
        }}
        .round-header {{
            padding: 16px 24px;
            background: #2c3e50;
            color: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .round-header h2 {{ font-size: 18px; }}
        .round-header .time {{ font-size: 13px; opacity: 0.8; }}
        .round-body {{ padding: 20px 24px; }}
        .section {{
            margin-bottom: 20px;
        }}
        .section h3 {{
            font-size: 15px;
            color: #2c3e50;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 2px solid #ecf0f1;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th {{
            background: #f8f9fa;
            padding: 10px 12px;
            text-align: left;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
        }}
        td {{
            padding: 8px 12px;
            border-bottom: 1px solid #eee;
            vertical-align: top;
        }}
        tr:hover {{ background: #f8f9fa; }}
        .badge {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-pass {{ background: #d4edda; color: #155724; }}
        .badge-fail {{ background: #f8d7da; color: #721c24; }}
        .params {{
            background: #f8f9fa;
            padding: 8px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            max-height: 120px;
            overflow-y: auto;
            word-break: break-all;
        }}
        .assertion-box {{
            padding: 12px 16px;
            border-radius: 8px;
            margin-top: 8px;
        }}
        .assertion-pass {{
            background: #d4edda;
            border-left: 4px solid #27ae60;
        }}
        .assertion-fail {{
            background: #f8d7da;
            border-left: 4px solid #e74c3c;
        }}
        .db-summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-top: 12px;
        }}
        .db-stat {{
            background: #f8f9fa;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }}
        .db-stat .num {{
            font-size: 24px;
            font-weight: 700;
            color: #2c3e50;
        }}
        .db-stat .desc {{
            font-size: 12px;
            color: #666;
        }}
        .collapsible {{
            cursor: pointer;
            user-select: none;
        }}
        .collapsible:hover {{ background: #e9ecef; }}
        .collapsible::before {{
            content: '\\25B6 ';
            display: inline-block;
            transition: transform 0.2s;
        }}
        .collapsible.active::before {{
            transform: rotate(90deg);
        }}
        .collapse-content {{
            display: none;
            padding: 12px 0;
        }}
        .collapse-content.show {{ display: block; }}
        .test-card {{
            margin-bottom: 16px;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            overflow: hidden;
        }}
        .test-card-header {{
            padding: 10px 14px;
            background: #f8f9fa;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .test-card-header:hover {{ background: #e9ecef; }}
        .test-card-header::before {{
            content: '\\25B6 ';
            display: inline-block;
            transition: transform 0.2s;
            font-size: 10px;
        }}
        .test-card-header.active::before {{
            transform: rotate(90deg);
        }}
        .failure-reason {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 8px 12px;
            margin: 8px 14px;
            border-radius: 4px;
            font-size: 12px;
            font-family: 'Consolas', monospace;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 200px;
            overflow-y: auto;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>灯控稳定性测试报告</h1>

        <!-- 总体统计 -->
        <div class="summary">
            <div class="summary-card">
                <div class="label">总轮次</div>
                <div class="value">{total_rounds}</div>
            </div>
            <div class="summary-card">
                <div class="label">通过轮次</div>
                <div class="value pass">{passed_rounds}</div>
            </div>
            <div class="summary-card">
                <div class="label">失败轮次</div>
                <div class="value fail">{failed_rounds}</div>
            </div>
            <div class="summary-card">
                <div class="label">总测试数</div>
                <div class="value">{total_tests}</div>
            </div>
            <div class="summary-card">
                <div class="label">通过测试</div>
                <div class="value pass">{passed_tests}</div>
            </div>
            <div class="summary-card">
                <div class="label">失败测试</div>
                <div class="value fail">{failed_tests}</div>
            </div>
        </div>
"""

    # 每轮详情
    for round_idx, rd in enumerate(rounds_data):
        round_num = rd.get("round_number", 0)
        start_time = rd.get("start_time", "")
        end_time = rd.get("end_time", "")
        duration = rd.get("duration_seconds", 0)
        tests = rd.get("tests", [])
        db_records = rd.get("db_records", [])
        db_assertion = rd.get("db_assertion", {})
        db_summary = rd.get("db_summary", {})

        # 是否为最近 N 轮（展示完整 API 明细）
        show_api_detail = round_idx >= detail_start

        round_passed = (
            db_assertion.get("passed", False)
            and all(t.get("passed", False) for t in tests)
        )
        badge = '<span class="badge badge-pass">PASS</span>' if round_passed else '<span class="badge badge-fail">FAIL</span>'

        html += f"""
        <!-- 第 {round_num} 轮 -->
        <div class="round">
            <div class="round-header">
                <h2>第 {round_num} 轮 {badge}</h2>
                <div class="time">
                    {start_time} ~ {end_time} | 耗时 {duration:.1f}s
                </div>
            </div>
            <div class="round-body">
"""

        # ── 测试结果表格（含失败原因列）──
        html += """
                <div class="section">
                    <h3>测试结果</h3>
                    <table>
                        <tr><th>测试用例</th><th>状态</th><th>耗时</th><th>失败原因</th></tr>
"""
        for t in tests:
            t_badge = '<span class="badge badge-pass">PASS</span>' if t.get("passed") else '<span class="badge badge-fail">FAIL</span>'
            t_duration = f"{t.get('duration', 0):.2f}s"
            cn_name = cn_test_name(t.get('name', 'N/A'))
            # 失败原因：优先 failure_reason（pytest断言），其次 db_assertion.message
            failure_reason = t.get("failure_reason", "")
            if not failure_reason and not t.get("passed"):
                db_msg = db_assertion.get("message", "")
                if db_msg:
                    failure_reason = db_msg
            # 截断过长的失败原因
            reason_display = ""
            if failure_reason:
                lines = failure_reason.strip().split("\n")
                # 取最后几行（通常是实际断言失败信息）
                reason_display = "\n".join(lines[-5:])[:300]
            html += f"""
                        <tr>
                            <td>{cn_name}</td>
                            <td>{t_badge}</td>
                            <td>{t_duration}</td>
                            <td style="color:#e74c3c;font-size:12px;max-width:400px;white-space:pre-wrap;word-break:break-all;">{_escape_html(reason_display)}</td>
                        </tr>
"""
        html += """
                    </table>
                </div>
"""

        # 从 round_data 获取两组数据
        api_records = rd.get("api_records", [])
        db_records = rd.get("db_records", [])
        tests = rd.get("tests", [])

        # ── 板块 1：API 调用明细（仅最近 N 轮展示完整明细）──
        if show_api_detail:
            html += f"""
                <div class="section">
                    <h3 class="collapsible" onclick="this.classList.toggle('active');this.nextElementSibling.classList.toggle('show')">
                        API 调用明细（{len(api_records)} 条 / {len(tests)} 个用例）
                    </h3>
                    <div class="collapse-content show">
"""
            # ── 所有测试用例卡片（循环内只关闭卡片，不关闭板块）──
            for t in tests:
                api_calls = t.get("api_calls", [])
                t_passed = t.get("passed", False)
                t_badge = '<span class="badge badge-pass">PASS</span>' if t_passed else '<span class="badge badge-fail">FAIL</span>'
                t_duration = f"{t.get('duration', 0):.2f}s"
                cn_name = cn_test_name(t.get('name', 'N/A'))

                # 失败原因（卡片内展示）
                failure_reason = t.get("failure_reason", "")
                if not failure_reason and not t_passed:
                    db_msg = db_assertion.get("message", "")
                    if db_msg:
                        failure_reason = db_msg

                html += f"""
                        <div class="test-card">
                            <div class="test-card-header"
                                 onclick="this.classList.toggle('active');this.nextElementSibling.classList.toggle('show')">
                                <strong>{cn_name}</strong>
                                {t_badge}
                                <span style="color:#888;font-size:12px">{t_duration}</span>
                                <span style="color:#888;font-size:12px">({len(api_calls)} 条 API)</span>
                            </div>
                            <div class="collapse-content" style="padding: 0;">
"""
                # 失败原因区块
                if failure_reason:
                    html += f"""
                                <div class="failure-reason">{_escape_html(failure_reason.strip()[:500])}</div>
"""

                if api_calls:
                    html += """
                                <table>
                                    <tr>
                                        <th>时间</th>
                                        <th>接口</th>
                                        <th>请求URL</th>
                                        <th>请求参数</th>
                                        <th>响应</th>
                                        <th>耗时</th>
                                        <th>状态</th>
                                    </tr>
"""
                    for r in api_calls:
                        status_badge = '<span class="badge badge-pass">成功</span>' if r.get("is_success") else '<span class="badge badge-fail">失败</span>'
                        params_json = json.dumps(r.get("body", r.get("params", {})), ensure_ascii=False, indent=2)[:500]
                        # 响应：优先 response_body，否则显示 code + msg
                        resp_body = r.get("response_body")
                        if resp_body:
                            response = str(resp_body)[:200]
                        else:
                            code = r.get("result_code", "")
                            msg = r.get("result_msg", "")
                            response = f"code={code}, msg={msg}" if code else "-"
                        op_name = r.get("operate_name", "") or r.get("url", "").rsplit("/", 1)[-1]

                        html += f"""
                                    <tr>
                                        <td style="white-space:nowrap">{r.get('create_time', '')}</td>
                                        <td>{op_name}</td>
                                        <td style="font-family:monospace;font-size:11px">{r.get('url', '')}</td>
                                        <td><div class="params">{_escape_html(params_json)}</div></td>
                                        <td><div class="params">{_escape_html(str(response)[:200])}</div></td>
                                        <td>{r.get('duration_ms', 0)}ms</td>
                                        <td>{status_badge}</td>
                                    </tr>
"""
                    html += "                                </table>"
                else:
                    html += '<p style="color:#999;padding:8px 14px">无 API 调用记录</p>'

                # 只关闭单个测试卡片
                html += """
                            </div>
                        </div>
"""
            # ── 循环结束后关闭板块 ──
            html += """
                    </div>
                </div>
"""
        else:
            # 历史轮次只显示摘要
            html += f"""
                <div class="section">
                    <h3>API 调用明细</h3>
                    <p style="color:#888;padding:4px 0">
                        共 {len(api_records)} 条 API 调用 / {len(tests)} 个用例
                        <span style="color:#aaa">（历史轮次仅保留摘要，最近 {detail_rounds} 轮展示完整明细）</span>
                    </p>
                </div>
"""

        # ─ 板块 2：灯控数据库断言 ─
        assertion_passed = db_assertion.get("passed", False)
        assertion_msg = db_assertion.get("message", "无断言数据")
        assertion_class = "assertion-pass" if assertion_passed else "assertion-fail"

        html += f"""
                <div class="section">
                    <h3>灯控数据库断言</h3>
                    <div class="assertion-box {assertion_class}">
                        {assertion_msg}
                    </div>
"""

        # 推送统计
        if db_summary:
            total = db_summary.get("total", 0)
            success = db_summary.get("success", 0)
            failed = db_summary.get("failed", 0)

            html += f"""
                    <div class="db-summary">
                        <div class="db-stat">
                            <div class="num">{total}</div>
                            <div class="desc">总灯控记录</div>
                        </div>
                        <div class="db-stat">
                            <div class="num pass">{success}</div>
                            <div class="desc">推送成功</div>
                        </div>
                        <div class="db-stat">
                            <div class="num fail">{failed}</div>
                            <div class="desc">推送失败</div>
                        </div>
                    </div>
"""

            # 按推送描述统计
            by_op = db_summary.get("by_operation", {})
            if by_op:
                html += """
                    <table style="margin-top: 12px;">
                        <tr><th>推送操作</th><th>总数</th><th>成功</th></tr>
"""
                for op, stats in by_op.items():
                    html += f"""
                        <tr>
                            <td>{op}</td>
                            <td>{stats['total']}</td>
                            <td class="pass">{stats['success']}</td>
                        </tr>
"""
                html += "                    </table>"

        # 每条灯控推送详情
        if db_records:
            html += """
                    <table style="margin-top: 12px;">
                        <tr>
                            <th>时间</th>
                            <th>推送描述</th>
                            <th>接口</th>
                            <th>设备/区域</th>
                            <th>耗时</th>
                            <th>状态</th>
                        </tr>
"""
            for r in db_records:
                status_badge = '<span class="badge badge-pass">成功</span>' if r.get("is_success") else '<span class="badge badge-fail">失败</span>'
                body = r.get("body", {})
                # 提取关键标识：设备ID 或 区域编号
                device_id = body.get("id", "") or body.get("regionNo", "") or "-"
                push_desc = r.get("push_desc", r.get("operate_name", ""))

                html += f"""
                        <tr>
                            <td style="white-space:nowrap">{r.get('create_time', '')}</td>
                            <td><strong>{push_desc}</strong></td>
                            <td style="font-family:monospace;font-size:11px">{r.get('url', '')}</td>
                            <td>{device_id}</td>
                            <td>{r.get('duration_ms', 0)}ms</td>
                            <td>{status_badge}</td>
                        </tr>
"""
            html += "                    </table>"

        html += "                </div>"

        html += """
            </div>
        </div>
"""

    # 页脚
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html += f"""
        <div class="footer">
            报告生成时间: {now} | 卓铭桌台管理系统 - 灯控稳定性测试
        </div>
    </div>

    <script>
        // 默认只展开轮次板块，测试卡片默认折叠（用户手动点击展开）
        document.querySelectorAll('.section > .collapsible').forEach(el => {{
            el.classList.add('active');
            el.nextElementSibling.classList.add('show');
        }});
    </script>
</body>
</html>
"""

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def _escape_html(text):
    """转义 HTML 特殊字符，防止 JSON 内容破坏页面结构"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
