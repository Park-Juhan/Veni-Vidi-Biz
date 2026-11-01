from app.common.web import bind_module
from app.common.validation import ValidationError
from app.common.time import korean_time


def create_blueprint(model, title, description, number):
    def prepare_submission(values,source,workspace,form):
        if form.get('use_material')=='yes':
            values['use_material']='yes'
            snapshot=model.import_material(workspace)
            if snapshot is None:
                raise ValidationError('가져올 재료 원가가 없습니다. 재료비 모듈에서 먼저 계산하거나 직접 원가를 입력하세요.')
            values['material']=str(snapshot.usage_cost)
            source+=f' / 재료비 연동: {snapshot.source}, 기준 {korean_time(snapshot.updated_at)}'
        return values,source
    return bind_module('menu_pricing', model, 'menu_pricing/index.html', title, description, number,prepare_submission)
