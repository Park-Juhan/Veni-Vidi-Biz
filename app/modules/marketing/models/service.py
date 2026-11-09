from decimal import ROUND_CEILING
from app.common.model import AnalysisModel
from app.common.validation import Field
from .decision_engine.engine import compare_channels


class MarketingModel(AnalysisModel):
    fields=(
        Field('business','사업 아이템 / 업종','동네 카페','text'),
        Field('target','목표 고객층','인근 직장인','select',choices=('인근 직장인','동네 주민','학생·청년','폭넓은 고객')),
        Field('scale','사업 규모','1인 매장','select',choices=('1인 매장','소규모 팀 매장')),
        Field('goal','홍보 목적','신규 고객 유입','select',choices=('신규 고객 유입','재방문 유도','브랜드 인지도')),
        Field('budget','월 홍보 예산 (원)','300000'),
        Field('hours','주당 운영 가능 시간','4',maximum='168'),
        Field('ticket','평균 객단가 (원)','8000',group='손익분기 계산',help='고객 1명이 한 번 방문해 쓰는 평균 금액'),
        Field('contribution_rate','공헌이익률 (%)','60',maximum='100',group='손익분기 계산',help='매출에서 재료비 등 변동비를 뺀 비율. 메뉴 가격 모듈 결과를 참고하세요.'),
    )

    def calculate(self,v):
        decision=compare_channels(v)
        candidates=decision['candidates']
        eligible=[c for c in candidates if c['feasible']]
        facts=decision['facts'];portfolio=facts['portfolio']
        unit=v['ticket']*v['contribution_rate']/100
        combo_breakeven=(facts['portfolio_cost']/unit).to_integral_value(rounding=ROUND_CEILING) if unit>0 else None
        return dict(model='채널 조합 최적화 (배낭 문제)',
                    metrics=[('조건에 맞는 방법',len(eligible),'개'),('추천 조합',' + '.join(portfolio) if portfolio else '없음',''),
                             ('추천 조합 월 비용',facts['portfolio_cost'],'원'),('추천 조합 주당 시간',facts['portfolio_hours'],'시간'),
                             ('비용 회수에 필요한 추가 고객',combo_breakeven if combo_breakeven is not None else '산출 불가','명/월' if combo_breakeven is not None else '')],
                    columns=['방법','실행 주체','가상 월 비용 (원)','주당 시간','조건','적합 점수','손익분기 추가 고객 (명/월)','추천 조합','장점','유의사항'],
                    rows=[[c['name'],c['owner'],c['cost'],c['hours'],'검토 가능' if c['feasible'] else '예산 또는 시간 초과',c['score'],
                           c['breakeven'] if c['breakeven'] is not None else '산출 불가','포함' if c['name'] in portfolio else '-',c['benefit'],c['caution']] for c in candidates],
                    charts=[dict(title='시연용 마케팅 비용 비교',unit='원',data=[(c['name'],c['cost']) for c in candidates]),
                            dict(title='채널별 손익분기 추가 고객 수',unit='명',data=[(c['name'],c['breakeven']) for c in candidates if c['breakeven'] is not None])],
                    notes=['비용·시간은 실제 업체 견적이 아닌 가상 시연 값입니다. 업체명과 실제 광고 성과 자료는 제공하지 않습니다.',
                           '규칙: 목표 고객층 +2점, 홍보 목적 +2점, 1인 운영 시 저시간 채널 +1점. 예산·시간을 모두 충족하는 방법을 우선 정렬합니다.',
                           f"업종 '{v['business']}'은 검토 맥락으로 기록합니다. 업종별 효과 차이를 추정할 자료는 없습니다.",
                           '조합 최적화: 가능한 모든 채널 조합 중 예산과 주당 시간을 넘지 않으면서 적합 점수 합이 가장 큰 조합을 고릅니다(0-1 배낭 문제). 점수가 같으면 비용이 적은 조합을 우선합니다.',
                           f"손익분기 추가 고객 = 채널 비용 ÷ (객단가 × 공헌이익률) = 비용 ÷ {unit:,.0f}원. 홍보로 매달 이만큼 새 고객이 더 와야 비용을 회수합니다.",
                           '매출 증가·ROI는 예측하지 않습니다. 광고비 외 제작비·계약 기간·수수료를 실제 실행 전에 확인하세요.'
                           ]+([] if eligible else ['현재 예산과 시간에 모두 맞는 방법이 없습니다. 조건을 조정하거나 작은 실험을 계획하세요.']),trace=decision['trace'])
