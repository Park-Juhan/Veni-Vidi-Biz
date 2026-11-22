"""One-at-a-time sensitivity of monthly operating profit (before savings)."""
from decimal import Decimal


STEPS = (Decimal(-20), Decimal(-10), Decimal(10), Decimal(20))
# (label, how a change of d% moves revenue and costs)
FACTORS = (
    ('매출 (재료비 함께 변동)', 'revenue'),
    ('재료비', 'material'),
    ('인건비', 'labor'),
    ('임대료', 'rent'),
)


def profit_after(v, total, factor, pct):
    """Operating profit when one factor changes by pct percent, others fixed."""
    ratio = pct / 100
    revenue, cost = v['revenue'], total
    if factor == 'revenue':
        # Material is a variable cost in this module, so it moves with revenue.
        revenue += v['revenue'] * ratio
        cost += v['material'] * ratio
    else:
        cost += v[factor] * ratio
    return revenue - cost


def sensitivity_table(v, total):
    base = v['revenue'] - total
    rows, swings = [], []
    for label, factor in FACTORS:
        profits = [profit_after(v, total, factor, step) for step in STEPS]
        swing = max(profits) - min(profits)
        swings.append((swing, label))
        rows.append([label, profits[0], profits[1], base, profits[2], profits[3], swing])
    top = max(swings)
    lead = (f"월 운영 손익에 가장 크게 영향을 주는 요인은 '{top[1]}'입니다 (±20% 변동 시 폭 {top[0]:,.0f}원)."
            if top[0] > 0 else '입력된 값이 모두 0이어서 변동 영향이 없습니다.')
    return dict(tab='민감도', title='요인별 ±10·20% 변동 시 월 운영 손익 (원)', lead=lead,
                columns=['요인', '-20%', '-10%', '기준', '+10%', '+20%', '±20% 변동 폭'], rows=rows,
                note='한 번에 한 요인만 바꾸고 나머지는 그대로 둡니다. 절감 시나리오 적용 전 손익입니다. 매출이 변하면 재료비도 같은 비율로 변한다고 가정합니다.')
