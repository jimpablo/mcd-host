"""合成演示数据：不联网、不需要 Token 就能完整体验 mcd-host。

所有价格、门店、优惠券都是编的，仅用于演示与测试。
"""

from __future__ import annotations

DEMO_STORE = "演示·东道主店"

DEMO_MENU = [
    # code, name, category, price(分)
    ("S001", "巨无霸套餐", "套餐", 4150),
    ("S002", "麦辣鸡腿堡套餐", "套餐", 3900),
    ("S003", "板烧鸡腿堡套餐", "套餐", 3950),
    ("S004", "1+1随心配", "套餐", 1290),
    ("M001", "巨无霸", "汉堡", 2100),
    ("M002", "麦辣鸡腿堡", "汉堡", 2000),
    ("M003", "板烧鸡腿堡", "汉堡", 2000),
    ("M004", "麦香鱼", "汉堡", 1900),
    ("M005", "双层吉士堡", "汉堡", 1500),
    ("M006", "麦香鸡", "汉堡", 1200),
    ("D001", "中薯条", "小食", 1150),
    ("D002", "大薯条", "小食", 1350),
    ("D003", "麦乐鸡5块", "小食", 1150),
    ("D004", "黄金翅", "小食", 1200),
    ("D005", "玉米杯", "小食", 900),
    ("K001", "中可乐", "饮料", 900),
    ("K002", "大可乐", "饮料", 1050),
    ("K003", "雪碧", "饮料", 900),
    ("K004", "冰红茶", "饮料", 850),
    ("T001", "奥利奥麦旋风", "甜品", 1000),
    ("T002", "菠萝派", "甜品", 750),
    ("T003", "香芋派", "甜品", 750),
    ("T004", "甜筒", "甜品", 600),
]

DEMO_COUPONS = [
    # id, name, threshold(分), value(分)
    ("C001", "满50减8", 5000, 800),
    ("C002", "满100减20", 10000, 2000),
    ("C003", "套餐立减5元", 4000, 500),
]

DEMO_NUTRITION = {
    "巨无霸": 500,
    "麦辣鸡腿堡": 490,
    "板烧鸡腿堡": 400,
    "麦香鱼": 330,
    "双层吉士堡": 400,
    "麦香鸡": 360,
    "巨无霸套餐": 780,
    "麦辣鸡腿堡套餐": 800,
    "板烧鸡腿堡套餐": 720,
    "中薯条": 290,
    "大薯条": 360,
    "麦乐鸡5块": 220,
    "黄金翅": 240,
    "玉米杯": 90,
    "中可乐": 150,
    "大可乐": 180,
    "雪碧": 150,
    "冰红茶": 140,
    "奥利奥麦旋风": 280,
    "菠萝派": 250,
    "香芋派": 250,
    "甜筒": 150,
}


def demo_menu_payload() -> dict:
    """伪装成 MCP query-meals 的返回结构（按分类分组）。"""
    categories = {}
    for code, name, category, price in DEMO_MENU:
        categories.setdefault(category, []).append(
            {"code": code, "name": name, "price": price, "category": category}
        )
    return {
        "storeCode": "DEMO001",
        "categories": [{"categoryName": name, "meals": meals} for name, meals in categories.items()],
    }


def demo_coupons_payload() -> dict:
    """伪装成 MCP 的券返回：门店券是 JSON，我的券是 Markdown 渲染文本。"""
    return {
        "storeCoupons": [
            {"couponId": cid, "name": name, "threshold": threshold, "amount": value}
            for cid, name, threshold, value in DEMO_COUPONS
        ]
        + [
            {
                "couponId": "C004",
                "name": "中薯条买一送一",
                "products": [{"productCode": "D001", "productName": "中薯条"}],
            }
        ],
        "myCoupons": [
            {"couponId": "M001", "name": "麦辣鸡腿堡立减3元", "threshold": 2000, "amount": 300}
        ],
        "myCouponsMarkdown": (
            "## 中薯条买一送一\n- **优惠**: ¥11.5 (用券价格)\n"
            "- **有效期**: 2026-10-12 10:30-2026-10-16 23:59\n\n"
            "## 甜筒买一送一\n- **优惠**: ¥6.0 (用券价格)\n"
            "- **有效期**: 2026-10-12 10:30-2026-10-16 23:59\n"
        ),
    }


def demo_nutrition_payload() -> dict:
    return {
        "foods": [{"name": name, "calorie": kcal} for name, kcal in DEMO_NUTRITION.items()]
    }
