"""Optional browser checks against a running local server; writes QA screenshots."""
from pathlib import Path
from decimal import Decimal
import argparse
import json
from playwright.sync_api import sync_playwright


ROUTES=('property','material-cost','menu-pricing','marketing','cost-optimization')


def run(base_url='http://127.0.0.1:5000'):
    base=base_url.rstrip('/')
    out=Path('tmp/ui');out.mkdir(parents=True,exist_ok=True)
    findings=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        for width,height in ((1440,1100),(768,1024),(390,844),(320,740)):
            context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1)
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base)
            page.screenshot(path=str(out/f'home-{width}.png'),full_page=True)
            assert page.locator('h1').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'Home overflow at {width}'
            for route in ROUTES:
                page.goto(base+'/'+route+'/')
                if route=='property':
                    page.locator('label.chip:has-text("상관없음")').click()   # any rent band, so data always yields areas
                page.locator('.input-panel .primary-button').click()
                page.wait_for_url(base+'/'+route+'/')
                page.locator('.method-panel').wait_for()
                assert page.locator('table tbody tr').count()>0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'{route} overflow at {width}'
                assert page.locator('.primary-button').is_enabled()
                page.screenshot(path=str(out/f'{route}-{width}.png'),full_page=True)
            # 03 takes the dish 02 just saved; let the server validate a malformed input even if native validation is bypassed.
            page.goto(base+'/menu-pricing/')
            assert page.locator('select[name=dish]').count()==1
            page.locator('form').first.evaluate('(f) => f.noValidate = true')
            page.locator('[name=volume]').fill('0.5')
            page.locator('.input-panel .primary-button').click()
            page.locator('[role=alert]').wait_for()
            assert page.locator('[name=volume]').input_value()=='0.5'
            assert not errors,errors
            findings.append({'width':width,'routes':len(ROUTES)+1,'results':'pass','overflow':False,'javascript_errors':errors})
            context.close()
        browser.close()
    (out/'results.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(findings,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Browser verification for VENI VIDI BIZ')
    parser.add_argument('--base-url',default='http://127.0.0.1:5000')
    run(parser.parse_args().base_url)
