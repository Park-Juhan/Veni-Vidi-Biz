"""Composition root: only this layer wires modules and public interfaces together."""
import importlib
import os
from secrets import token_hex
from decimal import Decimal
from flask import Flask, render_template
from app.common.web import csrf_token
from app.common.time import korean_time


MODULES=(
    ('property','Property','부동산 및 업장 관리','후보 입지를 비교하고 창업에 필요한 자금을 빠짐없이 살펴보세요.','공간과 초기 자금','01'),
    ('material_cost','MaterialCost','재료비 관리','구매 단위가 달라도, 한 번 사용하는 재료의 원가를 정확하게 계산하세요.','재료의 단위 원가','02'),
    ('menu_pricing','MenuPricing','메뉴 가격 관리','원가와 목표를 바탕으로 가격별 매출과 공헌이익을 비교하세요.','원가에서 판매가까지','03'),
    ('marketing','Marketing','마케팅 관리','예산과 운영 시간에 맞는 직접 홍보와 업체 이용 방안을 검토하세요.','우리 매장에 맞는 홍보','04'),
    ('cost_optimization','CostOptimization','비용 절감 및 운영 개선','월 비용 구조를 파악하고 절감 시나리오와 손익분기점을 확인하세요.','비용 구조와 다음 선택','05'),
)


def create_app(config=None,enabled_modules=None):
    app=Flask(__name__,template_folder='../common/templates',static_folder='../common/static',static_url_path='/static')
    app.config.update(SECRET_KEY=os.environ.get('VENI_SECRET_KEY') or token_hex(32),MAX_CONTENT_LENGTH=64*1024,
                      SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict')
    if config: app.config.update(config)
    enabled=set(enabled_modules) if enabled_modules is not None else {m[0] for m in MODULES}
    unknown=enabled-{m[0] for m in MODULES}
    if unknown: raise ValueError(f'Unknown modules: {unknown}')
    models={}
    # Build providers first; consumers use only the public snapshot contract.
    for name,cls,*_ in MODULES:
        if name not in enabled: continue
        repository_class=getattr(importlib.import_module(f'app.modules.{name}.repositories.memory'),cls+'Repository')
        model_class=getattr(importlib.import_module(f'app.modules.{name}.models.service'),cls+'Model')
        options={'material_provider':models.get('material_cost')} if name=='menu_pricing' else {}
        models[name]=model_class(repository_class(),**options)
    navigation=[]
    for name,_,title,description,short,number in MODULES:
        if name not in enabled: continue
        controller=importlib.import_module(f'app.modules.{name}.controllers.routes')
        app.register_blueprint(controller.create_blueprint(models[name],title,description,number))
        navigation.append(dict(name=name,title=title,description=description,short=short,number=number))

    @app.template_filter('display')
    def display(value):
        if isinstance(value,(int,float,Decimal)):
            return f'{value:,.0f}' if value==int(value) else f'{value:,.2f}'
        return value

    @app.context_processor
    def context():
        return dict(navigation=navigation,csrf_token=csrf_token)

    app.add_template_filter(korean_time,'korean_time')

    @app.get('/')
    def home():
        return render_template('home.html',module_name='home')

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(500)
    def error_page(error):
        messages={404:'요청한 화면을 찾을 수 없습니다.',413:'입력 데이터가 너무 큽니다.',500:'처리 중 문제가 발생했습니다. 입력을 확인하고 다시 시도해 주세요.'}
        message=messages.get(error.code,getattr(error,'description','잘못된 요청입니다.'))
        return render_template('error.html',code=error.code,message=message),error.code

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        response.headers['Cache-Control']='no-store'
        return response

    return app
