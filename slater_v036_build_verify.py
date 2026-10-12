"""Verify the four packaged Nexto bot modes without running Rocket League."""
import ast
import argparse
import hashlib
from pathlib import Path

NEXTO_SHA = 'bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa'
MODES = {
    'Nexto_NN_Greedy': (False, False),
    'Nexto_NN_Stochastic': (False, True),
    'Nexto_Script_Only': (True, False),
    'Nexto_Stock': (True, True),
}


def verify(root):
    results={}
    for name, (hardcoded, stochastic) in MODES.items():
        folder=Path(root)/name
        for file in ('bot.py','bot.cfg','agent.py','nexto_obs.py','nexto-model.pt','slater_v036_telemetry.py'):
            if not (folder/file).is_file():raise FileNotFoundError(folder/file)
        source=(folder/'bot.py').read_text(encoding='utf8')
        ast.parse(source)
        import re
        match=re.search(r'hardcoded_kickoffs=(True|False),\s*stochastic_kickoffs=(True|False)',source)
        if not match or (match.group(1)=='True',match.group(2)=='True')!=(hardcoded,stochastic):
            raise ValueError(f'Wrong kickoff modes in {name}')
        if source.count('_v036_note(self, packet, mode=')!=1:
            raise ValueError(f'Expected one telemetry hook in {name}')
        sha=hashlib.sha256((folder/'nexto-model.pt').read_bytes()).hexdigest()
        if sha != NEXTO_SHA:
            raise ValueError(f'Unexpected model hash {sha} in {name}')
        results[name]={'hardcoded_kickoffs':hardcoded,'stochastic_kickoffs':stochastic,'nexto_sha256':sha}
    return results


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',default='data/rlbot_exports/slater_v036_nexto_modes')
    a=p.parse_args()
    results=verify(a.root)
    for mode,r in results.items():print('V036_VERIFY_PASS',mode,r['hardcoded_kickoffs'],r['stochastic_kickoffs'],r['nexto_sha256'][:16])


if __name__=='__main__':main()
