"""生成 README 用的终端演示动画 SVG（assets/demo.svg）。

用 mcd-host 自己的 demo 数据渲染一段「打字机效果」的终端会话：
命令逐字打出 → 方案逐行出现 → 应付/人均高亮。纯 SVG + CSS 动画，
自包含（无外部字体/图片/脚本），遵守 prefers-reduced-motion。

用法：
    python scripts/make_demo_svg.py            # 写到 assets/demo.svg
    python scripts/make_demo_svg.py -o out.svg
"""

from __future__ import annotations

import argparse
import html
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcd_host.card import _yuan  # noqa: E402
from mcd_host.demo import demo_coupons_payload, demo_menu_payload, demo_nutrition_payload  # noqa: E402
from mcd_host.model import PlanRequest, normalize_coupons, normalize_menu  # noqa: E402
from mcd_host.planner import build_plan  # noqa: E402

_COMMAND = "mcd-host demo --people 6 --budget 300"

_STYLE = """
  .term { fill: #1C1B1A; }
  .bar { fill: #2A2825; }
  .dot-r { fill: #FF5F57; }
  .dot-y { fill: #FEBC2E; }
  .dot-g { fill: #28C840; }
  .prompt { fill: #5DCAA5; font: 400 13px var(--mono); }
  .cmd { fill: #F1EFE8; font: 400 13px var(--mono); }
  .head { fill: #EF9F27; font: 500 14px var(--mono); }
  .out { fill: #C9C6BC; font: 400 13px var(--mono); }
  .dim { fill: #8A8779; font: 400 13px var(--mono); }
  .pay { fill: #F1EFE8; font: 500 15px var(--mono); }
  .per { fill: #EF9F27; font: 500 15px var(--mono); }
  .title { fill: #8A8779; font: 400 12px var(--mono); }
  .line { opacity: 0; animation: show .01s linear forwards; }
  .cursor { fill: #EF9F27; animation: blink 1s steps(1) infinite; }
  .wipe { fill: #1C1B1A; transform-origin: right center; animation: wipe 1.6s steps(30) .3s forwards; }
  .flash { opacity: 0; animation: flash .5s ease-out forwards; }
  @keyframes show { to { opacity: 1; } }
  @keyframes blink { 50% { opacity: 0; } }
  @keyframes wipe { from { transform: scaleX(1); } to { transform: scaleX(0); } }
  @keyframes flash { 0% { opacity: 0; } 30% { opacity: 1; } 100% { opacity: 1; } }
  @media (prefers-reduced-motion: reduce) {
    .line, .flash { opacity: 1; animation: none; }
    .wipe { display: none; }
    .cursor { animation: none; }
  }
"""


def build_demo_svg() -> str:
    menu = normalize_menu(demo_menu_payload())
    coupons = normalize_coupons(demo_coupons_payload())
    plan = build_plan(menu, coupons, PlanRequest(people=6, budget=30000, occasion="dinner"), demo_nutrition_payload())

    lines = []  # (delay_seconds, css_class, text)
    delay = 2.1
    step = 0.16

    def add(cls: str, text: str, gap: float = step) -> None:
        nonlocal delay
        lines.append((delay, cls, text))
        delay += gap

    add("head", "麦门东道主 · 请客参谋", 0.28)
    add("dim", "一桌菜（6 人 · 晚饭）", 0.24)
    for line in plan.lines:
        name = line.name if len(line.name) <= 9 else line.name[:8] + "…"
        text = f"  {name}（{'套餐' if line.kind == 'set' else line.kind}）×{line.qty}"
        text = text.ljust(30) + _yuan(line.total)
        add("out", text)
    add("dim", "", 0.12)
    add("out", f"  小计".ljust(30) + _yuan(plan.subtotal), 0.14)
    if plan.coupon is not None:
        add("out", f"  优惠（{plan.coupon.name}）".ljust(24) + f"-{_yuan(plan.coupon_saving)}", 0.14)
    add("pay", f"  应付".ljust(28) + _yuan(plan.payable), 0.14)
    add("per", f"  人均".ljust(28) + _yuan(plan.per_person), 0.14)
    add("dim", f"  人均约 {plan.calories_per_person} 千卡 · 分享卡片已生成", 0.14)

    body_height = 40 + 30 + 16 + len(lines) * 22 + 46
    height = max(body_height, 420)

    rows = []
    y = 96
    for index, (at, cls, text) in enumerate(lines):
        safe = html.escape(text)
        classes = cls + (" line flash" if cls in ("pay", "per") else " line")
        rows.append(
            f'<text x="28" y="{y}" class="{classes}" style="animation-delay:{at:.2f}s">{safe}</text>'
        )
        y += 22

    cmd_len = len(_COMMAND)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 {height}" width="100%" role="img">
  <title>mcd-host 终端演示</title>
  <desc>打字机效果演示：运行 mcd-host demo，自动生成 6 人请客方案</desc>
  <style>
    :root {{ --mono: "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", "Courier New", monospace; }}
    {_STYLE}
  </style>
  <rect class="term" x="0" y="0" width="680" height="{height}" rx="12"/>
  <rect class="bar" x="0" y="0" width="680" height="36" rx="12"/>
  <rect class="bar" x="0" y="24" width="680" height="12"/>
  <circle class="dot-r" cx="20" cy="18" r="5"/>
  <circle class="dot-y" cx="38" cy="18" r="5"/>
  <circle class="dot-g" cx="56" cy="18" r="5"/>
  <text class="title" x="340" y="22" text-anchor="middle">mcd-host — zsh — 80×24</text>

  <text class="prompt" x="28" y="66">$</text>
  <text class="cmd" x="46" y="66">{html.escape(_COMMAND)}</text>
  <rect class="wipe" x="46" y="52" width="{cmd_len * 7.8:.0f}" height="22"/>
  <rect class="cursor" x="{46 + cmd_len * 7.8 + 6:.0f}" y="54" width="8" height="16" style="animation-delay:2.0s"/>

  {chr(10).join("  " + row for row in rows)}
</svg>'''
    return svg


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 README 终端演示动画 SVG")
    parser.add_argument("-o", "--output", default=os.path.join(os.path.dirname(__file__), "..", "assets", "demo.svg"))
    args = parser.parse_args()
    svg = build_demo_svg()
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"已写入：{os.path.abspath(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
