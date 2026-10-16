"""Real Chromium UI checks on both hostnames; game physics is tested separately."""
import pathlib
import struct
from playwright.sync_api import sync_playwright

HERE=pathlib.Path(__file__).parent
content=(HERE/'content.js').read_text()
raw=struct.pack('<II',1,4)+b''.join(struct.pack('<I7f',0,1,0,0,0,0,0,0) for _ in range(4))+bytes(128)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for host in ('car-soccer.com','turball.io'):
        page=browser.new_page(viewport={'width':1100,'height':768})
        page.route(f'https://{host}/**',lambda route:route.fulfill(body='<!doctype html><html><body>Test arena</body></html>',content_type='text/html'))
        page.goto(f'https://{host}/')
        page.evaluate('''() => {
          window.store={selectedModel:'g9',modelCatalog:{}};window.commands=[];
          window.chrome={runtime:{getURL:n=>n,onMessage:{addListener(){}},sendMessage:async()=>({ok:true})},
            storage:{local:{get:async keys=>Object.fromEntries(keys.map(k=>[k,window.store[k]]))},onChanged:{addListener(){}}}};
          window.state={active:false,loading:false,selectedBot:'nexto',botName:'Nexto',lastControls:{},mode:'offline',gameMode:'freeplay',phase:'idle',tas:{loaded:false}};
          window.pushStatus=()=>window.postMessage({source:'__grandchamp_trainer_v4__',from:'runtime',type:'status',state:window.state},location.origin);
          window.addEventListener('message',e=>{
            const m=e.data;if(m?.from!=='ui')return;window.commands.push(m.command);
            if(m.command==='select-bot'){window.state.selectedBot=m.botId;window.state.botName=m.botId==='tas'?'TAS':'Nexto';}
            if(m.command==='tas-load'){
              if(!(m.buffer instanceof ArrayBuffer))throw Error('Upload was not binary');
              window.state.selectedBot='tas';window.state.botName='TAS';window.state.tas={loaded:true,name:m.name,frames:new DataView(m.buffer).getUint32(4,true),seconds:4/120,frame:0,car:[0,-4608,17],ball:[0,0,93],message:'Loaded'};
            }
            if(m.command==='enable')window.state.active=true;
            if(m.command==='disable')window.state.active=false;
            window.pushStatus();
          });
        }''')
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_script_tag(content=content);page.evaluate('window.pushStatus()')
        page.keyboard.press('F7');page.get_by_role('option',name='TAS — recorded inputs').click()
        page.wait_for_selector('.gct4-tas:not([hidden])')
        page.locator('#gct4-tas-upload').set_input_files([
            {'name':'first.data','mimeType':'application/octet-stream','buffer':raw},
            {'name':'<second>.data','mimeType':'application/octet-stream','buffer':raw}])
        page.wait_for_function('window.state.tas.loaded')
        page.locator('#gct4-tas-select').select_option('1')
        page.wait_for_function('window.state.tas.name === "<second>.data"')
        assert '<second>.data' in page.locator('.gct4-tas-status').inner_text()
        page.get_by_role('button',name='Restore starting car + ball').click()
        page.wait_for_function('window.commands.includes("tas-prepare")')
        page.get_by_role('button',name='Play TAS from start').click()
        page.wait_for_function('window.state.active')
        page.get_by_role('button',name='Minimize trainer').click()
        assert not page.locator('#gct4-panel').is_visible()
        assert page.get_by_role('button',name='Open trainer').is_visible()
        assert page.evaluate('window.state.active'),'Minimize stopped playback'
        page.get_by_role('button',name='Open trainer').click()
        assert page.locator('#gct4-panel').is_visible()
        page.get_by_role('button',name='Minimize trainer').click();page.keyboard.press('F7')
        page.wait_for_selector('#gct4-model-menu:not([hidden])')
        page.keyboard.press('F7');page.wait_for_selector('#gct4-model-menu[hidden]',state='attached')
        page.get_by_role('button',name='Minimize trainer').click();page.keyboard.press('F8')
        page.wait_for_function('!window.state.active')
        assert not errors,errors
        print('PASS:',host,'TAS picker, multiple binary uploads, selection, restore/play, minimize without stopping, restore button, F7 toggle and F8 while minimized')
        page.close()
    browser.close()
