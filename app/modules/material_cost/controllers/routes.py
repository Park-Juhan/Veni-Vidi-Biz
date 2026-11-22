from flask import flash
from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    def current_values(workspace):
        record = model.latest(workspace)
        return record.inputs.copy() if record else model.defaults()

    def prepare_submission(values, source, workspace, form):
        if form.get('save_material') == 'yes':
            values['save_material'] = 'yes'
        return values, source

    def after_save(record, workspace, form):
        if form.get('save_material') == 'yes' and model.save_material(workspace, record.inputs):
            flash(f"'{record.inputs['name'].strip()}'을(를) 내 재료 목록에 저장했습니다. 메뉴 가격 모듈의 레시피 계산에서 쓸 수 있습니다.")

    def handle_action(action, values, workspace, form):
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
        return dict(catalog_enabled=model.catalog is not None, materials=model.list_materials(workspace))

    return bind_module('material_cost', model, 'material_cost/index.html', title, description, number,
                       prepare_submission, handle_action, after_save=after_save, view_context=view_context)
