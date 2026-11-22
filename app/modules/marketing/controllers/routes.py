from datetime import datetime, timedelta, timezone
from flask import g
from app.common.validation import ValidationError
from app.common.web import bind_module

KST = timezone(timedelta(hours=9))
CAMPAIGN_KEYS = ('name', 'channel', 'owner', 'started_on', 'ended_on', 'cost', 'hours_per_week',
                 'new_customers', 'revenue_before', 'revenue_after', 'note')


def create_blueprint(model, title, description, number):
    def current_values(workspace):
        record = model.latest(workspace)
        return record.inputs.copy() if record else model.defaults()

    def prepare_submission(values, source, workspace, form):
        history = model.channel_summary(workspace)
        values['history'] = history
        if history:
            source += f" / 내 캠페인 기록 {sum(s['runs'] for s in history)}건 참고"
        return values, source

    def handle_action(action, values, workspace, form):
        try:
            campaign_id = int(form.get('campaign_id', '')) or None
        except ValueError:
            campaign_id = None
        if action == 'save_campaign':
            typed = {key: form.get('camp_' + key, '') for key in CAMPAIGN_KEYS}
            try:
                model.save_campaign(workspace, typed, campaign_id)
            except ValidationError as exc:
                g.campaign_form, g.editing_id = typed, campaign_id
                return current_values(workspace), dict(action_error=str(exc))
            return current_values(workspace), dict(action_message=f"캠페인 '{typed['name'].strip()}'을(를) {'수정' if campaign_id else '기록'}했습니다.")
        if action == 'edit_campaign':
            found = next((c for c in model.list_campaigns(workspace) if c['id'] == campaign_id), None)
            if found is None:
                return current_values(workspace), dict(action_error='수정할 캠페인을 찾지 못했습니다.')
            g.campaign_form = {key: '' if found[key] is None else found[key] for key in CAMPAIGN_KEYS}
            g.editing_id = campaign_id
            return current_values(workspace), dict(action_message=f"'{found['name']}' 캠페인을 아래 양식에서 수정하세요.")
        if action == 'delete_campaign':
            deleted = model.delete_campaign(workspace, campaign_id) if campaign_id else False
            return current_values(workspace), (dict(action_message='캠페인 기록을 삭제했습니다.') if deleted else dict(action_error='삭제할 캠페인을 찾지 못했습니다.'))
        return values, {}

    def view_context(workspace):
        today = datetime.now(KST).date().isoformat()
        return dict(campaigns_enabled=model.campaign_store is not None, campaigns=model.list_campaigns(workspace),
                    channel_summary=model.channel_summary(workspace), campaign_form=g.get('campaign_form') or {},
                    editing_id=g.get('editing_id'), today=today,
                    channel_choices=('매장 소식·SNS 직접 운영', '동네 소식·재방문 쿠폰', '지역 타깃 광고 대행', '기타'))

    return bind_module('marketing', model, 'marketing/index.html', title, description, number,
                       prepare_submission, handle_action, view_context=view_context)
