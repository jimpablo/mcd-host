"""数据模型与 MCP 返回值的归一化。

麦当劳 MCP 各 Tool 的返回结构以实际服务为准，这里对所有输入做宽松解析：
只要对象里有名字和价格，就能变成 MenuItem；找不到价格的就跳过（并在
warnings 里提示）。金额单位统一为「分」（与 MCP 一致）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

KIND_ORDER = ("set", "main", "side", "drink", "dessert", "other")

KIND_LABELS = {
    "set": "套餐",
    "main": "主食",
    "side": "小食",
    "drink": "饮料",
    "dessert": "甜品",
    "other": "其他",
}

# 分类规则：按顺序匹配，先命中先算。顺序经过真实菜单校准：
# 「麦麦脆汁鸡」要先落到 side（鸡）而不是 drink（汁），「麦香鱼」要落到 main（鱼）。
_KIND_RULES = (
    ("set", ("套餐", "随心配", "1+1", "组合")),
    ("dessert", ("冰淇淋", "麦旋风", "甜筒", "新地", "圣代", "派", "蛋糕", "甜品", "蛋挞", "可可")),
    ("main", ("堡", "饭", "卷", "披萨", "主食", "鸡排", "鱼", "牛", "猪", "虾", "鲍")),
    ("side", ("薯条", "薯格", "薯饼", "鸡", "翅", "块", "玉米", "杯", "小食", "沙拉", "汤", "骨", "串")),
    ("drink", ("可乐", "汽水", "冰茶", "红茶", "绿茶", "茶", "咖啡", "汁", "奶", "雪冰", "水")),
)

OCCASIONS = ("lunch", "dinner", "tea", "breakfast", "birthday", "team")


def classify(category: str, name: str) -> str:
    text = f"{category or ''} {name or ''}"
    for kind, keywords in _KIND_RULES:
        if any(k in text for k in keywords):
            return kind
    return "other"


def _to_cents(value: Any) -> Optional[int]:
    """把 MCP 可能返回的价格转成「分」。

    规则（按真实返回校准）：
    - int → 按「分」解释（MCP 内部接口如 calculate-price 用整数分）；
    - float / str → 按「元」解释（query-meals 的 currentPrice 是 "13.9" 这样的字符串）。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value * 100))
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("¥", "").replace("￥", "")
        if not text:
            return None
        try:
            return int(round(float(text) * 100))
        except ValueError:
            return None
    return None


def _first(d: dict, *keys: str) -> Any:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return None


def _iter_dicts(payload: Any) -> Iterable[dict]:
    """递归遍历，产出所有 dict 节点。"""
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


_SIZE_PREFIXES = ("大杯", "中杯", "小杯", "大份", "中份", "小份", "大罐", "中罐", "小罐")


def _strip_size(name: str) -> str:
    for prefix in _SIZE_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def fuzzy_lookup(name: str, table: dict):
    """在 {名字: 值} 表里找 name 对应的值。

    菜单名和营养表/券的商品名常有规格差异（「玉米杯」vs「大杯玉米杯」），
    依次尝试：精确 → 互相包含 → 去规格前缀后再匹配。返回 (key, value)，找不到返回 (None, None)。
    """
    if not name:
        return None, None
    if name in table:
        return name, table[name]
    best = None
    for key in table:
        if key and (key in name or name in key):
            score = abs(len(key) - len(name))
            if best is None or score < best[0]:
                best = (score, key)
    if best is not None:
        return best[1], table[best[1]]
    stripped = _strip_size(name)
    if stripped != name:
        for key in table:
            key_stripped = _strip_size(key)
            if key_stripped and (key_stripped in stripped or stripped in key_stripped):
                return key, table[key]
    return None, None


@dataclass
class MenuItem:
    code: str
    name: str
    category: str = ""
    price: int = 0
    tags: list = field(default_factory=list)
    calorie: Optional[int] = None

    @property
    def kind(self) -> str:
        return classify(self.category, self.name)

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


@dataclass
class Coupon:
    id: str
    name: str
    threshold: Optional[int] = None  # 满 X 分可用（满减券）；None 表示非满减券
    value: Optional[int] = None      # 减免 X 分（满减券）
    kind: str = "threshold"          # threshold=满减券 / fixed=用券价 / bogo=买一送一
    product: str = ""                # 适用商品名（商品券）
    deal_price: Optional[int] = None # 用券价格（fixed）

    @property
    def is_threshold(self) -> bool:
        return self.kind == "threshold" and self.threshold is not None and self.value is not None


_COUPON_BOGO_KEYWORDS = ("买一送一", "第二份", "加一元", "买二赠一")
_COUPON_FIXED_HINT = ("用券价格", "券后价", "优惠价")


def _parse_coupon_markdown(text: str) -> list:
    """解析 query-my-coupons 的 Markdown 渲染输出。

    形如：
        ## 中薯条买一送一
        - **优惠**: ¥13.5 (用券价格)
        - **有效期**: ...
    """
    coupons = []
    blocks = re.split(r"(?m)^##\s+", text)
    for block in blocks[1:]:
        lines = block.splitlines()
        name = lines[0].strip()
        if not name:
            continue
        body = "\n".join(lines[1:])
        deal_price = None
        match = re.search(r"\*\*优惠\*\*\s*[:：]\s*[¥￥]?\s*([\d.]+)", body)
        if match:
            try:
                deal_price = int(round(float(match.group(1)) * 100))
            except ValueError:
                deal_price = None
        bogo = any(k in name or k in body for k in _COUPON_BOGO_KEYWORDS)
        kind = "bogo" if bogo else ("fixed" if deal_price is not None else "threshold")
        threshold = value = None
        full_match = re.search(r"满\s*([\d.]+)\s*减\s*([\d.]+)", name + " " + body)
        if full_match and not bogo and deal_price is None:
            try:
                threshold = int(round(float(full_match.group(1)) * 100))
                value = int(round(float(full_match.group(2)) * 100))
                kind = "threshold"
            except ValueError:
                pass
        coupons.append(
            Coupon(
                id=name,
                name=name,
                threshold=threshold,
                value=value,
                kind=kind,
                product=name,
                deal_price=deal_price,
            )
        )
    return coupons


def _iter_strings(payload: Any) -> Iterable[str]:
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def normalize_menu(payload: Any) -> list:
    """把 query-meals / query-meal-detail 的返回值归一化成 MenuItem 列表。"""
    items = []
    seen = set()
    for node in _iter_dicts(payload):
        name = _first(node, "name", "mealName", "title", "productName")
        if not isinstance(name, str) or not name.strip():
            continue
        code = _first(node, "code", "mealCode", "id", "productCode", "skuCode")
        code = str(code) if code is not None else name.strip()
        price = _to_cents(
            _first(node, "price", "currentPrice", "salePrice", "realPrice", "amount", "unitPrice")
        )
        if price is None or price <= 0:
            continue
        category = _first(node, "category", "categoryName", "type", "mealType") or ""
        category = str(category)
        tags = _first(node, "tags", "labels", "tagList") or []
        if isinstance(tags, str):
            tags = [tags]
        elif isinstance(tags, list):
            tags = [str(t) for t in tags if isinstance(t, (str, int))]
        else:
            tags = []
        key = (code, name.strip())
        if key in seen:
            continue
        seen.add(key)
        items.append(
            MenuItem(code=code, name=name.strip(), category=category, price=price, tags=tags)
        )
    return items


_NUTRITION_TEXT_RE = re.compile(r"\[(\d+)\]\{([^}]*)\}:")


def _parse_nutrition_text(text: str) -> dict:
    """解析 list-nutrition-foods 的文本表格返回。

    形如：
        [160]{productName,nutritionDescription,energyKj,energyKcal,...}:
          猪柳麦满分,null,1288,308,16,16,24,781,213
          中薯条,null,1210,289,4,12,38,165,18
    """
    match = _NUTRITION_TEXT_RE.search(text)
    if not match:
        return {}
    headers = [h.strip() for h in match.group(2).split(",")]
    result = {}
    for line in text[match.end() :].splitlines():
        line = line.strip().rstrip(",")
        if not line or "{" in line or line.startswith("["):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != len(headers):
            continue
        row = dict(zip(headers, parts))
        name = row.get("productName") or row.get("name")
        kcal = row.get("energyKcal") or row.get("calorie") or row.get("kcal")
        if not name or not kcal or name == "null":
            continue
        try:
            result[name] = int(float(kcal))
        except (TypeError, ValueError):
            continue
    return result


def normalize_nutrition(payload: Any) -> dict:
    """归一化 list-nutrition-foods 的返回值：{餐品名: 千卡}。

    兼容三种形态：文本表格、data 为字符串、标准 JSON 列表。
    """
    if isinstance(payload, str):
        return _parse_nutrition_text(payload)
    data = payload
    if isinstance(payload, dict):
        inner = payload.get("data")
        if isinstance(inner, str):
            return _parse_nutrition_text(inner)
        if inner is not None:
            data = inner
    result = {}
    for node in _iter_dicts(data):
        name = _first(node, "name", "mealName", "foodName", "productName", "title")
        if not isinstance(name, str) or not name.strip():
            continue
        calorie = _first(node, "calorie", "kcal", "energyKcal", "热量")
        if calorie is None:
            continue
        try:
            result[name.strip()] = int(float(calorie))
        except (TypeError, ValueError):
            continue
    return result


def normalize_coupons(payload: Any) -> list:
    """归一化各种来源的优惠券。

    - query-store-coupons / available-coupons：JSON，data[] 里有 title 和 products；
    - query-my-coupons：Markdown 渲染文本，按 name 合并用券价格。
    """
    coupons = []
    by_name = {}

    def add(coupon: Coupon) -> None:
        existing = by_name.get(coupon.name)
        if existing is None:
            by_name[coupon.name] = coupon
            coupons.append(coupon)
            return
        # 同名券合并：补齐另一来源的信息
        if existing.deal_price is None and coupon.deal_price is not None:
            existing.deal_price = coupon.deal_price
        # 商品名取更精确的（JSON 来源的 "中薯条" 比 Markdown 标题 "中薯条买一送一" 准）
        if coupon.product and (
            not existing.product
            or (len(coupon.product) < len(existing.product) and coupon.product in existing.product)
        ):
            existing.product = coupon.product
        if existing.kind == "threshold" and coupon.kind != "threshold":
            existing.kind = coupon.kind

    for text in _iter_strings(payload):
        if "## " in text and "优惠" in text:
            for coupon in _parse_coupon_markdown(text):
                add(coupon)

    for node in _iter_dicts(payload):
        name = _first(node, "name", "title", "couponName", "activityName")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        threshold = _to_cents(
            _first(node, "threshold", "thresholdPrice", "limitPrice", "conditionPrice", "fullPrice")
        )
        value = _to_cents(
            _first(node, "value", "discount", "amount", "reduce", "reduceAmount", "denomination")
        )
        product = ""
        products = _first(node, "products", "productList")
        if isinstance(products, list) and products:
            first_product = products[0]
            if isinstance(first_product, dict):
                product = str(_first(first_product, "productName", "name", "title") or "")
            elif isinstance(first_product, str):
                product = first_product
        product = product or str(_first(node, "productName", "product") or "")
        bogo = any(k in name for k in _COUPON_BOGO_KEYWORDS)
        if bogo:
            kind = "bogo"
        elif threshold is not None and value is not None:
            kind = "threshold"
        else:
            kind = "fixed"
        cid = str(_first(node, "id", "couponId", "code") or name)
        add(
            Coupon(
                id=cid,
                name=name,
                threshold=threshold,
                value=value,
                kind=kind,
                product=product,
            )
        )
    return coupons


@dataclass
class PlanRequest:
    people: int = 2
    budget: int = 0                    # 总预算，分；0 表示不限制
    occasion: str = "dinner"
    avoid: list = field(default_factory=list)    # 忌口关键词
    prefer: list = field(default_factory=list)   # 偏好关键词
    must_include: list = field(default_factory=list)  # 必须出现的餐品 code
    max_calories: Optional[int] = None           # 每人热量上限（千卡）
    with_dessert: Optional[bool] = None          # None = 按场合自动决定

    @staticmethod
    def from_payload(payload: Any) -> "PlanRequest":
        if not isinstance(payload, dict):
            raise ValueError("plan 请求必须是 JSON 对象")
        req = PlanRequest()
        people = payload.get("people")
        if people is None:
            req.people = 2
        else:
            req.people = int(people)
        if req.people < 1:
            raise ValueError("people 至少为 1")
        budget = payload.get("budget")
        if budget:
            # 请求里的预算单位是「元」
            req.budget = _to_cents(budget) if isinstance(budget, str) else int(round(float(budget) * 100))
        req.occasion = str(payload.get("occasion") or "dinner")
        for key in ("avoid", "prefer", "mustInclude", "must_include"):
            value = payload.get(key)
            if isinstance(value, list):
                target = req.avoid if key.startswith("avoid") else (
                    req.prefer if key.startswith("prefer") else req.must_include
                )
                target.extend(str(v) for v in value)
            elif isinstance(value, str) and value.strip():
                value = value.strip()
                target = req.avoid if key.startswith("avoid") else (
                    req.prefer if key.startswith("prefer") else req.must_include
                )
                target.extend(part.strip() for part in value.replace("，", ",").split(",") if part.strip())
        calorie = payload.get("maxCalories") or payload.get("max_calories")
        if calorie:
            try:
                req.max_calories = int(calorie)
            except (TypeError, ValueError):
                pass
        dessert = payload.get("withDessert", payload.get("with_dessert"))
        if dessert is not None:
            req.with_dessert = bool(dessert)
        return req


@dataclass
class PlanLine:
    code: str
    name: str
    kind: str
    qty: int
    price: int  # 单价，分

    @property
    def total(self) -> int:
        return self.qty * self.price


@dataclass
class Plan:
    occasion: str
    people: int
    budget: int
    lines: list = field(default_factory=list)  # list[PlanLine]
    subtotal: int = 0
    coupon: Optional[Coupon] = None
    coupon_saving: int = 0
    payable: int = 0
    per_person: int = 0
    calories_per_person: Optional[int] = None
    warnings: list = field(default_factory=list)
    rationale: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "occasion": self.occasion,
            "people": self.people,
            "budget": self.budget,
            "lines": [
                {
                    "code": line.code,
                    "name": line.name,
                    "kind": line.kind,
                    "qty": line.qty,
                    "price": line.price,
                    "total": line.total,
                }
                for line in self.lines
            ],
            "subtotal": self.subtotal,
            "coupon": (
                {
                    "id": self.coupon.id,
                    "name": self.coupon.name,
                    "kind": self.coupon.kind,
                    "product": self.coupon.product,
                    "threshold": self.coupon.threshold,
                    "value": self.coupon.value,
                    "dealPrice": self.coupon.deal_price,
                    "saving": self.coupon_saving,
                }
                if self.coupon
                else None
            ),
            "payable": self.payable,
            "perPerson": self.per_person,
            "caloriesPerPerson": self.calories_per_person,
            "warnings": list(self.warnings),
            "rationale": list(self.rationale),
        }
