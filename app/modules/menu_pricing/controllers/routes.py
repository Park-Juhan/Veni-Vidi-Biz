from flask import flash
from app.common.web import bind_module
from app.common.validation import ValidationError
from app.common.time import korean_time


def create_blueprint(model, title, description, number):
    def recipe_rows(source):
        return [(source.get(f'recipe_material_{i}', ''), source.get(f'recipe_qty_{i}', '')) for i in range(model.RECIPE_ROWS)]

    def current_values(workspace):
        record = model.latest(workspace)
        return record.inputs.copy() if record else model.defaults()

    def prepare_submission(values, source, workspace, form):
        use_recipe = form.get('use_recipe') == 'yes'
        if use_recipe:
            values['use_recipe'] = 'yes'
            # Keep the rows so the form shows them again (also after a validation error).
            for i, (material_id, quantity) in enumerate(recipe_rows(form)):
                values[f'recipe_material_{i}'], values[f'recipe_qty_{i}'] = material_id, quantity
        if form.get('use_material') == 'yes':
            values['use_material'] = 'yes'
            if use_recipe:
                raise ValidationError('재료비 가져오기와 레시피 계산 중 하나만 선택하세요.')
            snapshot = model.import_material(workspace)
            if snapshot is None:
                raise ValidationError('가져올 재료 원가가 없습니다. 재료비 모듈에서 먼저 계산하거나 직접 원가를 입력하세요.')
            values['material'] = str(snapshot.usage_cost)
            source += f' / 재료비 연동: {snapshot.source}, 기준 {korean_time(snapshot.updated_at)}'
        if use_recipe:
            total, _, description = model.recipe_cost(workspace, recipe_rows(form))
            # Plain digits without trailing zeros (860.0 -> 860, 12.50 -> 12.5).
            values['material'] = f'{total.normalize():f}'
            source += f' / 레시피 합산 (내 재료 목록 단가): {description}'
        return values, source

    def after_save(record, workspace, form):
        if record.inputs.get('use_recipe') == 'yes':
            _, items, _ = model.recipe_cost(workspace, recipe_rows(record.inputs))
            if model.save_recipe(workspace, record.inputs['name'], items):
                flash(f"메뉴 '{record.inputs['name'].strip()}'의 레시피를 저장했습니다.")

    def handle_action(action, values, workspace, form):
        try:
            menu_id = int(form.get('menu_id', ''))
        except ValueError:
            menu_id = None
        if action == 'load_menu':
            menu = model.get_menu(workspace, menu_id) if menu_id else None
            if menu is None:
                return current_values(workspace), dict(action_error='불러올 메뉴를 찾지 못했습니다.')
            values = current_values(workspace)
            values.update(name=menu['name'], use_recipe='yes', use_material='')
            for i in range(model.RECIPE_ROWS):
                item = menu['items'][i] if i < len(menu['items']) else None
                values[f'recipe_material_{i}'] = str(item['material_id']) if item else ''
                values[f'recipe_qty_{i}'] = f"{item['quantity']:f}" if item else ''
            return values, dict(action_message=f"메뉴 '{menu['name']}'의 레시피를 불러왔습니다. 가격 조건을 확인하고 계산하세요.")
        if action == 'delete_menu':
            deleted = model.delete_menu(workspace, menu_id) if menu_id else False
            return current_values(workspace), (dict(action_message='메뉴 레시피를 삭제했습니다.') if deleted
                                               else dict(action_error='삭제할 메뉴를 찾지 못했습니다.'))
        return values, {}

    def view_context(workspace):
        return dict(recipe_enabled=model.recipes is not None, recipe_rows=model.RECIPE_ROWS,
                    saved_materials=model.materials(workspace), menus=model.list_menus(workspace))

    return bind_module('menu_pricing', model, 'menu_pricing/index.html', title, description, number,
                       prepare_submission, handle_action, after_save=after_save, view_context=view_context)
