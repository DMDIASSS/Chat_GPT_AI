"""Create a NEW instrumented copy of an existing RLBot v4 bot. Source untouched.

The copy captures occasional NextoObsBuilder input vectors during real RLBot
matches. Never point to the only copy of a bot as a destination.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
import shutil

PREV_ANCHOR = 'obs = self.obs_builder.build_obs(player, self.game_state, self.action)'
ACT_ANCHOR = 'self.action, weights = self.agent.act(obs, beta)'


def instrument_source(code: str) -> str:
    if code.count(PREV_ANCHOR) != 1 or code.count(ACT_ANCHOR) != 1:
        raise ValueError('bot.py is not the expected Nexto-compatible RLBot v4 source; no files were patched')
    if 'slater_rlbot_capture_v034' in code:
        raise ValueError('bot.py is already instrumented')
    code = 'from slater_rlbot_capture_v034 import capture_decision as _slater_v034_capture\n' + code
    code = re.sub(r'^([ \t]*)' + re.escape(PREV_ANCHOR) + r'$',
                  lambda m: m.group(1) + '_slater_v034_previous_action = np.asarray(self.action, dtype=np.float32).copy()\n' + m.group(1) + PREV_ANCHOR,
                  code, flags=re.MULTILINE)
    code = re.sub(r'^([ \t]*)' + re.escape(ACT_ANCHOR) + r'$',
                  lambda m: m.group(1) + ACT_ANCHOR + '\n' + m.group(1) + '_slater_v034_capture(self, obs, _slater_v034_previous_action, self.action, packet, beta)',
                  code, flags=re.MULTILINE)
    compile(code, '<instrumented bot.py>', 'exec')
    return code


def clone_bot(src: Path, dst: Path, root: Path, module: Path):
    src, dst, root = src.resolve(), dst.resolve(), root.resolve()
    allowed = (root / 'data' / 'isolated').resolve()
    if not dst.is_relative_to(allowed) or not dst.name.startswith('slater_v034_'):
        raise ValueError('Instrumented bot destination must be data/isolated/slater_v034_*')
    if dst.exists() or dst.with_name(dst.name + '.partial').exists():
        raise FileExistsError(f'Refusing to overwrite existing bot: {dst}')
    if src == dst or dst.is_relative_to(src) or src.is_relative_to(dst):
        raise ValueError('Source and destination may not be nested')
    for name in ('bot.py', 'agent.py', 'nexto_obs.py', 'nexto-model.pt', 'bot.cfg'):
        if not (src / name).is_file():
            raise FileNotFoundError(f'Missing from source: {name}')
    modified = instrument_source((src / 'bot.py').read_text(encoding='utf-8-sig'))
    intermediate = dst.with_name(dst.name + '.partial')
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(src, intermediate, ignore=shutil.ignore_patterns('__pycache__', 'capture_v034'))
        (intermediate / 'bot.py').write_text(modified, encoding='utf-8')
        cfg_path = intermediate / 'bot.cfg'
        cfg_text = cfg_path.read_text(encoding='utf-8-sig')
        cfg_text = re.sub(r'(?m)^([ \t]*name[ \t]*=[ \t]*)([^\r\n]+)$',
                          lambda m: m.group(1) + m.group(2).strip() + ' [v034 capture]',
                          cfg_text, count=1)
        cfg_path.write_text(cfg_text, encoding='utf-8')
        shutil.copyfile(module, intermediate / 'slater_rlbot_capture_v034.py')
        # the capture helper imports canonical_obs from this safe module;
        # a self-contained copy is needed when RLBot launches outside the project.
        helper = (root / 'slater_parity_v034.py')
        if not helper.is_file():
            raise FileNotFoundError('slater_parity_v034.py is not in the project root')
        shutil.copyfile(helper, intermediate / 'slater_parity_v034.py')
        intermediate.rename(dst)
    except BaseException:
        shutil.rmtree(intermediate, ignore_errors=True)
        raise
    return dst


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-bot', required=True)
    p.add_argument('--out-bot', required=True)
    a = p.parse_args(argv)
    root = Path.cwd().resolve()
    out = clone_bot(Path(a.source_bot), root / a.out_bot, root,
                    Path(__file__).resolve().parent / 'slater_rlbot_capture_v034.py')
    print('INSTRUMENTED_RLBOT_COPY', out)
    print('LIVE_CAPTURE_DIR_AFTER_PLAYING', out / 'capture_v034')
    print('SOURCE_BOT_UNCHANGED; use NEW bot.cfg in RLBot v4 GUI for test matches')
    print('NORMAL_BOT_ACTIONS_UNCHANGED; snapshots only every 20 decisions by default')


if __name__ == '__main__':
    main()
