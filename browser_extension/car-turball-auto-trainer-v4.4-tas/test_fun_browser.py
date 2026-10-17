"""Real Chromium panel tests; native physics has its own integration test."""
from pathlib import Path
from playwright.sync_api import sync_playwright

content=Path(__file__).with_name('content.js').read_text()
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for host in ('car-soccer.com','turball.io'):
        page=browser.new_page(viewport={'width':1100,'height':850})
        page.route(f'https://{host}/**',lambda route:route.fulfill(body='<!doctype html><html><body>Test arena</body></html>',content_type='text/html'))
        page.goto(f'https://{host}/')
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.evaluate('''() => {
          window.chrome={runtime:{getURL:n=>n,onMessage:{addListener(){}},sendMessage:async()=>({ok:true})},
            storage:{local:{get:async()=>({selectedModel:'g9',modelCatalog:{}})},onChanged:{addListener(){}}}};
          window.commands=[];window.state={active:false,loading:false,selectedBot:'nexto',botName:'Nexto',lastControls:{},mode:'offline',gameMode:'freeplay',phase:'idle',
            fun:{available:true,enabled:false,scope:'local play',speedLimit:6000,currentSpeed:1200,glue:false,boost:false,jumps:false,speed:false,message:'Ready'}};
          window.pushStatus=()=>window.postMessage({source:'__grandchamp_trainer_v4__',from:'runtime',type:'status',state:window.state},location.origin);
          window.addEventListener('message',e=>{
            const m=e.data;if(m?.from!=='ui')return;window.commands.push(m);
            if(m.command==='fun-toggle')window.state.fun[m.effect]=!window.state.fun[m.effect];
            if(['fun-stop','disable'].includes(m.command))for(const k of ['glue','boost','jumps','speed'])window.state.fun[k]=false;
            if(m.command==='fun-speed')window.state.fun.speedLimit=m.speed;
            if(m.command==='fun-friends')window.state.fun.allowFriends=m.allowed;
            if(m.command==='fun-connect')window.state.fun.connected=true;
            window.state.fun.enabled=['glue','boost','jumps','speed'].some(k=>window.state.fun[k]);
            window.pushStatus();
          });
        }''')
        page.add_script_tag(content=content);page.evaluate('window.pushStatus()')
        if host=='turball.io':
            assert not page.locator('#gct4-fun').is_visible(),'Fun controls leaked onto Turball'
        else:
            page.locator('#gct4-fun summary').click()
            page.locator('[data-fun-effect=glue]').click()
            page.wait_for_function('window.state.fun.glue')
            assert page.locator('[data-fun-effect=glue]').get_attribute('aria-pressed')=='true'
            page.locator('[data-fun-action=goal]').click()
            page.wait_for_function('window.commands.some(m=>m.command==="fun-action"&&m.action==="goal")')
            page.locator('#gct4-fun-speed').fill('8000');page.locator('#gct4-fun-speed').press('Tab')
            page.wait_for_function('window.state.fun.speedLimit===8000')
            page.get_by_role('button',name='Minimize trainer').click()
            assert not page.locator('#gct4-panel').is_visible()
            assert 'FUN' in page.locator('#gct4-restore').inner_text()
            page.keyboard.press('F8');page.wait_for_function('!window.state.fun.enabled')
            page.get_by_role('button',name='Open trainer').click()
            page.evaluate('window.state.fun.available=false;window.state.fun.reason="Host the room first";window.pushStatus()')
            page.wait_for_function('document.querySelector("[data-fun-effect=boost]").disabled')
            assert 'Host the room first' in page.locator('.gct4-fun-status').inner_text()
            page.evaluate('Object.assign(window.state.fun,{available:true,reason:"",hosting:true,joined:false,allowFriends:false});window.pushStatus()')
            page.locator('#gct4-fun-friends').click()
            page.wait_for_function('window.state.fun.allowFriends')
            assert page.locator('#gct4-fun-friends').get_attribute('aria-pressed')=='true'
            assert not page.locator('#gct4-fun-connect').is_visible()
            page.evaluate('Object.assign(window.state.fun,{hosting:false,joined:true,connected:false});window.pushStatus()')
            page.locator('#gct4-fun-connect').click()
            page.wait_for_function('window.state.fun.connected')
            assert not page.locator('#gct4-fun-friends').is_visible()
        assert not errors,errors
        print('PASS:',host,'fun panel scope, toggles/actions, speed setting, minimized F8, restore and unavailable-state controls')
        page.close()
    browser.close()
