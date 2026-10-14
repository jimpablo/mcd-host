"""凑桌算法：请客场景下的「一桌菜」怎么点。

设计原则（全部可解释、可复现）：
- 套餐优先：有套餐时每人一份套餐，通常比单点划算；
- 不加东西：只在购物车里已有的品类里做选择，绝不为了凑数多加品类；
- 预算优先：核心（主食/饮料）必须满足，其次小食，最后甜品；超预算时降级；
- 一单一张券：MCP 规则一单只能用一张券，只从传入的券里挑最省的一张。
"""

from __future__ import annotations

from typing import Optional

from .model import (
    Coupon,
    KIND_ORDER,
    MenuItem,
    Plan,
    PlanLine,
    PlanRequest,
    fuzzy_lookup,
    normalize_nutrition,
)

_DESSERT_OCCASIONS = {"dinner", "tea", "birthday", "team"}
_SHARED_SIDE_PER = 2   # 每几人一份共享小食
_SHARED_DESSERT_PER = 3  # 每几人一份甜品
_MAX_DISTINCT_MAIN = 3
_MAX_DISTINCT_DRINK = 2
_MAX_DISTINCT_SIDE = 2
_MAX_DISTINCT_DESSERT = 2
_MIN_GUEST_SET_PRICE = 2000  # 低于 ¥20 的「套餐」是单人随心配（如 1+1），不当请客正餐


def _match_any(name: str, keywords) -> bool:
    return any(k and k in name for k in keywords)


def _pick_distinct(candidates: list, want: int, people: int) -> list:
    """从候选里挑最多 want 个不同的餐品，返回 [(item, qty), ...]，份数尽量平均。"""
    if not candidates or want <= 0:
        return []
    k = min(want, len(candidates), max(1, people))
    picked = candidates[:k]
    base, extra = divmod(people, k)
    return [(item, base + (1 if i < extra else 0)) for i, item in enumerate(picked)]


def _distribute(total: int, kinds: int) -> list:
    """把 total 份平均分给 kinds 个品类，返回每类的份数列表。"""
    if kinds <= 0:
        return []
    base, extra = divmod(total, kinds)
    return [base + (1 if i < extra else 0) for i in range(kinds)]


def pick_coupon(coupons: list, subtotal: int) -> tuple:
    """从券里挑一张最省的满减券。返回 (coupon, saving, gap_hint)。"""
    best = None
    best_saving = 0
    nearest = None  # (gap, coupon)
    for coupon in coupons:
        if not coupon.is_threshold:
            continue
        if coupon.threshold <= subtotal:
            saving = coupon.value or 0
            if saving > best_saving:
                best, best_saving = coupon, saving
        else:
            gap = coupon.threshold - subtotal
            if nearest is None or gap < nearest[0]:
                nearest = (gap, coupon)
    gap_hint = None
    if best is None and nearest is not None:
        gap, coupon = nearest
        gap_hint = {
            "gap": gap,
            "coupon": coupon.name,
            "saving": coupon.value or 0,
            "message": f"再加 ¥{gap / 100:.2f} 可用「{coupon.name}」省 ¥{(coupon.value or 0) / 100:.2f}",
        }
    return best, best_saving, gap_hint


def _coupon_bonus(coupons: list, name: str, price: int) -> int:
    """估算某餐品用券后每单位能省多少（用于选品时按券后价排序）。

    bogo 按「买两份省一份」估算（共享小食/多人套餐通常不止一份）；
    最终省多少以 plan 汇总时的精确计算为准。
    """
    bonus = 0
    for coupon in coupons:
        if coupon.kind == "threshold":
            continue
        product = coupon.product or coupon.name
        if not product or not (product in name or name in product):
            continue
        if coupon.kind == "bogo":
            bonus = max(bonus, price // 2)
        elif coupon.kind == "fixed" and coupon.deal_price is not None:
            bonus = max(bonus, max(0, price - coupon.deal_price))
    return bonus


def _product_coupon_saving(coupon, lines: list) -> tuple:
    """商品券能省多少。返回 (saving, matched_names)。

    - fixed（用券价格）：单价低于菜单价的部分 × 份数；
    - bogo（买一送一）：每两份省一份的价钱。
    """
    product = coupon.product or coupon.name
    if not product:
        return 0, []
    saving = 0
    matched = []
    for line in lines:
        if product in line.name or line.name in product:
            matched.append(line.name)
            if coupon.kind == "bogo":
                saving += (line.qty // 2) * line.price
            elif coupon.kind == "fixed" and coupon.deal_price is not None:
                saving += max(0, line.price - coupon.deal_price) * line.qty
    return (saving, matched) if matched else (0, [])


def _coupon_hints(coupons: list, lines: list) -> list:
    """差一点就能用上的券，给出 actionable 提示。"""
    hints = []
    for coupon in coupons:
        if coupon.kind != "bogo":
            continue
        product = coupon.product or coupon.name
        if not product:
            continue
        for line in lines:
            if line.qty == 1 and (product in line.name or line.name in product):
                hints.append(
                    f"「{coupon.name}」买一送一，把{line.name}加到 2 份可以再省一份的钱"
                )
    return hints


class _Pool:
    def __init__(self, menu: list, req: PlanRequest, coupons: list = None):
        self.req = req
        self.filtered_out = []
        self.by_kind = {kind: [] for kind in KIND_ORDER}
        for item in menu:
            must = _match_any(item.name, req.must_include) or item.code in req.must_include
            if not must and _match_any(item.name, req.avoid):
                self.filtered_out.append(item.name)
                continue
            self.by_kind[item.kind].append(item)
        # 每类按「券后有效价」升序，偏好关键词优先（同价位时排前）
        for kind, items in self.by_kind.items():
            items.sort(
                key=lambda it: (
                    0 if _match_any(it.name, req.prefer) else 1,
                    it.price - _coupon_bonus(coupons or [], it.name, it.price),
                    it.name,
                )
            )

    def take(self, kind: str) -> list:
        return list(self.by_kind.get(kind, []))


def build_plan(menu: list, coupons: list, req: PlanRequest, nutrition: Optional[dict] = None) -> Plan:
    if nutrition and not all(isinstance(v, int) for v in nutrition.values()):
        # 传进来的是 list-nutrition-foods 原始返回，先归一化
        nutrition = normalize_nutrition(nutrition)
    nutrition = nutrition or {}
    pool = _Pool(menu, req, coupons)
    plan = Plan(occasion=req.occasion, people=req.people, budget=req.budget)

    if req.people > 1:
        plan.rationale.append(f"按 {req.people} 人请客搭配：主食/饮料按人分配，小食和甜品全桌共享。")

    must_codes = set(req.must_include)
    lines = []
    handled_codes = set()

    def add_lines(pairs):
        for item, qty in pairs:
            if qty <= 0:
                continue
            lines.append(PlanLine(code=item.code, name=item.name, kind=item.kind, qty=qty, price=item.price))
            handled_codes.add(item.code)

    def total_of(ls):
        return sum(line.total for line in ls)

    sets = [s for s in pool.take("set") if s.price >= _MIN_GUEST_SET_PRICE]
    skipped_sets = [s for s in pool.take("set") if s.price < _MIN_GUEST_SET_PRICE]
    mains = pool.take("main")
    drinks = pool.take("drink")
    sides = pool.take("side")
    desserts = pool.take("dessert")

    want_dessert = req.with_dessert
    if want_dessert is None:
        want_dessert = req.occasion in _DESSERT_OCCASIONS

    budget = req.budget if req.budget > 0 else None
    per_person_budget = (budget // req.people) if budget else None

    if sets:
        # 策略 A：每人一份套餐（最多 3 种轮换），小食/甜品看预算加
        plan.rationale.append("本店有套餐，优先每人一份套餐，通常比单点划算。")
        pairs = _pick_distinct(sets, _MAX_DISTINCT_MAIN, req.people)
        if per_person_budget is not None:
            affordable = [(it, q) for it, q in pairs if it.price <= per_person_budget]
            if affordable:
                pairs = affordable
            else:
                cheapest = min(sets, key=lambda s: s.price)
                pairs = [(cheapest, req.people)]
                plan.warnings.append(f"人均预算内没有合适套餐，已按最低价套餐「{cheapest.name}」配置。")
        add_lines(pairs)
        core = total_of(lines)
        if core > (budget or core + 1):
            # 套餐都超预算：退回最便宜的套餐
            lines = [lines[0]] if lines else []
            if lines:
                lines[0] = PlanLine(
                    code=lines[0].code, name=lines[0].name, kind=lines[0].kind,
                    qty=req.people, price=lines[0].price,
                )
            core = total_of(lines)
            plan.warnings.append("最便宜的套餐也超出了总预算，已按最低成本配置。")
    else:
        # 策略 B：单点。主食、饮料按人；小食共享；甜品看预算。
        plan.rationale.append("本店没有合适套餐，按单点搭配：主食和饮料按人，小食全桌共享。")
        main_pairs = _pick_distinct(mains, _MAX_DISTINCT_MAIN, req.people)
        if per_person_budget is not None:
            ok = [(it, q) for it, q in main_pairs if it.price <= per_person_budget]
            if ok:
                main_pairs = ok
            elif mains:
                cheapest = min(mains, key=lambda m: m.price)
                main_pairs = [(cheapest, req.people)]
        drink_pairs = _pick_distinct(drinks, _MAX_DISTINCT_DRINK, req.people)
        add_lines(main_pairs)
        add_lines(drink_pairs)
        core = total_of(lines)
        if core > (budget or core + 1):
            # 降级：主食和饮料都取最便宜
            lines = []
            if mains:
                cheapest_main = min(mains, key=lambda m: m.price)
                add_lines([(cheapest_main, req.people)])
            if drinks:
                cheapest_drink = min(drinks, key=lambda d: d.price)
                add_lines([(cheapest_drink, req.people)])
            core = total_of(lines)
            plan.warnings.append("预算紧张，主食和饮料已降到最低价组合。")

    # must_include 里还没安排的补上
    for code in must_codes:
        if code in handled_codes:
            continue
        for item in menu:
            if item.code == code:
                add_lines([(item, 1)])
                plan.rationale.append(f"已按你指定的必点加入「{item.name}」。")
                break

    # 共享小食（核心已超预算时就不要再加了）
    if sides and (budget is None or total_of(lines) <= budget):
        want_total = -(-req.people // _SHARED_SIDE_PER)  # ceil
        pairs = _pick_distinct(sides, _MAX_DISTINCT_SIDE, want_total)
        add_lines(pairs)

    # 甜品
    if want_dessert and desserts and (budget is None or total_of(lines) <= budget):
        want_total = -(-req.people // _SHARED_DESSERT_PER)
        pairs = _pick_distinct(desserts, _MAX_DISTINCT_DESSERT, want_total)
        add_lines(pairs)
        plan.rationale.append(f"场合是{req.occasion}，加了 {want_total} 份甜品全桌分享。")
    elif not want_dessert:
        plan.rationale.append("这场合没配甜品；想要的话加 --with-dessert。")

    # 预算内尽量填满：优先加甜品，再加小食；同类轮着加，避免全堆在最便宜的那一样上
    if budget is not None:
        spent = total_of(lines)
        room = budget - spent
        side_cap = req.people
        dessert_cap = max(-(-req.people // _SHARED_DESSERT_PER), -(-req.people // 2))
        for kind, cap in (("dessert", dessert_cap if want_dessert else 0), ("side", side_cap)):
            if room <= 0:
                break
            existing = [line for line in lines if line.kind == kind]
            current_qty = sum(line.qty for line in existing)
            pool_items = [item for item in pool.take(kind) if item.price <= room]
            if not pool_items:
                continue
            order = pool_items if not existing else sorted(
                pool_items, key=lambda item: min(
                    (abs(line.qty - 1) for line in existing if line.code == item.code), default=0
                )
            )
            index = 0
            while current_qty < cap and order:
                item = order[index % len(order)]
                if item.price > room:
                    break
                target = next((line for line in lines if line.code == item.code), None)
                if target is not None:
                    target.qty += 1
                else:
                    lines.append(
                        PlanLine(code=item.code, name=item.name, kind=item.kind, qty=1, price=item.price)
                    )
                room -= item.price
                current_qty += 1
                index += 1
        if room > 0:
            plan.rationale.append(f"预算还剩 ¥{room / 100:.2f}，可以考虑现场升级大杯/大薯。")

    if skipped_sets:
        names = "、".join(s.name for s in skipped_sets)
        plan.rationale.append(f"「{names}」是单人随心配，没算进请客正餐。")

    # 汇总
    plan.lines = sorted(lines, key=lambda line: (KIND_ORDER.index(line.kind) if line.kind in KIND_ORDER else 99, line.price))
    plan.subtotal = total_of(plan.lines)

    # 选券：满减券和商品券一起比，一单一张券，挑最省的（MCP 规则）
    best = None  # (coupon, saving, matched_names)
    threshold_coupon, threshold_saving, gap_hint = pick_coupon(coupons, plan.subtotal)
    if threshold_coupon is not None:
        best = (threshold_coupon, threshold_saving, [])
    for coupon in coupons:
        if coupon.kind == "threshold":
            continue
        saving, matched = _product_coupon_saving(coupon, plan.lines)
        if saving > 0 and (best is None or saving > best[1]):
            best = (coupon, saving, matched)
    if best is not None:
        plan.coupon, plan.coupon_saving, matched_names = best
    else:
        matched_names = []
    plan.payable = plan.subtotal - plan.coupon_saving
    if plan.payable < 0:
        plan.payable = plan.subtotal
        plan.warnings.append("券面额超过应付金额，按无券计算。")
    plan.per_person = -(-plan.payable // req.people)  # 向上取整到分

    if plan.coupon is not None:
        kind_label = {"threshold": "满减券", "fixed": "商品券", "bogo": "买一送一券"}.get(plan.coupon.kind, "券")
        target = f"（{'、'.join(matched_names)}）" if matched_names else ""
        plan.rationale.append(
            f"用{kind_label}「{plan.coupon.name}」{target}省 ¥{plan.coupon_saving / 100:.2f}"
            "（MCP 一单只能用一张券，已挑最省的）。"
        )
    elif gap_hint is not None:
        plan.rationale.append(gap_hint["message"])
    for hint in _coupon_hints(coupons, plan.lines):
        if plan.coupon is None or plan.coupon.kind != "bogo":
            plan.rationale.append(hint)

    if budget is not None and plan.payable > budget:
        plan.warnings.append(
            f"应付 ¥{plan.payable / 100:.2f} 超出预算 ¥{budget / 100:.2f}，可以减人、减小食或换更便宜的套餐。"
        )
    if pool.filtered_out:
        plan.rationale.append(f"已避开忌口：{'、'.join(sorted(set(pool.filtered_out)))}。")

    # 热量（每人约值，甜品/小食按共享估算；营养名和菜单名允许规格差异）
    total_calorie = 0
    matched = 0
    for line in plan.lines:
        _, calorie = fuzzy_lookup(line.name, nutrition)
        if calorie:
            total_calorie += calorie * line.qty
            matched += 1
    if matched:
        plan.calories_per_person = total_calorie // req.people
        if matched < len(plan.lines):
            plan.rationale.append(
                f"营养表只覆盖 {matched}/{len(plan.lines)} 项，人均热量是下限。"
            )
        if req.max_calories and plan.calories_per_person > req.max_calories:
            plan.warnings.append(
                f"人均约 {plan.calories_per_person} 千卡，超过你设定的 {req.max_calories} 千卡上限。"
            )

    return plan
