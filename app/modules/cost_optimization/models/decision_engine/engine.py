from decimal import Decimal
from app.common.decision import Blackboard, KnowledgeSource, ControlComponent, ResultGenerator


CAUTIONS={
    'rent':'재계약·공간 조정 검토: 위약금·이전비·고객 접근성 확인',
    'labor':'근무 동선·업무 배치 개선: 최저임금·근로계약 준수, 서비스 품질 확인',
    'material':'발주·폐기율 점검: 품질·위생·수급 안정성 유지',
    'utilities':'에너지 사용·관리비 점검: 위생·안전 설비 유지',
    'advertising':'채널별 성과 확인 후 재배분: 신규 유입 감소 위험',
    'other':'정기 결제·수수료 점검: 세금·이자·필수 비용 임의 미납 금지',
}


def compare_savings(v,categories,total):
    board=Blackboard(v, facts={'total':total})
    def structure(b):
        for key,label,*_ in categories:
            b.candidates.append(dict(key=key,label=label,cost=v[key],share=v[key]/total*100 if total else Decimal(0),rate=v[key+'_rate']))
    def scenarios(b):
        for c in b.candidates:
            c['saving']=c['cost']*c['rate']/100
            c['caution']=CAUTIONS[c['key']]
        b.candidates.sort(key=lambda c:c['saving'],reverse=True)
    ControlComponent().run(board,[KnowledgeSource('비용 구조와 비중 분석',structure),KnowledgeSource('입력 감축률별 대안·위험 종합',scenarios)])
    return ResultGenerator().generate(board)
