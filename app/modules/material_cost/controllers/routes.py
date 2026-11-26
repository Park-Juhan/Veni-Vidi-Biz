from flask import flash, g
from app.common.validation import ValidationError
from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    def current_values(workspace):
        record = model.latest(workspace)
        return model.defaults() | record.inputs if record else model.defaults()

    def prepare_submission(values, source, workspace, form):
        if form.get('save_material') == 'yes':
            values['save_material'] = 'yes'
        return values, source

    def after_save(record, workspace, form):
        if form.get('save_material') == 'yes' and model.save_material(workspace, record.inputs):
            flash(f"'{record.inputs['name'].strip()}'을(를) 내 재료 목록에 저장했습니다. 메뉴 가격 모듈의 레시피 계산에서 쓸 수 있습니다.")

    def handle_action(action, values, workspace, form):
        if action == 'set_market':
            try:
                material_id = int(form.get('material_id', ''))
            except ValueError:
                return current_values(workspace), dict(action_error='시세를 연결할 재료를 고르세요.')
            choice = form.get('market_choice', '')
            text = form.get('market_item', '') if choice == 'pick' else choice
            try:
                changed = model.set_market_item(workspace, material_id, text)
            except ValidationError as exc:
                g.market_form = dict(material_id=material_id, market_item=form.get('market_item', ''), market_choice=choice)
                return current_values(workspace), dict(action_error=str(exc))
            if not changed:
                return current_values(workspace), dict(action_error='시세를 연결할 재료를 찾지 못했습니다. 화면을 새로고침해 주세요.')
            return current_values(workspace), dict(action_message={'auto': '이름이 같은 시세 품목으로 자동 비교합니다.', 'none': '이 재료는 시세와 비교하지 않습니다.'}.get(choice, '시세 품목을 연결했습니다.'))
        if action != 'delete_material':
            return values, {}
        try:
            deleted = model.delete_material(workspace, int(form.get('material_id', '')))
        except ValueError:
            deleted = False
        message = dict(action_message='재료를 목록에서 삭제했습니다. 이 재료를 쓰던 메뉴 레시피에서도 빠집니다.') if deleted \
            else dict(action_error='삭제할 재료를 찾지 못했습니다. 화면을 새로고침해 주세요.')
        return current_values(workspace), message

    def view_context(workspace):
        options = model.market_options()
        return dict(catalog_enabled=model.catalog is not None, materials=model.list_materials(workspace),
                    market_options=options, market_form=g.get('market_form') or {},
                    market_data_title='입력 기반 계산 · KAMIS 소매 시세 비교 가능' if options else None)

    return bind_module('material_cost', model, 'material_cost/index.html', title, description, number,
                       prepare_submission, handle_action, after_save=after_save, view_context=view_context)
