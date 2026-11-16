from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    def handle_action(action, values, workspace, form):
        """Fill inputs from other modules' latest results without calculating."""
        if action != 'import':
            return values, {}
        imported = model.import_operating_costs(workspace)
        values = values | imported['values']
        return values, dict(imported=imported['origins'], import_missing=imported['missing'], import_done=True)

    def prepare_submission(values, source, workspace, form):
        # Hidden "import_<field>" inputs remember what was filled in; credit a module only if the value was kept.
        names = {field.name: field.label.split(' (')[0] for field in model.fields}
        kept = []
        for _, field in model.IMPORTABLE:
            remembered = form.get('import_' + field, '')
            imported_value, _, label = remembered.partition('|')
            if label and values.get(field, '').strip() == imported_value:
                kept.append(f'{names[field]} ← {label[:120]}')
        if kept:
            source += ' / 다른 모듈 값 사용: ' + ', '.join(kept)
        return values, source

    return bind_module('cost_optimization', model, 'cost_optimization/index.html', title, description, number,
                       prepare_submission, handle_action, extra_context=dict(can_import=bool(model.cost_providers)))
