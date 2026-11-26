from datetime import datetime, timedelta, timezone
from flask import flash, g, request
from app.common.web import bind_module
from app.common.validation import ValidationError

KST = timezone(timedelta(hours=9))


def create_blueprint(model, title, description, number):
    def current_values(workspace):
        record = model.latest(workspace)
        return model.defaults_for(workspace) | record.inputs if record else model.defaults_for(workspace)

    def prepare_submission(values, source, workspace, form):
        parts = ['재료비: 02 재료비 관리']
        if model.location(workspace): parts.append('임대료·상권 매출: 01 추천 상권')
        return values, ' · '.join(parts)

    def after_save(record, workspace, form):
        model.remember(workspace, record)

    def handle_action(action, values, workspace, form):
        try:
            menu_id = int(form.get('menu_id', ''))
        except ValueError:
            menu_id = None
        if action == 'delete_menu':
            deleted = model.delete_menu(workspace, menu_id) if menu_id else False
            return current_values(workspace), (dict(action_message='메뉴를 판매 기록 목록에서 삭제했습니다.') if deleted
                                               else dict(action_error='삭제할 메뉴를 찾지 못했습니다.'))
        if action in ('save_sales', 'delete_sales'):
            period = form.get('sales_period', '').strip()
            g.sales_period = period
            if action == 'delete_sales':
                deleted = model.delete_sales(workspace, period)
                g.sales_period = None
                return current_values(workspace), (dict(action_message=f'{period} 판매 기록을 삭제했습니다.') if deleted
                                                   else dict(action_error='삭제할 판매 기록이 없습니다.'))
            rows = [(menu['id'], form.get(f"sales_qty_{menu['id']}", ''), form.get(f"sales_price_{menu['id']}", ''))
                    for menu in model.list_menus(workspace)]
            try:
                count = model.save_sales(workspace, period, rows)
            except ValidationError as exc:
                g.sales_form = {menu_id: (qty, price) for menu_id, qty, price in rows}
                return current_values(workspace), dict(action_error=str(exc))
            return current_values(workspace), dict(action_message=f'{period} 판매 기록 {count}개 메뉴를 저장했습니다. 아래에서 메뉴 분석을 확인하세요.')
        return values, {}

    def view_context(workspace):
        dishes = model.dishes(workspace)
        place = model.location(workspace)
        imported = {}
        if place: imported['rent'] = f'01 추천 1순위 {place.area_name}'
        imported['volume'] = '02 재료비 관리에서 정한 판매량'
        return dict(dishes=dishes, place=place, imported=imported, submit_label='손익분기점 계산하기',
                    dish_info={d.name: dict(cost=f'{d.cost_per_serving:,.0f}', volume=f'{d.monthly_volume.normalize():f}',
                                            price=f'{model.suggested_price(d.cost_per_serving):f}') for d in dishes},
                    market_data_title='02 재료비와 01 임대료를 이어받아 계산합니다' if dishes else '재료비를 직접 넣거나 02에서 이어받아 계산합니다') | sales_context(workspace)

    def sales_context(workspace):
        menus = model.list_menus(workspace)
        if model.sales is None:
            return dict(menus=menus, sales_enabled=False)
        periods = model.sales_periods(workspace)
        wanted = g.get('sales_period') or request.args.get('period', '')
        period = wanted if model.PERIOD.match(wanted or '') else (periods[0] if periods else datetime.now(KST).strftime('%Y-%m'))
        recorded = model.sales_for(workspace, period)
        last_prices = model.latest_prices(workspace)
        typed = g.get('sales_form', {})
        form_rows = []
        for menu in menus:
            if menu['id'] in typed:
                quantity, price = typed[menu['id']]
            elif menu['id'] in recorded:
                quantity, price = (f'{value.normalize():f}' for value in recorded[menu['id']])
            else:
                quantity, price = '', (f"{last_prices[menu['id']].normalize():f}" if menu['id'] in last_prices else '')
            form_rows.append(dict(id=menu['id'], name=menu['name'], quantity=quantity, price=price))
        return dict(menus=menus, sales_enabled=True, sales_periods=periods, sales_period=period, sales_form_rows=form_rows,
                    engineering=model.menu_engineering(workspace, period) if period in periods else None)

    return bind_module('menu_pricing', model, 'menu_pricing/index.html', title, description, number,
                       prepare_submission, handle_action, after_save=after_save, view_context=view_context,
                       defaults_for=model.defaults_for)
