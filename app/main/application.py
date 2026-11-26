"""Composition root: only this layer wires modules and public interfaces together."""
import importlib
import os
from pathlib import Path
import re
from secrets import token_hex
from decimal import Decimal
from flask import Flask, abort, redirect, render_template, request, session, url_for
from app.common.db import Database
from app.common.repository import SqliteRepository
from app.common.web import csrf_token, verify_csrf, workspace_id
from app.common.time import korean_time
from app.reference.kamis import KamisPrices
from app.reference.dineout import DineOutPrices
from app.reference.kosis import KosisBenchmarks, StartupBenchmarks
from app.reference.seoul_areas import SeoulAreaData


MODULES=(
    ('property','Property','부동산 및 업장 관리','후보 입지를 비교하고 창업에 필요한 자금을 빠짐없이 살펴보세요.','공간과 초기 자금','01'),
    ('material_cost','MaterialCost','재료비 관리','구매 단위가 달라도, 한 번 사용하는 재료의 원가를 정확하게 계산하세요.','재료의 단위 원가','02'),
    ('menu_pricing','MenuPricing','메뉴 가격 관리','원가와 목표를 바탕으로 가격별 매출과 공헌이익을 비교하세요.','원가에서 판매가까지','03'),
    ('marketing','Marketing','마케팅 관리','예산과 운영 시간에 맞는 직접 홍보와 업체 이용 방안을 검토하세요.','우리 매장에 맞는 홍보','04'),
    ('cost_optimization','CostOptimization','비용 절감 및 운영 개선','월 비용 구조를 파악하고 절감 시나리오와 손익분기점을 확인하세요.','비용 구조와 다음 선택','05'),
)


ROOT=Path(__file__).resolve().parents[2]
WORKSPACE_CODE=re.compile(r'^[0-9a-f]{32}$')


def persistent_secret(folder):
    """Reuse one secret per data folder so sessions (and their workspaces) survive restarts."""
    path=Path(folder)/'secret_key'
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(token_hex(32),encoding='ascii')
    return path.read_text(encoding='ascii').strip()


def create_app(config=None,enabled_modules=None):
    app=Flask(__name__,template_folder='../common/templates',static_folder='../common/static',static_url_path='/static')
    app.config.update(MAX_CONTENT_LENGTH=64*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',RETENTION_DAYS=365)
    if config: app.config.update(config)
    # Tests and explicit DATABASE=None keep the in-memory store; normal runs use a SQLite file.
    default_db=None if app.config.get('TESTING') else os.environ.get('VENI_DATABASE') or ROOT/'instance'/'veni.db'
    database_path=app.config.get('DATABASE',default_db)
    database=Database(database_path) if database_path else None
    if database:
        database.migrate()
        database.purge_inactive(app.config['RETENTION_DAYS'])
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY']=os.environ.get('VENI_SECRET_KEY') or (persistent_secret(database.path.parent) if database else token_hex(32))
    enabled=set(enabled_modules) if enabled_modules is not None else {m[0] for m in MODULES}
    unknown=enabled-{m[0] for m in MODULES}
    if unknown: raise ValueError(f'Unknown modules: {unknown}')
    # Saved lists (materials, menus) always need SQL; without a DB file they use a private in-memory database.
    catalog_db=database or Database.in_memory()
    if not database: catalog_db.migrate()
    models={}
    # Build providers first; consumers use only the public snapshot contract.
    for name,cls,*_ in MODULES:
        if name not in enabled: continue
        repository_class=getattr(importlib.import_module(f'app.modules.{name}.repositories.memory'),cls+'Repository')
        repository=SqliteRepository(database,name) if database else repository_class()
        model_class=getattr(importlib.import_module(f'app.modules.{name}.models.service'),cls+'Model')
        options={}
        if name=='property':
            # Reference data lives in the same database; tests can pass AREA_DATA (any AreaDataProvider).
            options={'candidates':importlib.import_module('app.modules.property.repositories.candidates').CandidateStore(catalog_db),
                     'areas':app.config.get('AREA_DATA') or SeoulAreaData(catalog_db),
                     'startup':app.config.get('STARTUP_BENCHMARKS') or StartupBenchmarks(catalog_db)}
        if name=='marketing':
            options={'campaigns':importlib.import_module('app.modules.marketing.repositories.campaigns').CampaignStore(catalog_db)}
        if name=='material_cost':
            options={'catalog':importlib.import_module('app.modules.material_cost.repositories.catalog').MaterialCatalog(catalog_db),
                     'prices':app.config.get('MARKET_PRICES') or KamisPrices(catalog_db)}
        if name=='menu_pricing':
            recipes=importlib.import_module('app.modules.menu_pricing.repositories.recipes').RecipeStore(catalog_db)
            sales=importlib.import_module('app.modules.menu_pricing.repositories.sales').SalesStore(catalog_db)
            options={'material_provider':models.get('material_cost'),'material_catalog':models.get('material_cost'),'recipes':recipes,'sales':sales,
                     'dineout':app.config.get('DINEOUT') or DineOutPrices(catalog_db)}
        if name=='cost_optimization':
            # Only enabled providers; each is labelled "<number> <title>" for display.
            labels={m[0]:f'{m[5]} {m[2]}' for m in MODULES}
            options={'cost_providers':tuple((labels[source],models[source]) for source in ('property','menu_pricing','marketing') if source in models),
                     'financials':importlib.import_module('app.modules.cost_optimization.repositories.financials').FinancialStore(catalog_db),
                     'benchmarks':app.config.get('BENCHMARKS') or KosisBenchmarks(catalog_db)}
        models[name]=model_class(repository,**options)
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
        return dict(navigation=navigation,csrf_token=csrf_token,persistent=database is not None)

    app.add_template_filter(korean_time,'korean_time')

    @app.get('/')
    def home():
        return render_template('home.html',module_name='home')

    def workspace_has_data(code):
        if database: return database.workspace_exists(code)
        return any(model.latest(code) is not None for model in models.values())

    @app.route('/workspace/',methods=['GET','POST'])
    def workspace():
        """Show this browser's workspace code, open another workspace by code, or delete all data."""
        current=workspace_id()
        message=error=None
        status=200
        if request.method=='POST':
            verify_csrf()
            action=request.form.get('action')
            if action=='open':
                code=request.form.get('code','').strip().lower().replace('-','').replace(' ','')
                if not WORKSPACE_CODE.match(code):
                    error,status='작업 공간 코드는 32자리 영문(a~f)·숫자입니다. 하이픈은 있어도 됩니다.',422
                elif code==current:
                    message='이미 이 작업 공간을 사용하고 있습니다.'
                elif not workspace_has_data(code):
                    error,status='해당 코드로 저장된 데이터가 없습니다. 코드를 다시 확인하세요.',404
                else:
                    session['workspace']=code
                    return redirect(url_for('workspace',opened=1),code=303)
            elif action=='delete' and request.form.get('confirm')=='yes':
                for model in models.values():
                    model.forget(current)
                session.pop('workspace',None)
                return redirect(url_for('workspace',deleted=1),code=303)
            elif action=='delete':
                error,status='삭제하려면 확인란을 선택하세요.',422
            else:
                abort(400)
        if request.args.get('opened'): message='작업 공간을 열었습니다. 각 모듈에서 저장된 결과를 확인하세요.'
        if request.args.get('deleted'): message='이전 작업 공간의 데이터를 모두 삭제했습니다. 새 작업 공간을 사용합니다.'
        code=workspace_id()
        return render_template('workspace.html',module_name='workspace',title='작업 공간',code=code,
                               display_code='-'.join(code[i:i+4] for i in range(0,32,4)),
                               has_data=workspace_has_data(code),message=message,error=error,
                               retention_days=app.config['RETENTION_DAYS']),status

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
