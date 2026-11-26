"""Shared request plumbing. Module controllers bind their own Model and View."""
import hmac
from secrets import token_urlsafe
from uuid import uuid4
from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from app.common.validation import ValidationError


def workspace_id():
    if 'workspace' not in session:
        session['workspace']=uuid4().hex
    return session['workspace']


def csrf_token():
    if 'csrf' not in session:
        session['csrf']=token_urlsafe(32)
    return session['csrf']


def verify_csrf():
    token=request.form.get('csrf','')
    if not token.isascii() or not hmac.compare_digest(token,csrf_token()):
        abort(400,description='요청 확인 정보가 만료되었습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.')


def bind_module(name,model,template,title,description,number,prepare_submission=None,handle_action=None,extra_context=None,
                after_save=None,view_context=None,defaults_for=None):
    """after_save(record, workspace, form) runs after a successful calculation;
    view_context(workspace) adds per-request template values (e.g. saved lists);
    defaults_for(workspace) gives starting values filled from other modules."""
    blueprint=Blueprint(name,__name__,url_prefix='/'+name.replace('_','-'),template_folder='../modules/'+name+'/views')

    @blueprint.route('/',methods=['GET','POST'])
    def index():
        workspace=workspace_id()
        record=model.latest(workspace)
        starting=defaults_for(workspace) if defaults_for else model.defaults()
        values=starting|record.inputs if record else starting  # fields added later fall back to defaults
        error=None
        status=200
        extra=dict(extra_context or {})
        if view_context: extra.update(view_context(workspace))
        example=request.args.get('example')=='1'
        if example:
            values=starting; record=None
        if request.method=='POST':
            verify_csrf()
            values={field.name: request.form.get(field.name,'') for field in model.fields}
            action=request.form.get('action','')
            if action and handle_action:
                # Non-saving actions (e.g. fill inputs from other modules) re-render the form.
                values,action_context=handle_action(action,values,workspace,request.form)
                if view_context: extra.update(view_context(workspace))
                extra.update(action_context)
                return render_template(template,fields=model.fields,values=values,record=record,error=None,
                                       module_name=name,title=title,description=description,number=number,**extra)
            try:
                source='사용자 입력 · 실측 검증 안 됨'
                if prepare_submission:
                    values,source=prepare_submission(values,source,workspace,request.form)
                record=model.analyze(values,workspace,source)
                if after_save: after_save(record,workspace,request.form)
                return redirect(url_for(name+'.index'),code=303)
            except ValidationError as exc:
                error=str(exc);record=None;status=422
        return render_template(template,fields=model.fields,values=values,record=record,error=error,
                               module_name=name,title=title,description=description,number=number,**extra),status

    return blueprint
