from pathlib import Path

from mcd_host.model import (
    PlanRequest,
    classify,
    fuzzy_lookup,
    normalize_coupons,
    normalize_menu,
    normalize_nutrition,
)


def test_classify_kinds():
    assert classify("套餐", "巨无霸套餐") == "set"
    assert classify("", "1+1随心配") == "set"
    assert classify("汉堡", "麦辣鸡腿堡") == "main"
    assert classify("汉堡", "麦香鱼") == "main"
    assert classify("小食", "麦乐鸡5块") == "side"
    assert classify("小食", "玉米杯") == "side"
    assert classify("饮料", "中可乐") == "drink"
    assert classify("甜品", "奥利奥麦旋风") == "dessert"
    assert classify("甜品", "菠萝派") == "dessert"
    assert classify("", "甜筒") == "dessert"


def test_normalize_menu_from_mcp_shaped_fixture():
    fixture = Path(__file__).parent / "fixtures" / "mcp_shaped.json"
    with open(fixture, encoding="utf-8") as fh:
        import json

        payload = json.load(fh)
    menu = normalize_menu(payload)
    names = {item.name for item in menu}
    assert {"巨无霸", "麦辣鸡腿堡", "中薯条", "中可乐", "麦旋风", "神秘限定堡"} <= names
    big_mac = next(item for item in menu if item.name == "巨无霸")
    assert big_mac.price == 2100
    assert big_mac.code == "9001"
    assert big_mac.kind == "main"
    # 没有价格的会被跳过
    assert all(item.price > 0 for item in menu)


def test_normalize_menu_handles_yuan_floats_and_strings():
    menu = normalize_menu(
        {"meals": [{"name": "测试堡", "price": 21.5}, {"name": "测试薯条", "price": "11.5"}]}
    )
    prices = {item.name: item.price for item in menu}
    assert prices["测试堡"] == 2150
    assert prices["测试薯条"] == 1150


def test_normalize_coupons():
    coupons = normalize_coupon = normalize_coupons(
        {"coupons": [{"name": "满60减15", "threshold": 6000, "amount": 1500}, {"name": "无门槛", "amount": 200}]}
    )
    threshold_coupon = next(c for c in coupons if c.name == "满60减15")
    assert threshold_coupon.is_threshold
    assert threshold_coupon.threshold == 6000
    assert threshold_coupon.value == 1500
    no_threshold = next(c for c in coupons if c.name == "无门槛")
    assert not no_threshold.is_threshold


def test_normalize_nutrition():
    result = normalize_nutrition({"foods": [{"name": "巨无霸", "calorie": 500}]})
    assert result["巨无霸"] == 500


def test_plan_request_from_payload():
    req = PlanRequest.from_payload(
        {
            "people": 8,
            "budget": 500,
            "occasion": "birthday",
            "avoid": ["辣", "酸黄瓜"],
            "prefer": "麦辣,板烧",
            "must_include": "9001",
            "maxCalories": 900,
            "withDessert": True,
        }
    )
    assert req.people == 8
    assert req.budget == 50000
    assert req.avoid == ["辣", "酸黄瓜"]
    assert req.prefer == ["麦辣", "板烧"]
    assert req.must_include == ["9001"]
    assert req.max_calories == 900
    assert req.with_dessert is True


def test_plan_request_rejects_bad_people():
    import pytest

    with pytest.raises(ValueError):
        PlanRequest.from_payload({"people": 0})


def test_normalize_menu_string_prices_are_yuan():
    menu = normalize_menu(
        {
            "data": {
                "categories": [{"name": "汉堡", "meals": [{"code": "1"}, {"code": "2"}]}],
                "meals": {
                    "1": {"name": "测试堡", "currentPrice": "15"},
                    "2": {"name": "测试薯条", "currentPrice": "13.9"},
                },
            }
        }
    )
    prices = {item.name: item.price for item in menu}
    assert prices["测试堡"] == 1500
    assert prices["测试薯条"] == 1390


def test_normalize_coupons_from_store_json_and_markdown():
    payload = {
        "storeCoupons": {
            "data": [
                {"title": "中薯条买一送一", "couponId": "C1", "products": [{"productCode": "D1", "productName": "中薯条"}]},
                {"title": "满60减15", "couponId": "C2", "threshold": 6000, "amount": 1500},
            ]
        },
        "myCoupons": (
            "## 中薯条买一送一\n- **优惠**: ¥13.5 (用券价格)\n- **有效期**: 2026-10-12 10:30-2026-10-16 23:59\n\n"
            "## 奥利奥麦旋风\n- **优惠**: ¥6.9 (用券价格)\n- **有效期**: 2026-10-12 10:30-2026-10-16 23:59\n"
        ),
    }
    coupons = normalize_coupons(payload)
    by_name = {c.name: c for c in coupons}
    bogo = by_name["中薯条买一送一"]
    assert bogo.kind == "bogo"
    assert bogo.product == "中薯条"
    assert bogo.deal_price == 1350  # 从 Markdown 合并来的用券价格
    threshold = by_name["满60减15"]
    assert threshold.kind == "threshold"
    assert threshold.is_threshold
    fixed = by_name["奥利奥麦旋风"]
    assert fixed.kind == "fixed"
    assert fixed.deal_price == 690


def test_normalize_nutrition_text_table():
    text = (
        "[3]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:\n"
        "  猪柳麦满分,null,1288,308,16,16,24,781,213\n"
        "  中薯条,null,1210,289,4,12,38,165,18\n"
        "  圆筒冰淇淋,null,391,93,2,3,14,36,77"
    )
    result = normalize_nutrition(text)
    assert result == {"猪柳麦满分": 308, "中薯条": 289, "圆筒冰淇淋": 93}


def test_normalize_nutrition_data_as_string():
    result = normalize_nutrition({"data": "[1]{productName,energyKcal}:\n  中薯条,289"})
    assert result["中薯条"] == 289


def test_fuzzy_lookup_size_prefix():
    table = {"大杯玉米杯": 90, "中薯条": 289}
    assert fuzzy_lookup("玉米杯", table) == ("大杯玉米杯", 90)
    assert fuzzy_lookup("中薯条", table) == ("中薯条", 289)
    assert fuzzy_lookup("不存在的餐品", table) == (None, None)
