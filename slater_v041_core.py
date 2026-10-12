"""Pure, testable safeguards and selection mathematics for Slater v0.4.1.

Scoring uses paired first-goal outcomes on identical seeds/sides/opponents.
A timeout is a CENSORED 0, not a win or a draw. Model promotion remains
PROVISIONAL until full-length RLBot matches are independently verified.
"""
from __future__ import annotations
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import uuid

V60_SHA = '5f9bf7cb6a0bcfb3bcf801ade021b11499181d80fb36b0cfad827e2648936c74'
CYCLE9_SHA = '50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
NEXTO_SHA = 'bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa'
RIVAL_NAMES = ('nexto', 'cycle9', 'wavedash', 'original_champion', 'v70', 'v60')

def utc():
    return datetime.now(timezone.utc).isoformat()

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.writing.' + uuid.uuid4().hex)
    with tmp.open('x', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default

def verify_protected(paths):
    actual = {}
    for name, (path, expected_sha) in paths.items():
        p=Path(path)
        if not p.is_file():
            raise FileNotFoundError(f'Protected {name} not found: {p}')
        digest=sha256(p)
        if expected_sha and digest != expected_sha:
            raise RuntimeError(f'Protected {name} SHA mismatch at {p}: {digest}')
        actual[name]=digest
    return actual

def find_model(root, name, explicit=None):
    """Prefer actual RLBot export's nexto-model.pt; never guess another bot.

    A path explicitly set in config is authoritative. Otherwise find exact
    case/underscore/dash-insensitive export folder aliases. Only Cycle9, V70,
    V60 and stock Nexto have precisely known fallback training paths.
    """
    root=Path(root).resolve()
    if explicit:
        path=Path(explicit)
        if not path.is_absolute(): path=root/path
        if not path.is_file():raise FileNotFoundError(f'{name} model path missing: {path}')
        if path.suffix.lower() != '.pt':raise ValueError('Expected a .pt model')
        return path.resolve()
    key=lambda s: ''.join(ch for ch in s.lower() if ch.isalnum())
    aliases={
        'nexto':{'nexto','stocknexto','originalnexto'},
        'cycle9':{'cycle9','cycle09','cycle9champion'},
        'wavedash':{'wavedash','wave'},
        'original_champion':{'originalchampion','ogchampion','champion','original'},
        'v70':{'v70','u70','version70'},
        'v60':{'v60','u60','version60'},
    }
    exports=root/'data'/'rlbot_exports'
    matches=[]
    if exports.is_dir():
        for folder in exports.iterdir():
            if folder.is_dir() and key(folder.name) in aliases[name]:
                candidate=folder/'nexto-model.pt'
                if candidate.is_file():matches.append(candidate.resolve())
    if len(matches)>1:
        raise RuntimeError(f'Ambiguous RLBot exports for {name}: {matches}; set explicit path in config')
    if len(matches)==1:return matches[0]
    standard={
        'nexto':'vendor/nexto/nexto-model.pt',
        'cycle9':'data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt',
        'v60':'data/isolated/slater_v027_campaign01_u0060.pt',
        'v70':'data/isolated/v040_multirival_campaign01_u0070.pt',
    }
    if name in standard and (root/standard[name]).is_file():
        return (root/standard[name]).resolve()
    choices=[]
    if exports.is_dir():
        choices=[str(p.relative_to(root)) for p in exports.glob('*/nexto-model.pt')]
    raise FileNotFoundError(
        f'Cannot locate {name} model. Available RLBot exports: {choices}. '
        f'Set "{name}" to the exact nexto-model.pt path in slater_v041_config.json')

def validate_pool(root, config):
    cfg = config['opponents']
    files={name:find_model(root,name,cfg.get(name)) for name in RIVAL_NAMES}
    pinned_fallbacks={
        'nexto':root/'vendor/nexto/nexto-model.pt',
        'cycle9':root/'data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt',
        'v60':root/'data/isolated/slater_v027_campaign01_u0060.pt',
    }
    trusted={'nexto':NEXTO_SHA,'cycle9':CYCLE9_SHA,'v60':V60_SHA}
    hashes=verify_protected({k:(p, trusted[k] if k in trusted and p.resolve()==pinned_fallbacks[k].resolve() else None)
                              for k,p in files.items()})
    if len({hashes[n] for n in RIVAL_NAMES}) != len(RIVAL_NAMES):
        raise ValueError('Six rivals resolve to duplicated weights. Check export folders and config.')
    return {n:{'path':str(files[n]),'sha256':hashes[n]} for n in RIVAL_NAMES}

def validate_config(c):
    if set(c['opponents']) != set(RIVAL_NAMES):raise ValueError('Exactly six rivals required')
    for key in ('rollout_steps','updates_per_trial','episode_steps','eval_steps','screen_seeds','promotion_seeds','max_archive','min_disk_gb'):
        if not isinstance(c[key],int) or c[key]<1:raise ValueError(f'{key} must be positive integer')
    if not (128<=c['rollout_steps']<=4096 and 1<=c['updates_per_trial']<=12
            and 120<=c['episode_steps']<=4500 and 120<=c['eval_steps']<=4500
            and 1<=c['screen_seeds']<=8 and 2<=c['promotion_seeds']<=16
            and 2<=c['max_archive']<=64 and 1<=c['min_disk_gb']<=100):
        raise ValueError('Config limits exceeded')
    for k in ('small_mutation','large_mutation','promote_margin'):
        if not isinstance(c[k], (int,float)) or not math.isfinite(c[k]):raise ValueError(k)
    if not (0 < c['small_mutation']<=.05 and c['small_mutation']*2<=c['large_mutation']<=.15):
        raise ValueError('Mutation scales unsafe')
    if not (0 < c['promote_margin'] <= .5):raise ValueError('Promotion margin unsafe')
    if c.get('save_every_update') is not True:
        raise ValueError('Unattended training requires saving every PPO update')
    if c.get('run_name') is None or not c['run_name'].replace('_','').replace('-','').isalnum() or len(c['run_name'])>32:
        raise ValueError('Invalid run name')
    return c

def specs_for_generation(gen, archive_count):
    # A large parameter-space jump, two local derivatives, two local trials
    # from the incumbent, plus one from the previous archive if available.
    specs=[{'kind':'large_root','base':'leader'},
           {'kind':'large_child_1','base':'large_root'},
           {'kind':'large_child_2','base':'large_root'},
           {'kind':'leader_small_1','base':'leader'},
           {'kind':'leader_small_2','base':'leader'}]
    if archive_count > 0:specs.append({'kind':'previous_generation_small','base':'archive'})
    return specs

def training_mode_index(pool_size, episode_count, offset):
    """Balanced cyclic opponent assignment; one opponent per completed episode.

    A seeded initial offset diversifies small trials across the six frozen rivals
    and the current provisional leader. This does not guarantee equal rollout
    time because episodes can have different lengths.
    """
    if pool_size < 1 or episode_count < 1:
        raise ValueError('Mode scheduling requires a nonempty pool and a positive episode index')
    return (episode_count - 1 + int(offset)) % pool_size


def outcome_score(rows):
    wins=sum(r['outcome']==1 for r in rows)
    losses=sum(r['outcome']==-1 for r in rows)
    censored=sum(r['outcome']==0 for r in rows)
    return {'n':len(rows),'wins':wins,'losses':losses,'censored_timeouts':censored,
            'net_outcome_per_episode':(wins-losses)/len(rows) if rows else None}

def paired_scores(rows):
    """rows: [{rival,seed,side,candidate_outcome,leader_outcome}]."""
    if not rows:raise ValueError('Empty comparison')
    keys=set()
    for row in rows:
        key=(row['rival'],row['seed'],row['side'])
        if key in keys:raise ValueError('Duplicate paired evaluation key')
        keys.add(key)
        if row['candidate_outcome'] not in (-1,0,1) or row['leader_outcome'] not in (-1,0,1):
            raise ValueError('Invalid outcome')
    c=outcome_score([{'outcome':r['candidate_outcome']} for r in rows])
    b=outcome_score([{'outcome':r['leader_outcome']} for r in rows])
    diffs=[r['candidate_outcome']-r['leader_outcome'] for r in rows]
    by_rival={}
    for rival in sorted(set(r['rival'] for r in rows)):
        part=[r for r in rows if r['rival']==rival]
        by_rival[rival]={'candidate':outcome_score([{'outcome':r['candidate_outcome']} for r in part]),
                         'leader':outcome_score([{'outcome':r['leader_outcome']} for r in part]),
                         'difference':sum(r['candidate_outcome']-r['leader_outcome'] for r in part)/len(part)}
    return {'candidate':c,'leader':b,'mean_paired_delta':sum(diffs)/len(diffs),
            'resolved_pairs':sum(r['candidate_outcome']!=0 or r['leader_outcome']!=0 for r in rows),
            'by_rival':by_rival}

def should_promote(result, *, margin, min_resolved):
    if result['resolved_pairs'] < min_resolved:return False,'insufficient_decisive_episodes'
    if result['mean_paired_delta'] < margin:return False,'no_mean_advantage'
    # No large downside against core opponents even if weaker opponents inflate score.
    for name in ('nexto','cycle9','v60','v70'):
        rival=result['by_rival'].get(name)
        if rival and rival['difference'] < -0.34:return False,'core_opponent_regression_'+name
    return True,'promising_simulator_candidate_only'

@contextlib.contextmanager
def process_lock(path):
    """Kernel-held byte lock: abandoned processes release automatically on Windows."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:raise RuntimeError('Overnight league already running') from exc
            try:yield
            finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc:raise RuntimeError('Overnight league already running') from exc
            try:yield
            finally:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def space_preflight(root, gb):
    remaining=shutil.disk_usage(root).free
    if remaining < gb*1024**3:raise RuntimeError(f'Free disk {remaining/1024**3:.1f} GiB < {gb} GiB minimum')
    return remaining

DEFAULT_CONFIG={
 'run_name':'overnight01',
 'opponents':{n:None for n in RIVAL_NAMES},
 'rollout_steps':512, 'updates_per_trial':3, 'episode_steps':450,
 'eval_steps':600, 'screen_seeds':1, 'promotion_seeds':3,
 'small_mutation':0.012, 'large_mutation':0.065,
 'promote_margin':0.13,'max_archive':10, 'min_disk_gb':2,
 'save_every_update':True, 'generation_candidates_limit':6,
 'teacher_weight_small':0.30, 'teacher_weight_large':0.10,
 'actor_lr_small':2e-6, 'actor_lr_large':8e-6,
 'epochs':2,'minibatch':128,
 'limit_generations':0,
}
