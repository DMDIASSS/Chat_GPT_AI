"""Chromium popup download checks with mocked extension messaging, no live game."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).parent
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(accept_downloads=True)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def serve(route):
        name=route.request.url.split('/')[-1] or 'popup.html'
        file=ROOT/name
        route.fulfill(body=file.read_bytes(),content_type='text/html' if name.endswith('.html') else 'text/javascript')
    page.route('https://extension.test/**',serve)
    page.add_init_script('''
    window.captured=false;window.source='export{changed as startGame};';
    window.chrome={tabs:{query:async()=>[{id:7,url:'https://turball.io/'}]},
      runtime:{getURL:n=>n,sendMessage:async m=>{
        if(m.type==='gct-status')return {ok:true,status:{site:'turball',state:captured?'unsupported':'waiting-gameplay',
          message:'Gameplay module needed',expectedGameplay:'/assets/app/chunk-KALAXRXF.js',canSaveGameplay:captured,
          gameplay:captured?{filename:'chunk-KALAXRXF.js',bytes:source.length}:null}};
        if(m.type==='gct-gameplay-source')return {ok:true,filename:'chunk-KALAXRXF.js',source};
        if(m.type==='gct-diagnostics')return {ok:true,report:{extensionVersion:'4.5.2',scope:'Public asset diagnostics'}};
        return {ok:true};}},
      storage:{onChanged:{addListener(){}},local:{get:async()=>({})}}};
    ''')
    page.goto('https://extension.test/popup.html')
    page.wait_for_function("document.getElementById('capture-status').textContent.includes('KALAXRXF')")
    assert page.locator('#save-gameplay').is_disabled()
    page.evaluate('window.captured=true')
    page.wait_for_function("!document.getElementById('save-gameplay').disabled")
    with page.expect_download() as pending:page.locator('#save-gameplay').click()
    download=pending.value
    assert download.suggested_filename=='chunk-KALAXRXF.js'
    assert Path(download.path()).read_text()=='export{changed as startGame};'
    with page.expect_download() as pending:page.locator('#save-diagnostics').click()
    assert json.loads(Path(pending.value.path()).read_text())['extensionVersion']=='4.5.2'
    assert not errors,errors
    print('PASS Chromium popup waiting/captured states, gameplay JS and diagnostics downloads; no page errors')
    browser.close()
