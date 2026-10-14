"""请客方案卡：把一份 Plan 画成自包含 SVG（浅色/深色自适应，无外部依赖）。"""

from __future__ import annotations

import hashlib
import html
from typing import Optional

from .model import Plan

_OCCASION_LABELS = {
    "lunch": "午饭",
    "dinner": "晚饭",
    "tea": "下午茶",
    "breakfast": "早饭",
    "birthday": "庆生",
    "team": "团餐",
}

_KIND_LABELS = {
    "set": "套餐",
    "main": "主食",
    "side": "小食",
    "drink": "饮料",
    "dessert": "甜品",
    "other": "其他",
}

_STYLE = """
  .bg { fill: var(--bg); }
  .panel { fill: var(--panel); stroke: var(--border); stroke-width: 0.5; }
  .ink { fill: var(--ink); }
  .muted { fill: var(--muted); }
  .accent { fill: var(--accent); }
  .rule { stroke: var(--rule); stroke-width: 0.5; stroke-dasharray: 3 3; }
  .solid { stroke: var(--rule); stroke-width: 0.5; }
  .title { font: 500 17px var(--sans); }
  .sub { font: 400 12px var(--sans); }
  .meta { font: 400 12px var(--sans); }
  .row { font: 400 13px var(--sans); }
  .rowb { font: 500 13px var(--sans); }
  .small { font: 400 11px var(--sans); }
  .amount { font: 500 15px var(--sans); }
  .big { font: 500 20px var(--sans); }
"""

_DEFS = """
  <defs>
    <g id="burger">
      <rect x="0" y="0" width="34" height="7" rx="3.5" class="accent"/>
      <rect x="2" y="8.5" width="30" height="4.5" rx="2" class="accent" opacity="0.75"/>
      <rect x="1" y="14.5" width="32" height="5" rx="2.5" class="accent" opacity="0.9"/>
      <rect x="0" y="21" width="34" height="7" rx="3.5" class="accent"/>
    </g>
  </defs>
"""


def _yuan(cents: int) -> str:
    return f"¥{cents / 100:.2f}"


def _is_1024(date: str) -> bool:
    """卡片日期是 10-24（程序员节）时返回 True。"""
    return bool(date) and date[5:] == "10-24"


def _easter_egg_1024(date: str, y: float) -> str:
    """10-24 程序员节彩蛋行。"""
    if not _is_1024(date):
        return ""
    return f'<text class="small" x="52" y="{y}" fill="#BA7517">Happy 0x400 Day · 1024 程序员节快乐</text>'


def _barcode(seed_text: str, width: int, x: float, y: float, height: float = 34) -> str:
    """由方案内容确定性生成装饰条形码（纯 SVG rect，无随机依赖）。"""
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    bars = []
    cursor = x
    index = 0
    while cursor < x + width - 2:
        byte = digest[index % len(digest)]
        bar_width = 1 + (byte % 3)
        if byte % 5 != 0:  # 偶尔留白
            bars.append(f'<rect x="{cursor:.1f}" y="{y}" width="{bar_width}" height="{height}" class="ink"/>')
        cursor += bar_width + 1 + (byte % 2)
        index += 1
    return "".join(bars)


def render_receipt_svg(
    plan: Plan,
    store: str = "",
    date: str = "",
    host: str = "",
) -> str:
    """竖版热敏小票风请客方案卡（适合发朋友圈/小红书）。"""
    occasion = _OCCASION_LABELS.get(plan.occasion, plan.occasion or "请客")
    rows = []
    y = 150
    for line in plan.lines:
        kind_label = _KIND_LABELS.get(line.kind, line.kind)
        name = html.escape(line.name)
        qty = f"x{line.qty}"
        price = _yuan(line.total)
        rows.append(
            f'<text class="row ink" x="46" y="{y}">{name}<tspan class="muted" dx="4">{kind_label}</tspan></text>'
            f'<text class="row ink" x="374" y="{y}" text-anchor="end">{qty} {price}</text>'
        )
        y += 24
    bottom = y + 6

    coupon_row = ""
    if plan.coupon is not None:
        coupon_row = (
            f'<text class="row ink" x="46" y="{bottom + 22}">优惠 {html.escape(plan.coupon.name)}</text>'
            f'<text class="rowb" x="374" y="{bottom + 22}" text-anchor="end" fill="#1D9E75">-{_yuan(plan.coupon_saving)}</text>'
        )
        bottom += 24

    height = bottom + 210
    store_text = f'<tspan class="meta muted">{html.escape(store)}</tspan>' if store else ""
    host_text = f'<tspan class="meta muted">东道主 {html.escape(host)}</tspan>' if host else ""
    date_text = f'<tspan class="meta muted">{html.escape(date)}</tspan>' if date else ""

    seed = f"{plan.occasion}{plan.people}{plan.payable}" + "".join(line.name for line in plan.lines)
    zigzag_top = " ".join(f"{46 + i * 12},24 {52 + i * 12},32" for i in range(26))
    zigzag_bottom = " ".join(f"{46 + i * 12},{height - 8} {52 + i * 12},{height - 16}" for i in range(26))

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 {height}" width="100%" role="img">
  <title>麦门东道主 · 请客小票</title>
  <desc>{plan.people} 人{occasion}请客小票，应付 {_yuan(plan.payable)}，人均 {_yuan(plan.per_person)}</desc>
  <style>
    :root {{ --sans: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; --mono: "SF Mono", Menlo, Consolas, "Courier New", monospace; }}
    {_STYLE}
    @media (prefers-color-scheme: dark) {{
      :root {{ --bg: #1C1B1A; --panel: #26241F; --border: #4A473E; --ink: #F1EFE8; --muted: #A9A69B; --rule: #4A473E; --accent: #EF9F27; }}
    }}
    @media (prefers-color-scheme: light) {{
      :root {{ --bg: #FAEEDA; --panel: #FFFEF9; --border: #E5DCC8; --ink: #412402; --muted: #854F0B; --rule: #E5DCC8; --accent: #EF9F27; }}
    }}
  </style>
  <rect class="bg" x="0" y="0" width="420" height="{height}" rx="4"/>
  <polyline class="accent" points="{zigzag_top}" fill="none" stroke-width="2"/>
  <rect class="panel" x="34" y="30" width="352" height="{height - 60}" rx="6"/>

  <text class="title ink" x="210" y="66" text-anchor="middle">麦门东道主</text>
  <text class="sub muted" x="210" y="88" text-anchor="middle">请客小票 · {occasion} · {plan.people} 人</text>
  <text class="meta muted" x="210" y="110" text-anchor="middle">{store_text}{host_text}{date_text}</text>
  <line class="rule" x1="46" y1="124" x2="374" y2="124"/>

  {''.join(chr(10) + '  ' + row for row in rows)}

  <line class="rule" x1="46" y1="{bottom + 4}" x2="374" y2="{bottom + 4}"/>
  <text class="row muted" x="46" y="{bottom + 22}">小计</text>
  <text class="rowb ink" x="374" y="{bottom + 22}" text-anchor="end">{_yuan(plan.subtotal)}</text>
  {coupon_row}
  <text class="amount ink" x="46" y="{bottom + (52 if plan.coupon is not None else 32)}">应付</text>
  <text class="big ink" x="374" y="{bottom + (52 if plan.coupon is not None else 32)}" text-anchor="end">{_yuan(plan.payable)}</text>

  <line class="rule" x1="46" y1="{bottom + (70 if plan.coupon is not None else 50)}" x2="374" y2="{bottom + (70 if plan.coupon is not None else 50)}"/>
  <text class="rowb" x="210" y="{bottom + (96 if plan.coupon is not None else 76)}" text-anchor="middle">人均 {_yuan(plan.per_person)}</text>
  {_barcode(seed, 200, 110, bottom + (110 if plan.coupon is not None else 90))}
  <text class="small" x="210" y="{height - 84}" text-anchor="middle" fill="#BA7517">{"Happy 0x400 Day · 1024 程序员节快乐" if _is_1024(date) else ""}</text>
  <text class="small muted" x="210" y="{height - 66}" text-anchor="middle">数据来自麦当劳中国 MCP · 非官方参赛作品</text>
  <text class="small muted" x="210" y="{height - 48}" text-anchor="middle">mcd-host 生成 · 金额以实时价格为准</text>
  <polyline class="accent" points="{zigzag_bottom}" fill="none" stroke-width="2"/>
</svg>'''
    return svg


def render_card_svg(
    plan: Plan,
    store: str = "",
    date: str = "",
    host: str = "",
    style: str = "card",
) -> str:
    if style == "receipt":
        return render_receipt_svg(plan, store=store, date=date, host=host)
    return _render_card_svg(plan, store=store, date=date, host=host)


def _render_card_svg(
    plan: Plan,
    store: str = "",
    date: str = "",
    host: str = "",
) -> str:
    occasion = _OCCASION_LABELS.get(plan.occasion, plan.occasion or "请客")
    rows = []
    y = 132
    for line in plan.lines:
        kind_label = _KIND_LABELS.get(line.kind, line.kind)
        name = html.escape(line.name)
        qty = f"×{line.qty}"
        price = _yuan(line.total)
        rows.append(
            f'<text class="row ink" x="52" y="{y}">{name}'
            f'<tspan class="muted" dx="6">{kind_label}</tspan></text>'
            f'<text class="rowb ink" x="628" y="{y}" text-anchor="end">{qty}　{price}</text>'
            f'<line class="rule" x1="52" y1="{y + 9}" x2="628" y2="{y + 9}"/>'
        )
        y += 26
    bottom = y + 4

    coupon_row = ""
    if plan.coupon is not None:
        coupon_row = (
            f'<text class="row muted" x="52" y="{bottom + 22}">优惠（{html.escape(plan.coupon.name)}）</text>'
            f'<text class="rowb" x="628" y="{bottom + 22}" text-anchor="end" fill="#1D9E75">-{_yuan(plan.coupon_saving)}</text>'
        )
        bottom += 26

    height = bottom + 150
    store_text = f'　·　{html.escape(store)}' if store else ""
    host_text = f"　·　东道主 {html.escape(host)}" if host else ""
    date_text = f"　·　{html.escape(date)}" if date else ""

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 {height}" width="100%" role="img">
  <title>麦门东道主 · 请客方案卡</title>
  <desc>{plan.people} 人{occasion}请客方案，应付 {_yuan(plan.payable)}，人均 {_yuan(plan.per_person)}</desc>
  <style>
    :root {{ --sans: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }}
    {_STYLE}
    @media (prefers-color-scheme: dark) {{
      :root {{ --bg: #1C1B1A; --panel: #26241F; --border: #4A473E; --ink: #F1EFE8; --muted: #A9A69B; --rule: #4A473E; --accent: #EF9F27; }}
    }}
    @media (prefers-color-scheme: light) {{
      :root {{ --bg: #FAEEDA; --panel: #FFFDF7; --border: #E5DCC8; --ink: #412402; --muted: #854F0B; --rule: #E5DCC8; --accent: #EF9F27; }}
    }}
  </style>
  {_DEFS}
  <rect class="bg" x="0" y="0" width="680" height="{height}" rx="16"/>
  <rect class="panel" x="24" y="24" width="632" height="{height - 48}" rx="14"/>

  <use href="#burger" x="52" y="52"/>
  <text class="title ink" x="104" y="62">麦门东道主</text>
  <text class="sub muted" x="104" y="82">请客方案 · {occasion} · {plan.people} 人{store_text}{host_text}{date_text}</text>

  <line class="solid" x1="52" y1="104" x2="628" y2="104"/>

  {''.join(chr(10) + '  ' + row for row in rows)}

  <text class="row muted" x="52" y="{bottom + 22}">小计</text>
  <text class="rowb ink" x="628" y="{bottom + 22}" text-anchor="end">{_yuan(plan.subtotal)}</text>
  {coupon_row}
  <text class="amount ink" x="52" y="{bottom + (52 if plan.coupon is not None else 30)}">应付</text>
  <text class="big ink" x="628" y="{bottom + (52 if plan.coupon is not None else 30)}" text-anchor="end">{_yuan(plan.payable)}</text>

  <rect x="52" y="{bottom + (66 if plan.coupon is not None else 44)}" width="150" height="30" rx="15" class="accent"/>
  <text class="rowb" x="127" y="{bottom + (85 if plan.coupon is not None else 63)}" text-anchor="middle" fill="#412402">人均 {_yuan(plan.per_person)}</text>

  {_easter_egg_1024(date, height - 60)}
  <text class="small muted" x="52" y="{height - 44}">由 mcd-host 生成 · 数据来自麦当劳中国 MCP · 非官方参赛作品</text>
  <text class="small muted" x="52" y="{height - 28}">金额以麦当劳下单时实时价格为准，本卡仅供请客参考</text>
</svg>'''
    return svg


def render_card_text(plan: Plan, store: str = "") -> str:
    """终端里的文字版卡片。"""
    occasion = _OCCASION_LABELS.get(plan.occasion, plan.occasion or "请客")
    lines = []
    lines.append("┌─────────────────────────────────────┐")
    lines.append(f"│  麦门东道主 · {occasion}请客 · {plan.people} 人")
    if store:
        lines.append(f"│  门店：{store}")
    lines.append("├─────────────────────────────────────┤")
    for line in plan.lines:
        kind_label = _KIND_LABELS.get(line.kind, line.kind)
        name = line.name if len(line.name) <= 10 else line.name[:9] + "…"
        left = f"  {name}（{kind_label}）×{line.qty}"
        right = _yuan(line.total)
        pad = 37 - sum(2 if ord(c) > 127 else 1 for c in left) - len(right)
        lines.append("│" + left + " " * max(pad, 1) + right)
    lines.append("├─────────────────────────────────────┤")
    subtotal = f"  小计：{_yuan(plan.subtotal)}"
    lines.append("│" + subtotal)
    if plan.coupon is not None:
        saved = f"  优惠（{plan.coupon.name}）：-{_yuan(plan.coupon_saving)}"
        lines.append("│" + saved)
    payable = f"  应付：{_yuan(plan.payable)}"
    lines.append("│" + payable)
    per_person = f"  人均：{_yuan(plan.per_person)}"
    lines.append("│" + per_person)
    lines.append("└─────────────────────────────────────┘")
    return "\n".join(lines)
