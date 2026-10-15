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
import time
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
    try:
        with tmp.open('x', encoding='utf-8') as f:
            json.dump(obj, f, indent=2, sort_keys=True)
            f.flush(); os.fsync(f.fileno())
        # Windows readers may briefly hold a handle without FILE_SHARE_DELETE.
        # Keep the old complete file until replacement succeeds; never truncate
        # or remove it to work around a sharing/access violation.
        for attempt in range(9):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as exc:
                if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 8:
                    raise
                time.sleep(min(.02 * 2**attempt, .25))
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass  # A scanner may still hold the temporary file on Windows.

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
            and 1<=c['screen_seeds']<=8 and 2<=c['promotion_seeds']<=128
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
    for key,low,high in (('target_kl',1e-5,.1),('promotion_error_budget',1e-6,.1)):
        value=c.get(key,DEFAULT_CONFIG[key])
        if not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'Invalid {key}')
    if c.get('generation_candidates_limit',6)!=6:
        raise ValueError('This league implements a six-candidate generation budget')
    if not isinstance(c.get('limit_generations',0),int) or c.get('limit_generations',0)<0:
        raise ValueError('limit_generations must be a nonnegative integer')
    if c.get('training_reset','kickoff') not in ('kickoff','mixed_ground'):
        raise ValueError('Invalid training reset distribution')
    if not isinstance(c.get('rlbot_delay',False),bool):
        raise ValueError('rlbot_delay must be boolean')
    if c.get('replay_starts') is not None and not isinstance(c['replay_starts'],str):
        raise ValueError('replay_starts must be a path or null')
    p=c.get('replay_start_probability',.2)
    if not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=.5:
        raise ValueError('Replay reset probability must be between 0 and .5')
    return c

def specs_for_generation(gen, archive_count):
    # Include ordinary PPO continuation: every candidate need not first damage
    # a strong incumbent with parameter noise. Keep the original trial budget.
    specs=[{'kind':'ppo_continuation','base':'leader'},
           {'kind':'large_root','base':'leader'},
           {'kind':'large_child_1','base':'large_root'},
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
        if row['side'] not in ('blue','orange') or row['rival'] not in RIVAL_NAMES:
            raise ValueError('Invalid evaluation side or rival')
        key=(row['rival'],row['seed'],row['side'])
        if key in keys:raise ValueError('Duplicate paired evaluation key')
        keys.add(key)
        if row['candidate_outcome'] not in (-1,0,1) or row['leader_outcome'] not in (-1,0,1):
            raise ValueError('Invalid outcome')
        for policy in ('candidate','leader'):
            timeout=row.get(policy+'_timeout')
            if timeout is not None and timeout != (row[policy+'_outcome']==0):
                raise ValueError('Timeout flag disagrees with first-goal outcome')
    c=outcome_score([{'outcome':r['candidate_outcome']} for r in rows])
    b=outcome_score([{'outcome':r['leader_outcome']} for r in rows])
    diffs=[r['candidate_outcome']-r['leader_outcome'] for r in rows]
    by_rival={}
    for rival in sorted(set(r['rival'] for r in rows)):
        part=[r for r in rows if r['rival']==rival]
        by_rival[rival]={'candidate':outcome_score([{'outcome':r['candidate_outcome']} for r in part]),
                         'leader':outcome_score([{'outcome':r['leader_outcome']} for r in part]),
                         'difference':sum(r['candidate_outcome']-r['leader_outcome'] for r in part)/len(part)}
    # A seed's two sides and six rivals are correlated. Treat the seed, rather
    # than the individual episode, as the unit of evidence.
    seed_deltas={}
    complete=True
    expected={(rival,side) for rival in RIVAL_NAMES for side in ('blue','orange')}
    for seed in sorted({r['seed'] for r in rows}):
        part=[r for r in rows if r['seed']==seed]
        complete &= {(r['rival'],r['side']) for r in part} == expected
        seed_deltas[seed]=sum(r['candidate_outcome']-r['leader_outcome'] for r in part)/len(part)
    positive=sum(d>0 for d in seed_deltas.values())
    negative=sum(d<0 for d in seed_deltas.values())
    n=positive+negative
    # Exact one-sided sign test, ties omitted. Tests consistency of advantage
    # across random seeds, not a confidence interval for mean goal difference.
    p_value=sum(math.comb(n,k) for k in range(positive,n+1))/2**n if n else 1.
    return {'candidate':c,'leader':b,'mean_paired_delta':sum(diffs)/len(diffs),
            'resolved_pairs':sum(r['candidate_outcome']!=0 or r['leader_outcome']!=0 for r in rows),
            'by_rival':by_rival,
            'seed_evidence':{'complete_balanced_rosters':bool(complete),
                'seed_count':len(seed_deltas),'positive_seeds':positive,
                'negative_seeds':negative,'tied_seeds':len(seed_deltas)-n,
                'sign_test_p_value':p_value}}

def should_promote(result, *, margin, min_resolved, alpha=.05, min_seeds=8):
    if result['resolved_pairs'] < min_resolved:return False,'insufficient_decisive_episodes'
    if result['mean_paired_delta'] < margin:return False,'no_mean_advantage'
    # No large downside against core opponents even if weaker opponents inflate score.
    for name in ('nexto','cycle9','v60','v70'):
        rival=result['by_rival'].get(name)
        if rival and rival['difference'] < -0.34:return False,'core_opponent_regression_'+name
    evidence=result.get('seed_evidence',{})
    if not evidence.get('complete_balanced_rosters'):
        return False,'incomplete_balanced_holdout'
    if evidence.get('positive_seeds',0)+evidence.get('negative_seeds',0) < min_seeds:
        return False,'insufficient_independent_seeds'
    if not 0 < alpha < 1:raise ValueError('alpha must be between zero and one')
    if evidence['sign_test_p_value'] > alpha:
        return False,'advantage_not_consistent_across_seeds'
    return True,'promising_simulator_candidate_only'


def promotion_alpha(generation, finalists=2, budget=.05):
    """Spend a bounded error budget across finalists AND repeated generations.

    Sum_{g>=1} 1/(g*(g+1))=1. Bonferroni protects the two independently
    screened finalists even though they share a holdout. Assumes valid
    independent seed draws within each fresh, previously unseen holdout.
    """
    if generation<1 or finalists<1 or not 0<budget<1:
        raise ValueError('Invalid promotion evidence budget')
    return budget/(generation*(generation+1)*finalists)


def holdout_seed_count(configured,generation,budget=.05):
    # A fixed 16-seed test eventually cannot clear a shrinking error budget,
    # even with every seed positive. Grow the holdout before that happens.
    required=math.ceil(-math.log2(promotion_alpha(generation,budget=budget)))+2
    return max(configured,required)


def evaluation_seed_base(generation,holdout):
    """Disjoint seed ranges for screen/holdout and every supported generation."""
    if generation<1:raise ValueError('Invalid generation')
    seed=2_000_000+(generation-1)*262144+(131072 if holdout else 0)
    if seed+127*997 >= 2**31-20000:
        raise ValueError('Evaluation seed namespace exhausted; start a new research protocol')
    return seed

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
 'run_name':'overnight02',
 'opponents':{n:None for n in RIVAL_NAMES},
 'rollout_steps':512, 'updates_per_trial':3, 'episode_steps':450,
 'eval_steps':600, 'screen_seeds':1, 'promotion_seeds':16,
 'small_mutation':0.012, 'large_mutation':0.065,
 'promote_margin':0.13,'max_archive':10, 'min_disk_gb':2,
 'save_every_update':True, 'generation_candidates_limit':6,
 'teacher_weight_small':0.30, 'teacher_weight_large':0.10,
 'actor_lr_small':2e-6, 'actor_lr_large':8e-6,
 'epochs':2,'minibatch':128,
 'target_kl':.02,'promotion_error_budget':.05,
 'training_reset':'mixed_ground','rlbot_delay':True,
 'replay_starts':None,'replay_start_probability':.2,
 'limit_generations':0,
}
