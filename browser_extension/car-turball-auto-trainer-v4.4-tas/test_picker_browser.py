import pathlib
from playwright.sync_api import sync_playwright
js=pathlib.Path(__file__).with_name('content.js').read_text()
state={ 'active':False, 'loading':False, 'selectedBot':'nexto','botName':'G9 u0073','aiReady':False,'lastControls':{},'mode':'offline','gameMode':'freeplay','phase':'idle'}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page()
    page.goto('about:blank')
    page.evaluate('''() => {
      const originalPostMessage = window.postMessage.bind(window);
      window.postMessage = (m, target) => originalPostMessage(m, target === 'null' ? '*' : target);
      window.testStore = { selectedModel:'g9', modelCatalog:{'custom-test':{id:'custom-test',name:'Custom Pilot'} } };
      window.testCalls = [];
      chrome.runtime = { getURL:(name)=>'http://127.0.0.1:9876/'+name,
        onMessage:{addListener:()=>{}},
        sendMessage:async (msg)=>{ window.testCalls.push(msg); if (msg.type==='gct-select-model') { window.testStore.selectedModel=msg.modelId;return {ok:true};} return {ok:true}; } };
      chrome.storage = { local:{get:async keys=>Object.fromEntries(keys.filter(k=>k in window.testStore).map(k=>[k,window.testStore[k]]))},onChanged:{addListener:()=>{}} };
    }''')
    page.add_script_tag(content=js)
    page.evaluate('''s=>window.postMessage({source:'__grandchamp_trainer_v4__',from:'runtime',type:'status',state:s},location.origin)''',state)
    page.wait_for_selector('#gct4-panel')
    page.keyboard.press('F7')
    assert page.locator('#gct4-model-menu').is_visible(),'F7 menu did not open'
    assert page.get_by_role('option',name='Custom Pilot').count()==1
    page.get_by_role('option',name='Custom Pilot').click()
    page.wait_for_function('window.testStore.selectedModel === "custom-test"')
    assert 'Custom Pilot' in page.locator('.gct4-select').inner_text()
    assert not page.locator('#gct4-model-menu').is_visible()
    page.locator('.gct4-select').click()
    assert page.locator('#gct4-model-menu').is_visible(),'model menu failed on click'
    page.get_by_role('option',name='Original Nexto').click()
    page.wait_for_function('window.testStore.selectedModel === "nexto"')
    assert 'Original Nexto' in page.locator('.gct4-select').inner_text()
    print('PASS: F7 picker, imported-model switch, click picker, Original Nexto switch, menu dismissal.')
    browser.close()
