from mcd_host.demo import demo_coupons_payload, demo_menu_payload, demo_nutrition_payload
from mcd_host.model import PlanRequest, normalize_coupons, normalize_menu
from mcd_host.planner import build_plan, pick_coupon


def _menu():
    return normalize_menu(demo_menu_payload())


def _coupons():
    return normalize_coupons(demo_coupons_payload())


def test_basic_dinner_plan_within_budget():
    plan = build_plan(_menu(), _coupons(), PlanRequest(people=6, budget=30000, occasion="dinner"), demo_nutrition_payload())
    assert plan.payable <= 30000
    assert plan.people == 6
    # 每人一份套餐
    set_lines = [line for line in plan.lines if line.kind == "set"]
    assert sum(line.qty for line in set_lines) == 6
    # 1+1 随心配不当正餐
    assert all(line.price >= 2000 for line in set_lines)
    # 最省的满减券：满100减20
    assert plan.coupon is not None
    assert plan.coupon.name == "满100减20"
    assert plan.coupon_saving == 2000
    # 人均向上取整
    assert plan.per_person == -(-plan.payable // 6)
    assert plan.calories_per_person is not None


def test_avoid_keywords_filter_items():
    plan = build_plan(_menu(), _coupons(), PlanRequest(people=4, budget=30000, occasion="dinner", avoid=["辣"]))
    assert all("麦辣" not in line.name for line in plan.lines)
    assert any("麦辣" in reason for reason in plan.rationale)


def test_lunch_has_no_dessert_by_default():
    plan = build_plan(_menu(), _coupons(), PlanRequest(people=4, budget=30000, occasion="lunch"))
    assert not any(line.kind == "dessert" for line in plan.lines)
    plan_with = build_plan(_menu(), _coupons(), PlanRequest(people=4, budget=30000, occasion="lunch", with_dessert=True))
    assert any(line.kind == "dessert" for line in plan_with.lines)


def test_over_budget_uses_cheapest_and_warns():
    plan = build_plan(_menu(), _coupons(), PlanRequest(people=6, budget=20000, occasion="dinner"))
    assert plan.warnings
    assert any("预算" in w for w in plan.warnings)
    # 超预算时不再加共享小食/甜品以外的额外项
    assert plan.payable >= 20000


def test_must_include_is_added():
    plan = build_plan(_menu(), _coupons(), PlanRequest(people=4, budget=30000, occasion="dinner", must_include=["M006"]))
    codes = {line.code for line in plan.lines}
    assert "M006" in codes


def test_coupon_gap_hint_when_subtotal_too_low():
    coupons = [
        type("C", (), {"name": "满500减100", "threshold": 50000, "value": 10000, "is_threshold": True})()
    ]
    coupon, saving, hint = pick_coupon(coupons, 10000)
    assert coupon is None
    assert saving == 0
    assert hint is not None
    assert hint["gap"] == 40000


def test_pick_coupon_chooses_best():
    from mcd_host.model import Coupon

    coupons = [
        Coupon(id="1", name="满50减8", threshold=5000, value=800),
        Coupon(id="2", name="满100减20", threshold=10000, value=2000),
        Coupon(id="3", name="满200减30", threshold=20000, value=3000),
    ]
    coupon, saving, _ = pick_coupon(coupons, 25000)
    assert coupon.name == "满200减30"
    assert saving == 3000


def test_singles_strategy_when_no_sets():
    from mcd_host.model import MenuItem

    menu = [
        MenuItem(code="M1", name="测试堡", price=2000),
        MenuItem(code="M2", name="测试堡2号", price=2200),
        MenuItem(code="D1", name="测试薯条", price=1000),
        MenuItem(code="K1", name="测试可乐", price=800),
    ]
    plan = build_plan(menu, [], PlanRequest(people=4, budget=20000, occasion="dinner"))
    kinds = {line.kind for line in plan.lines}
    assert "main" in kinds and "drink" in kinds
    mains = [line for line in plan.lines if line.kind == "main"]
    assert sum(line.qty for line in mains) == 4


def test_bogo_coupon_drives_selection_and_saving():
    """有「中薯条买一送一」时，选品应偏向薯条，并且最终真的用上这张券。"""
    from mcd_host.model import Coupon, MenuItem

    menu = [
        MenuItem(code="D1", name="中薯条", price=1350),
        MenuItem(code="D2", name="玉米杯", price=1300),
        MenuItem(code="M1", name="测试堡", price=2000),
        MenuItem(code="K1", name="测试可乐", price=800),
    ]
    coupons = [
        Coupon(id="C1", name="中薯条买一送一", kind="bogo", product="中薯条", deal_price=1350)
    ]
    plan = build_plan(menu, coupons, PlanRequest(people=4, budget=20000, occasion="dinner"))
    side_lines = [line for line in plan.lines if line.kind == "side"]
    assert any(line.name == "中薯条" for line in side_lines)
    assert plan.coupon is not None
    assert plan.coupon.name == "中薯条买一送一"
    # 4 人 → 2 份共享小食，买一送一省 1 份
    assert plan.coupon_saving == 1350
    assert plan.payable == plan.subtotal - 1350


def test_fixed_coupon_uses_deal_price():
    from mcd_host.model import Coupon, MenuItem

    menu = [
        MenuItem(code="D1", name="中薯条", price=1350),
        MenuItem(code="D2", name="玉米杯", price=1300),
        MenuItem(code="M1", name="测试堡", price=2000),
        MenuItem(code="K1", name="测试可乐", price=800),
    ]
    coupons = [Coupon(id="C1", name="玉米杯券后价", kind="fixed", product="玉米杯", deal_price=900)]
    plan = build_plan(menu, coupons, PlanRequest(people=4, budget=20000, occasion="dinner"))
    assert plan.coupon is not None
    assert plan.coupon.name == "玉米杯券后价"
    assert plan.coupon_saving == 400 * 2  # (1300-900) × 2 份


def test_calorie_coverage_note_when_partial():
    from mcd_host.model import MenuItem

    menu = [
        MenuItem(code="M1", name="测试堡", price=2000),
        MenuItem(code="D1", name="中薯条", price=1350),
        MenuItem(code="K1", name="测试可乐", price=800),
    ]
    nutrition = {"中薯条": 289}
    plan = build_plan(menu, [], PlanRequest(people=2, budget=20000, occasion="dinner"), nutrition)
    assert plan.calories_per_person == 289
    assert any("营养表只覆盖" in reason for reason in plan.rationale)
