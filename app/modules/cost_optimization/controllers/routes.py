from datetime import datetime, timedelta, timezone
from flask import flash
from app.common.validation import ValidationError
from app.common.web import bind_module

KST = timezone(timedelta(hours=9))


def create_blueprint(model, title, description, number):
    importable = [field for _, field in model.IMPORTABLE] + ['previous']

    def current_values(workspace):
        record = model.latest(workspace)
        return model.defaults() | record.inputs if record else model.defaults()

    def keep_month_inputs(values, form):
        for key in ('bench_industry', 'bench_region'):
            if key in form: values[key] = form.get(key, '').strip()
        values['period'] = form.get('period', '').strip()
        values['save_month'] = 'yes' if form.get('save_month') == 'yes' else ''
        return values

    def handle_action(action, values, workspace, form):
        if action == 'import':
            imported = model.import_operating_costs(workspace, form.get('period', '').strip())
            values = keep_month_inputs(values | imported['values'], form)
            return values, dict(imported=imported['origins'], import_missing=imported['missing'], import_done=True)
        period = form.get('month', '').strip()
        if action == 'load_month':
            loaded = model.month_values(workspace, period)
            if loaded is None:
                return current_values(workspace), dict(action_error='불러올 월 기록을 찾지 못했습니다.')
            loaded.update(period=period, save_month='yes')
            return loaded, dict(action_message=f'{period} 기록을 불러왔습니다. 절감 가정을 정하고 계산하세요.')
        if action == 'delete_month':
            deleted = model.delete_month(workspace, period)
            return current_values(workspace), (dict(action_message=f'{period} 기록을 삭제했습니다.') if deleted
                                               else dict(action_error='삭제할 월 기록을 찾지 못했습니다.'))
        return values, {}

    def prepare_submission(values, source, workspace, form):
        keep_month_inputs(values, form)
        if model.benchmarks and values.get('bench_industry') != 'none':
            source += ' / 소상공인실태조사 업종 평균 비교'
        if values['save_month'] and not model.PERIOD.match(values['period']):
            raise ValidationError('월별 기록으로 저장하려면 기록할 월을 선택하세요.')
        # Hidden "import_<field>" inputs remember what was filled in; credit a source only if the value was kept.
        names = {field.name: field.label.split(' (')[0] for field in model.fields}
        kept = []
        for field in importable:
            remembered = form.get('import_' + field, '')
            imported_value, _, label = remembered.partition('|')
            if label and values.get(field, '').strip() == imported_value:
                kept.append(f"{names[field]} ← {label.split(' · ')[0]}")
        if kept:
            source += ' / 다른 모듈 값 사용: ' + ', '.join(kept)
        if values['save_month']:
            source += f" / {values['period']} 월별 기록으로 저장"
        return values, source

    def after_save(record, workspace, form):
        if record.inputs.get('save_month') == 'yes' and model.save_month(workspace, record.inputs['period'], record.inputs):
            flash(f"{record.inputs['period']} 매출·비용을 월별 기록에 저장했습니다.")

    def view_context(workspace):
        industries, regions = model.benchmark_choices()
        return dict(bench_industries=industries, bench_regions=regions, bench_default=model.DEFAULT_BENCHMARK,
                    market_data_title='다른 모듈 결과를 불러오고 소상공인실태조사 업종 평균과 비교해 할 일을 추천합니다' if industries else '다른 모듈 결과를 불러와 할 일을 추천합니다',
                    can_import=bool(model.cost_providers), months_enabled=model.financials is not None,
                    months=model.list_months(workspace), this_month=datetime.now(KST).strftime('%Y-%m'))

    return bind_module('cost_optimization', model, 'cost_optimization/index.html', title, description, number,
                       prepare_submission, handle_action, after_save=after_save, view_context=view_context)
