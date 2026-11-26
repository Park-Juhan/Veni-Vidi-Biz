from flask import flash
from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    def current_values(workspace):
        record = model.latest(workspace)
        return model.defaults() | record.inputs if record else model.defaults()

    def prepare_submission(values, source, workspace, form):
        return values, f"표준 레시피 · {'공공 소매 시세' if model.prices else '가정 단가'}"

    def after_save(record, workspace, form):
        model.remember(workspace, record)
        if model.dishes:
            flash(f"'{record.result['dish']}'의 재료비를 저장했습니다. 메뉴 가격 관리(03)에서 바로 쓸 수 있습니다.")

    def handle_action(action, values, workspace, form):
        try:
            item_id = int(form.get('item_id', ''))
        except ValueError:
            item_id = None
        if action == 'delete_dish':
            done = item_id is not None and model.delete_dish(workspace, item_id)
            return current_values(workspace), dict(action_message='메뉴를 목록에서 삭제했습니다.') if done else dict(action_error='삭제할 메뉴를 찾지 못했습니다.')
        if action == 'delete_material':
            done = item_id is not None and model.delete_material(workspace, item_id)
            return current_values(workspace), dict(action_message='재료를 목록에서 삭제했습니다.') if done else dict(action_error='삭제할 재료를 찾지 못했습니다.')
        return values, {}

    def view_context(workspace):
        return dict(dish_groups=model.dish_groups(), dishes=model.dishes.list(workspace) if model.dishes else [],
                    catalog_enabled=model.catalog is not None, materials=model.list_materials(workspace),
                    submit_label='재료비 계산하기',
                    market_data_title='음식을 고르면 재료와 원가를 공공 시세로 계산합니다' if model.prices else '음식을 고르면 표준 레시피로 재료와 원가를 계산합니다')

    return bind_module('material_cost', model, 'material_cost/index.html', title, description, number,
                       prepare_submission, handle_action, after_save=after_save, view_context=view_context)
