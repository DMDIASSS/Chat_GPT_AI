"""Package a complete native checkpoint for RLBot v4 without modifying its weights."""
import json,shutil,tempfile
from pathlib import Path
import numpy as np
from export_rlbot_v4 import ROOT,OUTPUT,TEMPLATE,validate_name
from slater_native_actor import NativeActor,checkpoint_identity
from nexto_teacher import nexto_actions

def export_native(checkpoint,name,output=None,*,scripted_kickoff=False):
    source=Path(checkpoint).resolve()
    if source.is_file() and source.suffix.lower()=='.lt':source=source.parent
    actor=NativeActor(source);identity=checkpoint_identity(source)
    name=validate_name(name);out=Path(output or OUTPUT).resolve();out.mkdir(parents=True,exist_ok=True);target=out/name
    if target.exists():raise FileExistsError('Export already exists: '+str(target))
    tmp=Path(tempfile.mkdtemp(prefix='.native_export_',dir=out))
    try:
        (tmp/'checkpoint').mkdir()
        for f in identity['files']:shutil.copy2(source/f,tmp/'checkpoint'/f)
        text=(ROOT/'slater_native_actor.py').read_text(encoding='utf8')
        text=text.replace('from nexto_teacher import nexto_actions','def nexto_actions():return np.load(Path(__file__).resolve().parent/"actions.npy")')
        text=text.replace('from slater_v041_core import sha256','def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()')
        (tmp/'native_actor.py').write_text(text,encoding='utf8')
        bot=(ROOT/'native_rlbot_v4.py').read_text(encoding='utf8').replace('SCRIPTED_KICKOFF=True','SCRIPTED_KICKOFF='+str(bool(scripted_kickoff)))
        (tmp/'bot.py').write_text(bot,encoding='utf8')
        shutil.copy2(ROOT/'slater_nexto_scheduler_v038b.py',tmp)
        from rlgym.rocket_league.common_values import BOOST_LOCATIONS
        np.save(tmp/'boost_locations.npy',np.asarray(BOOST_LOCATIONS));np.save(tmp/'actions.npy',nexto_actions())
        for f in ('appearance.cfg','nexto_logo.png','NEXT0_UPSTREAM_LICENSE.txt'):shutil.copy2(TEMPLATE/f,tmp/f)
        (tmp/'requirements.txt').write_text('rlbot==1.*\nnumpy\ntorch\n',encoding='utf8')
        (tmp/'bot.cfg').write_text(f'[Locations]\nlooks_config = ./appearance.cfg\npython_file = ./bot.py\nrequirements_file = ./requirements.txt\nlogo_file = ./nexto_logo.png\nname = {name}\nmaximum_tick_rate_preference = 120\n\n[Details]\ndeveloper = Chat GPT AI project\ndescription = Experimental GigaLearn native policy\nlanguage = python\ntags = 1v1\n',encoding='utf8')
        report={'format':'RLBot v4 native 230/90','source':identity,'hardcoded_kickoffs':bool(scripted_kickoff),
                'packet_limitations':'Jump timers inferred; wheel contact cannot distinguish ground/wall; world-contact normal unavailable. Live behavior parity unverified.'}
        (tmp/'EXPORT_INFO.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        (tmp/'README_IMPORT.txt').write_text('Load bot.cfg in RLBot v4. Standard Soccar only, 1v1/2v2/3v3. Run at 120 FPS.\n'+report['packet_limitations']+'\n',encoding='utf8')
        if checkpoint_identity(source)!=identity:raise RuntimeError('Source changed during export')
        if checkpoint_identity(tmp/'checkpoint')['files']!=identity['files']:raise RuntimeError('Export weight mismatch')
        tmp.rename(target);print('SUCCESS: exported native bot at',target,flush=True);return target
    except BaseException:shutil.rmtree(tmp,ignore_errors=True);raise

def refresh_native_exports():
    """Update only native bot wrappers; preserve weights and kickoff choices."""
    updated=0
    for info in OUTPUT.glob('*/EXPORT_INFO.json'):
        doc=json.loads(info.read_text(encoding='utf8'))
        if doc.get('format')!='RLBot v4 native 230/90':continue
        folder=info.parent;checkpoint_identity(folder/'checkpoint')
        bot=folder/'bot.py';backup=folder/'bot.py.before_native_control_fix'
        if bot.exists() and not backup.exists():shutil.copy2(bot,backup)
        source=(ROOT/'native_rlbot_v4.py').read_text(encoding='utf8').replace('SCRIPTED_KICKOFF=True','SCRIPTED_KICKOFF='+str(bool(doc['hardcoded_kickoffs'])))
        temp=folder/'bot.py.updating';temp.write_text(source,encoding='utf8');temp.replace(bot)
        print('Updated native wrapper:',folder,'scripted kickoff:',doc['hardcoded_kickoffs'],flush=True);updated+=1
    print('Updated',updated,'native exports. Restart these bots in RLBot.',flush=True)

if __name__=='__main__':refresh_native_exports()
