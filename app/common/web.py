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


def bind_module(name,model,template,title,description,number,prepare_submission=None):
    blueprint=Blueprint(name,__name__,url_prefix='/'+name.replace('_','-'),template_folder='../modules/'+name+'/views')

    @blueprint.route('/',methods=['GET','POST'])
    def index():
        workspace=workspace_id()
        record=model.latest(workspace)
        values=record.inputs.copy() if record else model.defaults()
        error=None
        status=200
        example=request.args.get('example')=='1'
        if example:
            values=model.defaults(); record=None
        if request.method=='POST':
            token=request.form.get('csrf','')
            if not token.isascii() or not hmac.compare_digest(token,csrf_token()):
                abort(400,description='요청 확인 정보가 만료되었습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.')
            values={field.name: request.form.get(field.name,'') for field in model.fields}
            values['data_mode']='user' if request.form.get('data_mode')=='user' else 'example'
            try:
                source='사용자 입력 · 실측 검증 안 됨' if values['data_mode']=='user' else '가상 예시 · 실제 시장 자료 아님'
                if prepare_submission:
                    values,source=prepare_submission(values,source,workspace,request.form)
                model.analyze(values,workspace,source)
                return redirect(url_for(name+'.index'),code=303)
            except ValidationError as exc:
                error=str(exc);record=None;status=422
        return render_template(template,fields=model.fields,values=values,record=record,error=error,
                               module_name=name,title=title,description=description,number=number),status

    return blueprint
