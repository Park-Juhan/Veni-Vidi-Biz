"""Optional browser checks against a running local server; writes QA screenshots."""
from pathlib import Path
from decimal import Decimal
import argparse
import json
from playwright.sync_api import sync_playwright


ROUTES=('property','material-cost','menu-pricing','marketing','cost-optimization')


def run(base_url='http://127.0.0.1:5000',channel=True):
    base=base_url.rstrip('/')
    out=Path('tmp/ui');out.mkdir(parents=True,exist_ok=True)
    findings=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(**({'channel':'chrome'} if channel else {}),headless=True)
        for width,height in ((1440,1100),(768,1024),(390,844),(320,740)):
            context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1)
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base)
            page.screenshot(path=str(out/f'home-{width}.png'),full_page=True)
            assert page.locator('h1').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'Home overflow at {width}'
            page.goto(base+'/menu-pricing/')
            page.locator('[name=use_material]').check()
            page.get_by_role('button',name='계산하고 대안 비교하기').click()
            page.locator('[role=alert]').wait_for()
            assert page.locator('[name=use_material]').is_checked()
            # Property input is a step-by-step wizard: only one step and no submit button at first.
            page.goto(base+'/property/')
            steps=page.locator('.wizard-step')
            assert steps.count()==5 and page.locator('.wizard-step:visible').count()==1
            assert not page.get_by_role('button',name='계산하고 대안 비교하기').is_visible()
            page.locator('[name=budget]').fill('')
            page.get_by_role('button',name='다음 단계 →').click()
            assert page.locator('.wizard-progress li.active').inner_text().startswith('1')
            page.locator('[name=budget]').fill('1500000')
            for _ in range(4): page.get_by_role('button',name='다음 단계 →').click()
            assert page.locator('[name=w_fit]').is_visible()
            page.get_by_role('button',name='← 이전').click()
            assert page.locator('[name=b_rent]').is_visible()
            for route in ROUTES:
                page.goto(base+'/'+route+'/')
                if route=='property':
                    for _ in range(4): page.get_by_role('button',name='다음 단계 →').click()
                page.get_by_role('button',name='계산하고 대안 비교하기').click()
                page.wait_for_url(base+'/'+route+'/')
                page.locator('.method-panel').wait_for()
                assert page.locator('table tbody tr').count()>0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'{route} overflow at {width}'
                assert page.locator('.primary-button').is_enabled()
                page.screenshot(path=str(out/f'{route}-{width}.png'),full_page=True)
            # Optional import is a user action; absence never prevents direct entry.
            page.goto(base+'/menu-pricing/')
            page.locator('[name=use_material]').check()
            page.get_by_role('button',name='계산하고 대안 비교하기').click()
            page.locator('.method-panel').wait_for()
            assert Decimal(page.locator('[name=material]').input_value())==Decimal(360)
            # Let the server validate a malformed input even if native validation is bypassed.
            page.locator('form').evaluate('(f) => f.noValidate = true')
            page.locator('[name=margin]').fill('100')
            page.get_by_role('button',name='계산하고 대안 비교하기').click()
            page.locator('[role=alert]').wait_for()
            assert page.locator('[name=margin]').input_value()=='100'
            assert page.locator('[name=use_material]').is_checked()
            assert not errors,errors
            findings.append({'width':width,'routes':len(ROUTES)+1,'results':'pass','overflow':False,'javascript_errors':errors})
            context.close()
        browser.close()
    (out/'results.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(findings,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Browser verification for VENI VIDI BIZ')
    parser.add_argument('--base-url',default='http://127.0.0.1:5000')
    parser.add_argument('--bundled-chromium',action='store_true',help='Use Playwright Chromium instead of installed Chrome')
    args=parser.parse_args()
    run(args.base_url,channel=not args.bundled_chromium)
