from flask import g
from app.common.validation import ValidationError
from app.common.web import bind_module


def create_blueprint(model, title, description, number):
    candidate_keys = ('name', 'rent', 'deposit', 'area', 'interior', 'fit', 'traffic', 'facility')

    def current_values(workspace):
        record = model.latest(workspace)
        return record.inputs.copy() if record else model.defaults()

    def selected_ids(form):
        ids = set()
        for value in form.getlist('compare'):
            try:
                ids.add(int(value))
            except ValueError:
                pass
        return ids

    def prepare_submission(values, source, workspace, form):
        # Saved candidates: only the ticked ones. Nothing saved: the two fictional examples.
        candidates, saved = model.candidates_for(workspace, selected_ids(form) if form.get('compare_sent') else None)
        values['candidates'] = candidates
        values['compare'] = sorted(int(c['id']) for c in candidates if 'id' in c)
        source += f' / 저장한 후보 {len(candidates)}곳 비교' if saved else ' / 가상 예시 후보 2곳 비교'
        return values, source

    def handle_action(action, values, workspace, form):
        try:
            candidate_id = int(form.get('candidate_id', '')) or None
        except ValueError:
            candidate_id = None
        if action == 'save_candidate':
            typed = {key: form.get('cand_' + key, '') for key in candidate_keys}
            try:
                model.save_candidate(workspace, typed, candidate_id)
            except ValidationError as exc:
                g.candidate_form, g.editing_id = typed, candidate_id
                return current_values(workspace), dict(action_error=str(exc))
            return current_values(workspace), dict(action_message=f"후보 '{typed['name'].strip()}'을(를) {'수정' if candidate_id else '추가'}했습니다. 비교할 후보에서 선택해 계산하세요.")
        if action == 'edit_candidate':
            found = next((c for c in model.list_candidates(workspace) if c['id'] == candidate_id), None)
            if found is None:
                return current_values(workspace), dict(action_error='수정할 후보를 찾지 못했습니다.')
            g.candidate_form, g.editing_id = {key: found[key] for key in candidate_keys}, candidate_id
            return current_values(workspace), dict(action_message=f"'{found['name']}' 후보를 아래 양식에서 수정하세요.")
        if action == 'delete_candidate':
            deleted = model.delete_candidate(workspace, candidate_id) if candidate_id else False
            return current_values(workspace), (dict(action_message='후보를 삭제했습니다.') if deleted else dict(action_error='삭제할 후보를 찾지 못했습니다.'))
        if action == 'add_examples':
            added = model.add_example_candidates(workspace)
            return current_values(workspace), dict(action_message=f'가상 예시 후보 {len(added)}곳을 추가했습니다.' if added else '가상 예시 후보가 이미 목록에 있습니다.')
        return values, {}

    def view_context(workspace):
        return dict(candidates_enabled=model.candidate_store is not None, saved_candidates=model.list_candidates(workspace),
                    candidate_form=g.get('candidate_form') or {}, editing_id=g.get('editing_id'),
                    example_candidates=model.defaults()['candidates'])

    return bind_module('property', model, 'property/index.html', title, description, number,
                       prepare_submission, handle_action, view_context=view_context)
