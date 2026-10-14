"""mcd-host 命令行入口。

子命令：
  plan    凑一桌：读菜单/券/营养 JSON，输出请客方案（可同时生成分享卡片）
  card    由方案 JSON 生成分享卡片 SVG
  demo    不联网、不需要 Token 的一键演示
  fetch   用 MCP Token 拉取只读数据（门店/菜单/券/营养），供 plan 使用
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

from . import __version__
from .card import render_card_svg, render_card_text
from .demo import DEMO_STORE, demo_coupons_payload, demo_menu_payload, demo_nutrition_payload
from .model import (
    PlanRequest,
    normalize_coupons,
    normalize_menu,
    normalize_nutrition,
)
from .mcp import MCPClient, MCPError
from .planner import build_plan
from .render import Renderer


def _to_cents(text: str) -> int:
    try:
        return int(round(float(text) * 100))
    except (TypeError, ValueError):
        raise ValueError(f"无法解析金额：{text}")


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _split_csv(value: str) -> list:
    if not value:
        return []
    return [part.strip() for part in value.replace("，", ",").split(",") if part.strip()]


def _emit_json(payload: dict, ok: bool = True) -> None:
    sys.stdout.write(json.dumps({"ok": ok, **payload}, ensure_ascii=False) + "\n")


def _fail(message: str, json_mode: bool) -> int:
    if json_mode:
        _emit_json({"error": {"message": message}}, ok=False)
    else:
        sys.stderr.write(f"错误：{message}\n")
    return 1


def _today() -> str:
    return datetime.date.today().isoformat()


def _plan_from_args(args, json_mode: bool):
    """汇总输入 → (menu, coupons, req, nutrition, store)。"""
    req = PlanRequest()
    nutrition = {}
    store = args.store or ""

    if args.input:
        payload = _load_json(args.input)
        if not isinstance(payload, dict):
            raise ValueError("--input 需要是一个 JSON 对象")
        req = PlanRequest.from_payload(payload.get("request", payload))
        menu_payload = payload.get("menu")
        coupons_payload = payload.get("coupons")
        nutrition_payload = payload.get("nutrition")
    else:
        req.people = args.people
        req.budget = _to_cents(args.budget) if args.budget else 0
        req.occasion = args.occasion
        req.avoid = _split_csv(args.avoid or "")
        req.prefer = _split_csv(args.prefer or "")
        req.must_include = _split_csv(args.must or "")
        req.max_calories = args.max_cal
        if args.with_dessert is not None:
            req.with_dessert = args.with_dessert
        menu_payload = _load_json(args.menu) if args.menu else None
        coupons_payload = _load_json(args.coupons) if args.coupons else None
        nutrition_payload = _load_json(args.nutrition) if args.nutrition else None

    if args.demo and menu_payload is None:
        menu_payload = demo_menu_payload()
    if args.demo and coupons_payload is None:
        coupons_payload = demo_coupons_payload()
    if args.demo and nutrition_payload is None:
        nutrition_payload = demo_nutrition_payload()
    if menu_payload is None:
        raise ValueError(
            "没有菜单数据。用 --menu 提供 query-meals 的返回 JSON，"
            "或用 mcd-host fetch menu --store-code <门店> 拉取，或者先 --demo 体验。"
        )

    menu = normalize_menu(menu_payload)
    if not menu:
        raise ValueError("菜单 JSON 里没有解析出任何带价格的餐品。")
    coupons = normalize_coupons(coupons_payload) if coupons_payload else []
    if nutrition_payload:
        nutrition = normalize_nutrition(nutrition_payload)
    if args.demo and not store:
        store = DEMO_STORE
    return menu, coupons, req, nutrition, store


def _cmd_plan(args) -> int:
    json_mode = args.json
    try:
        menu, coupons, req, nutrition, store = _plan_from_args(args, json_mode)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _fail(str(exc), json_mode)

    plan = build_plan(menu, coupons, req, nutrition)

    card_path = None
    if args.card or args.output:
        card_path = args.output or "mcd-host-card.svg"
        svg = render_card_svg(plan, store=store, date=args.date or _today(), host=args.host or "")
        with open(card_path, "w", encoding="utf-8") as fh:
            fh.write(svg)

    if json_mode:
        data = plan.to_dict()
        data["store"] = store
        if card_path:
            data["cardPath"] = os.path.abspath(card_path)
        _emit_json({"data": data})
    else:
        renderer = Renderer(color=not args.no_color)
        renderer.plan(plan, demo=args.demo, store=store)
        if card_path:
            sys.stdout.write(f"\n分享卡片已写入：{os.path.abspath(card_path)}\n")
    return 0


def _cmd_card(args) -> int:
    json_mode = args.json
    try:
        if args.demo:
            menu = normalize_menu(demo_menu_payload())
            coupons = normalize_coupons(demo_coupons_payload())
            plan = build_plan(menu, coupons, PlanRequest(people=6, budget=30000, occasion="dinner"), demo_nutrition_payload())
            store = DEMO_STORE
        else:
            if not args.plan:
                return _fail("card 需要 --plan <方案 JSON>，或者用 --demo 生成演示卡片。", json_mode)
            payload = _load_json(args.plan)
            data = payload.get("data", payload) if isinstance(payload, dict) else payload
            plan = _rebuild_plan_from_dict(data)
            store = data.get("store", "")
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as exc:
        return _fail(str(exc), json_mode)

    path = args.output or "mcd-host-card.svg"
    svg = render_card_svg(plan, store=store, date=args.date or _today(), host=args.host or "")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    if json_mode:
        _emit_json({"data": {"path": os.path.abspath(path)}})
    else:
        sys.stdout.write(render_card_text(plan, store=store) + "\n")
        sys.stdout.write(f"分享卡片已写入：{os.path.abspath(path)}\n")
    return 0


def _rebuild_plan_from_dict(data: dict):
    """从 plan --json 的输出还原 Plan（card 子命令用）。"""
    from .model import Coupon, Plan, PlanLine

    plan = Plan(
        occasion=data.get("occasion", "dinner"),
        people=data.get("people", 2),
        budget=data.get("budget", 0),
    )
    plan.lines = [
        PlanLine(
            code=line.get("code", ""),
            name=line.get("name", ""),
            kind=line.get("kind", "other"),
            qty=int(line.get("qty", 1)),
            price=int(line.get("price", 0)),
        )
        for line in data.get("lines", [])
    ]
    plan.subtotal = int(data.get("subtotal", sum(line.total for line in plan.lines)))
    coupon_data = data.get("coupon")
    if coupon_data:
        plan.coupon = Coupon(
            id=str(coupon_data.get("id", "")),
            name=str(coupon_data.get("name", "")),
            threshold=coupon_data.get("threshold"),
            value=coupon_data.get("value"),
        )
        plan.coupon_saving = int(coupon_data.get("saving", 0))
    plan.payable = int(data.get("payable", plan.subtotal - plan.coupon_saving))
    plan.per_person = int(data.get("perPerson", plan.payable // max(plan.people, 1)))
    plan.calories_per_person = data.get("caloriesPerPerson")
    plan.warnings = list(data.get("warnings", []))
    plan.rationale = list(data.get("rationale", []))
    return plan


def _cmd_demo(args) -> int:
    demo_args = argparse.Namespace(**vars(args))
    demo_args.demo = True
    demo_args.card = True
    demo_args.output = args.output or "mcd-host-card-demo.svg"
    demo_args.menu = None
    demo_args.coupons = None
    demo_args.nutrition = None
    demo_args.input = None
    demo_args.people = args.people
    demo_args.budget = args.budget
    demo_args.occasion = args.occasion
    demo_args.avoid = args.avoid
    demo_args.prefer = args.prefer
    demo_args.must = None
    demo_args.max_cal = None
    demo_args.with_dessert = None
    demo_args.store = ""
    demo_args.host = ""
    demo_args.date = ""
    return _cmd_plan(demo_args)


def _cmd_fetch(args) -> int:
    json_mode = args.json
    try:
        client = MCPClient(timeout=args.timeout)
        if args.what == "stores":
            arguments = {
                "searchType": 2,   # 2 = 按位置搜索（1 = 收藏门店）
                "beType": 1,       # 1 = 到店自取
            }
            if args.city:
                arguments["city"] = args.city
            if args.keyword:
                arguments["keyword"] = args.keyword
            if not (args.city and args.keyword):
                raise ValueError("查找门店需要同时给 --city 和 --keyword（MCP 接口要求）。")
            payload = client.call_tool("query-nearby-stores", arguments)
        elif args.what == "menu":
            if not args.store_code:
                raise ValueError("拉菜单需要 --store-code <门店编码>（来自 fetch stores）。")
            payload = client.call_tool("query-meals", {"storeCode": args.store_code, "beType": 1, "orderType": 1})
        elif args.what == "coupons":
            if not args.store_code:
                raise ValueError("拉券需要 --store-code <门店编码>。")
            store_coupons = client.call_tool("query-store-coupons", {"storeCode": args.store_code, "beType": 1})
            my_coupons = client.call_tool("query-my-coupons", {})
            available = client.call_tool("available-coupons", {})
            payload = {
                "storeCoupons": store_coupons,
                "myCoupons": my_coupons,
                "availableCoupons": available,
            }
        elif args.what == "nutrition":
            payload = client.call_tool("list-nutrition-foods", {})
        else:
            raise ValueError(f"未知的 fetch 目标：{args.what}")
    except (MCPError, ValueError) as exc:
        return _fail(str(exc), json_mode)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        if json_mode:
            _emit_json({"data": {"path": os.path.abspath(args.out)}})
        else:
            sys.stdout.write(f"已写入：{os.path.abspath(args.out)}\n")
    elif json_mode:
        _emit_json({"data": payload})
    else:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcd-host",
        description="麦门东道主 · 请客参谋：基于麦当劳中国 MCP 的请客/团餐凑桌、分摊与分享卡片",
    )
    parser.add_argument("--version", action="version", version=f"mcd-host {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="凑一桌请客方案")
    plan.add_argument("--people", type=int, default=2, help="请客人数（默认 2）")
    plan.add_argument("--budget", help="总预算，元，如 300")
    plan.add_argument("--occasion", default="dinner", help="场合：lunch/dinner/tea/breakfast/birthday/team")
    plan.add_argument("--avoid", help="忌口关键词，逗号分隔，如 辣,酸黄瓜")
    plan.add_argument("--prefer", help="偏好关键词，逗号分隔，如 麦辣")
    plan.add_argument("--must", help="必点餐品 code，逗号分隔")
    plan.add_argument("--max-cal", type=int, dest="max_cal", help="每人热量上限（千卡）")
    plan.add_argument("--with-dessert", dest="with_dessert", action="store_true", default=None, help="强制配甜品")
    plan.add_argument("--no-dessert", dest="with_dessert", action="store_false", help="不要甜品")
    plan.add_argument("--menu", help="菜单 JSON（MCP query-meals 返回）")
    plan.add_argument("--coupons", help="优惠券 JSON（query-store-coupons/query-my-coupons 返回）")
    plan.add_argument("--nutrition", help="营养 JSON（list-nutrition-foods 返回）")
    plan.add_argument("--input", help="一次给全的请求 JSON：{request, menu, coupons, nutrition}")
    plan.add_argument("--store", help="门店名称（只用于展示）")
    plan.add_argument("--host", help="东道主名字（只用于展示）")
    plan.add_argument("--date", help="日期，默认今天，如 2026-10-24")
    plan.add_argument("--card", action="store_true", help="同时生成分享卡片 SVG")
    plan.add_argument("-o", "--output", help="卡片输出路径")
    plan.add_argument("--demo", action="store_true", help="用合成数据演示，不需要 Token")
    plan.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    plan.add_argument("--no-color", action="store_true", help="禁用颜色")
    plan.set_defaults(func=_cmd_plan)

    card = sub.add_parser("card", help="由方案 JSON 生成分享卡片")
    card.add_argument("--plan", help="plan --json 输出的方案 JSON 文件")
    card.add_argument("--store", help="门店名称")
    card.add_argument("--host", help="东道主名字")
    card.add_argument("--date", help="日期")
    card.add_argument("-o", "--output", help="输出路径")
    card.add_argument("--demo", action="store_true", help="用演示数据生成卡片")
    card.add_argument("--json", action="store_true")
    card.set_defaults(func=_cmd_card)

    demo = sub.add_parser("demo", help="一键演示（合成数据，不需要 Token）")
    demo.add_argument("--people", type=int, default=6)
    demo.add_argument("--budget", default="300")
    demo.add_argument("--occasion", default="dinner")
    demo.add_argument("--avoid", default="")
    demo.add_argument("--prefer", default="")
    demo.add_argument("--must", default="")
    demo.add_argument("--max-cal", type=int, dest="max_cal")
    demo.add_argument("--with-dessert", dest="with_dessert", action="store_true", default=None)
    demo.add_argument("--no-dessert", dest="with_dessert", action="store_false")
    demo.add_argument("--store", default="")
    demo.add_argument("--host", default="")
    demo.add_argument("--date", default="")
    demo.add_argument("-o", "--output")
    demo.add_argument("--json", action="store_true")
    demo.add_argument("--no-color", action="store_true")
    demo.set_defaults(func=_cmd_demo)

    fetch = sub.add_parser("fetch", help="用 MCP Token 拉取只读数据")
    fetch.add_argument("what", choices=["stores", "menu", "coupons", "nutrition"])
    fetch.add_argument("--city", help="城市（查找门店时必填）")
    fetch.add_argument("--keyword", help="地标关键词（查找门店时必填）")
    fetch.add_argument("--store-code", dest="store_code", help="门店编码（拉菜单/券时必填）")
    fetch.add_argument("--out", help="写入文件而不是打印")
    fetch.add_argument("--timeout", type=int, default=30)
    fetch.add_argument("--json", action="store_true")
    fetch.set_defaults(func=_cmd_fetch)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except MCPError as exc:
        return _fail(str(exc), getattr(args, "json", False))
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
