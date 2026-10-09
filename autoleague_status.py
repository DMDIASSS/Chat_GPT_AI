"""Display saved champion, backups and decisions without loading Torch or running RocketSim."""
import json
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'/'autoleague'


def main():
    print('=== Chat GPT AI: AutoLeague status ===')
    progress=DATA/'league_state.json'
    if not progress.is_file():
        print('Not started: No league_state.json. Use AUTO_0_PREFLIGHT.bat then AUTO_1_START.bat.')
        return
    info=json.loads(progress.read_text(encoding='utf8'))
    print('Champion origin:',info.get('champion_origin'))
    print('Current champion:',DATA/'champion.pt')
    print('Champion SHA256:',info.get('champion_sha'))
    print('Current cycle:',info.get('cycle'),'| promotions:',info.get('promotions'))
    print('Last decision:',info.get('last_decision','not yet'))
    print('Protection status:',info.get('phase','unknown'))
    print('PPO candidate:',DATA/'candidate.pt' if (DATA/'candidate.pt').is_file() else 'none')
    print('Blacklist count:',len(json.loads((DATA/'blacklist.json').read_text())) if (DATA/'blacklist.json').exists() else 0)
    backups=sorted((DATA/'backups').glob('*.pt')) if (DATA/'backups').exists() else []
    print('Saved timestamped backups:',len(backups))
    for path in backups[-5:]:
        print(' ',path.name)
    history=DATA/'history.jsonl'
    if history.is_file():
        print('\nLast decisions:')
        for line in history.read_text(encoding='utf8').splitlines()[-5:]:
            try:
                data=json.loads(line)
                print(' cycle',data['cycle'],data['verdict'],data.get('reason'))
            except (json.JSONDecodeError,KeyError):pass
    replay=DATA/'replay_analysis_summary.json'
    if replay.exists():
        info=json.loads(replay.read_text(encoding='utf8'))
        print('\nDownloaded replay analysis:',info)

if __name__=='__main__':main()
