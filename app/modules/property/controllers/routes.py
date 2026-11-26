import json
from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    def prepare_submission(values, source, workspace, form):
        values['districts'] = form.getlist('districts')
        where = ', '.join(values['districts']) if values['districts'] else '서울 전체'
        source = f"{where} 상권 추천 · 서울시 상권분석서비스, 부동산원 임대료"
        if model.startup:
            source += ', 소상공인실태조사'
        return values, source

    def view_context(workspace):
        industries = model.industries()
        return dict(industries=industries, districts=model.districts(),
                    suggestions_json=json.dumps(model.suggestions(), ensure_ascii=False),
                    data_ready=bool(industries) and model.rents is not None,
                    market_data_title='서울 상권 공공데이터로 후보 상권을 골라 드립니다' if industries else '상권 공공데이터를 불러오면 추천을 쓸 수 있습니다')

    return bind_module('property', model, 'property/index.html', title, description, number,
                       prepare_submission, view_context=view_context)
