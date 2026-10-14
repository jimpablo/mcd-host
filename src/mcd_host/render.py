"""终端渲染：人类可读的方案输出（无第三方依赖，支持 NO_COLOR）。"""

from __future__ import annotations

import os
import sys

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


def _c(enabled: bool, code: str) -> str:
    return code if enabled else ""


class Renderer:
    def __init__(self, color: bool = True):
        self.color = color and not os.environ.get("NO_COLOR")

    def _w(self, text: str = "") -> None:
        sys.stdout.write(text + "\n")

    def plan(self, plan: Plan, demo: bool = False, store: str = "") -> None:
        bold = _c(self.color, "\033[1m")
        dim = _c(self.color, "\033[2m")
        yellow = _c(self.color, "\033[33m")
        green = _c(self.color, "\033[32m")
        red = _c(self.color, "\033[31m")
        reset = _c(self.color, "\033[0m")

        occasion = _OCCASION_LABELS.get(plan.occasion, plan.occasion or "请客")
        tag = f"{yellow}(demo 合成数据){reset} " if demo else ""
        self._w(f"{tag}{bold}麦门东道主 · 请客参谋{reset}")
        if store:
            self._w(f"{dim}门店：{store}{reset}")
        self._w(f"{bold}一桌菜（{plan.people} 人 · {occasion}）{reset}")
        self._w()
        width = 46
        for line in plan.lines:
            kind = _KIND_LABELS.get(line.kind, line.kind)
            left = f"  {line.name}（{kind}）×{line.qty}"
            right = f"¥{line.total / 100:.2f}"
            pad = width - sum(2 if ord(c) > 127 else 1 for c in left) - len(right)
            self._w(left + " " * max(pad, 1) + right)
        self._w()
        subtotal = f"  小计：¥{plan.subtotal / 100:.2f}"
        self._w(subtotal)
        if plan.coupon is not None:
            self._w(f"{green}  优惠（{plan.coupon.name}）：-¥{plan.coupon_saving / 100:.2f}{reset}")
        self._w(f"{bold}  应付：¥{plan.payable / 100:.2f}{reset}")
        self._w(f"{bold}  人均：¥{plan.per_person / 100:.2f}{reset}")
        if plan.calories_per_person:
            self._w(f"{dim}  人均约 {plan.calories_per_person} 千卡{reset}")
        for warning in plan.warnings:
            self._w(f"{red}  ! {warning}{reset}")
        if plan.rationale:
            self._w()
            self._w(f"{dim}思路：{'；'.join(plan.rationale)}{reset}")
