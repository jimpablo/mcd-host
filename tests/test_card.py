import json
import re

from mcd_host.card import render_card_svg, render_card_text
from mcd_host.demo import demo_coupons_payload, demo_menu_payload, demo_nutrition_payload
from mcd_host.model import PlanRequest, normalize_coupons, normalize_menu
from mcd_host.planner import build_plan


def _plan():
    return build_plan(
        normalize_menu(demo_menu_payload()),
        normalize_coupons(demo_coupons_payload()),
        PlanRequest(people=6, budget=30000, occasion="dinner"),
        demo_nutrition_payload(),
    )


def test_svg_is_self_contained():
    svg = render_card_svg(_plan(), store="演示·东道主店", date="2026-10-24", host="小东")
    assert svg.startswith("<svg")
    assert "viewBox" in svg
    # 自包含：不引用外部字体/图片/脚本
    assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in svg
    assert "<image" not in svg
    assert "<script" not in svg
    # 关键信息都在
    assert "麦门东道主" in svg
    assert "人均" in svg
    assert "2026-10-24" in svg
    assert "演示·东道主店" in svg


def test_svg_escapes_item_names():
    plan = _plan()
    plan.lines[0].name = '<script>alert("x")</script>'
    svg = render_card_svg(plan)
    assert "<script>alert" not in svg
    assert "&lt;script&gt;" in svg


def test_svg_light_and_dark_rules():
    svg = render_card_svg(_plan())
    assert "prefers-color-scheme: dark" in svg
    assert "prefers-color-scheme: light" in svg


def test_text_card_contains_amounts():
    text = render_card_text(_plan(), store="演示·东道主店")
    assert "应付" in text
    assert "人均" in text
    assert re.search(r"¥\d+\.\d{2}", text)


def test_receipt_style_svg():
    plan = _plan()
    svg = render_card_svg(plan, store="演示·东道主店", date="2026-10-24", style="receipt")
    assert svg.startswith("<svg")
    assert "请客小票" in svg
    assert "viewBox=\"0 0 420" in svg
    # 自包含 + 关键信息
    assert "https://" not in svg
    assert "人均" in svg
    assert "演示·东道主店" in svg
    # 装饰条形码由内容确定性生成
    first = render_card_svg(plan, style="receipt")
    second = render_card_svg(plan, style="receipt")
    assert first == second


def test_receipt_escapes_names():
    plan = _plan()
    plan.lines[0].name = '<script>alert("x")</script>'
    svg = render_card_svg(plan, style="receipt")
    assert "<script>alert" not in svg


def test_card_deterministic():
    first = render_card_svg(_plan(), store="演示·东道主店", date="2026-10-24")
    second = render_card_svg(_plan(), store="演示·东道主店", date="2026-10-24")
    assert first == second


def test_plan_dict_round_trip_for_card():
    from mcd_host.cli import _rebuild_plan_from_dict

    plan = _plan()
    data = plan.to_dict()
    data["store"] = "演示·东道主店"
    restored = _rebuild_plan_from_dict(data)
    assert restored.payable == plan.payable
    assert restored.per_person == plan.per_person
    assert restored.coupon.name == plan.coupon.name
    assert [line.name for line in restored.lines] == [line.name for line in plan.lines]
