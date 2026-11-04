"""Bounded-memory progress summaries; exports approved metrics, never raw logs."""
from __future__ import annotations

import csv
from collections import defaultdict, deque
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit, urlunsplit
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BOTS={'scripted','nexto','ripple','chronos','galactus','latest','history'}
SCENARIOS={'kickoff','shot','defense','dribble','aerial','recovery','wall','replay'}
REWARDS={'goal','potential','approach','touch','high_touch','ball_progress','boost_cost'}
PPO_KEYS={'train/loss','train/value_loss','train/policy_gradient_loss','train/entropy_loss',
          'train/approx_kl','train/clip_fraction','train/learning_rate','train/explained_variance',
          'train/n_updates','rollout/ep_rew_mean','rollout/ep_len_mean','time/fps'}


def number(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (TypeError,ValueError,OverflowError): return None


def numbers(data,keys):
    if not isinstance(data,dict): return {}
    return {k:number(data[k]) for k in keys if k in data and number(data[k]) is not None}


def read_json(path):
    try:
        with Path(path).open(encoding='utf8') as f: result=json.load(f)
        return result if isinstance(result,dict) else {}
    except (OSError,ValueError): return {}


def safe_url(value):
    try:
        url=urlsplit(value or '')
        if url.scheme!='https' or url.username or url.password: return None
        if url.hostname in {'wandb.ai','wandb.coreweave.com'}:
            pattern=r'/[\w.-]+/[\w.-]+/runs/[\w-]+/?'
        elif url.hostname=='forge.coreweave.com':
            pattern=r'/wandb/[\w.-]+/[\w.-]+/runs/[\w-]+/?'
        else: return None
        if not re.fullmatch(pattern,url.path): return None
        return urlunsplit((url.scheme,url.netloc,url.path,'',''))
    except (ValueError,TypeError): return None


def clean_config(cfg):
    result=numbers(cfg,{'workers','threads','seed'})
    for key,values in [('device',{'cpu','cuda','auto'}),('rewards',{'shaped','sparse'})]:
        if cfg.get(key) in values: result[key]=cfg[key]
    ppo=cfg.get('ppo',{})
    result['ppo']=numbers(ppo,{'learning_rate','n_steps','batch_size','n_epochs','gamma',
                               'gae_lambda','clip_range','ent_coef'})
    layers=ppo.get('net_arch')
    if isinstance(layers,list) and all(isinstance(n,int) and 0<n<100000 for n in layers):
        result['ppo']['net_arch']=layers[:10]
    result['env']=numbers(cfg.get('env',{}),{'episode_seconds','no_touch_seconds'})
    result['env']['uses_replay_bank']=bool(cfg.get('env',{}).get('replay_bank'))
    result['league']=numbers(cfg.get('league',{}),{'snapshot_every','history_size'})
    result['league']['weights']=numbers(cfg.get('league',{}).get('weights',{}),BOTS)
    result['curriculum']={'adaptive':bool(cfg.get('curriculum',{}).get('adaptive')),
        'weights':numbers(cfg.get('curriculum',{}).get('weights',{}),SCENARIOS)}
    return result


def clean_episode(raw):
    step=number(raw.get('timesteps'));outcome=number(raw.get('outcome'))
    if step is None or step<0 or outcome not in {-1.,0.,1.}: return None
    opponent=str(raw.get('opponent','')).split(':')[0]
    scenario=raw.get('scenario')
    if opponent not in BOTS or scenario not in SCENARIOS: return None
    side=raw.get('side')
    if side not in (0,1): return None
    row=dict(timesteps=int(step),outcome=int(outcome),opponent=opponent,scenario=scenario,side=side,
        timeout=bool(raw.get('timeout')),practice_success=bool(raw.get('practice_success')),
        reward=number(raw.get('episode',{}).get('r')) or 0.,
        reward_parts=numbers(raw.get('reward_parts',{}),REWARDS))
    row.update({k:number(raw.get(k)) or 0. for k in ['touches','seconds','dribble_seconds']})
    return row


class Aggregate:
    def __init__(self): self.n=0;self.sums=defaultdict(float)
    def add(self,row):
        self.n+=1
        values=dict(score_fraction=row['outcome']==1,concede_fraction=row['outcome']==-1,
                    timeout_fraction=row['timeout'],contact_fraction=row['touches']>0,
                    practice_success_fraction=row['practice_success'],reward_mean=row['reward'],
                    touches_mean=row['touches'],seconds_mean=row['seconds'])
        for k,v in values.items(): self.sums[k]+=v
    def summary(self): return dict(episodes=self.n,**{k:v/self.n for k,v in self.sums.items()}) if self.n else {'episodes':0}


class TimeBins:
    def __init__(self,upper): self.width=max(1,math.ceil(upper/60));self.bins={}
    def add(self,row):
        while row['timesteps']//self.width>=60:
            merged={}
            for i,agg in self.bins.items():
                target=merged.setdefault(i//2,Aggregate());target.n+=agg.n
                for k,v in agg.sums.items(): target.sums[k]+=v
            self.bins=merged;self.width*=2
        self.bins.setdefault(row['timesteps']//self.width,Aggregate()).add(row)
    def points(self):
        return [dict(timesteps=(i+.5)*self.width,**agg.summary()) for i,agg in sorted(self.bins.items())]


def snapshot_lines(path,notes):
    """Read a size snapshot so an active append-only log cannot extend this loop."""
    try:
        with Path(path).open('rb') as f:
            limit=os.fstat(f.fileno()).st_size
            while f.tell()<limit:
                line=f.readline(min(1024*1024,limit-f.tell()))
                if not line: break
                if not line.endswith(b'\n'):
                    notes['partial_or_oversize_lines']+=1
                    if len(line)>=1024*1024: break
                    continue
                yield line.decode('utf8',errors='replace')
    except OSError:
        notes['unavailable_logs']+=1


def episode_summaries(path,upper):
    notes=defaultdict(int);first=[];last=deque(maxlen=2000);total=Aggregate();bins=TimeBins(upper)
    groups=defaultdict(Aggregate)
    for line in snapshot_lines(path,notes):
        try: row=clean_episode(json.loads(line))
        except (ValueError,TypeError,AttributeError): row=None
        if row is None: notes['invalid_episode_rows']+=1;continue
        total.add(row);bins.add(row);groups[row['opponent']].add(row)
        if len(first)<2000: first.append(row)
        last.append(row)
    count=min(2000,total.n//2)
    early=first[:count];late=list(last)[-count:] if count else []
    def summarize(rows):
        agg=Aggregate()
        for row in rows: agg.add(row)
        return agg.summary()
    a=defaultdict(Aggregate);b=defaultdict(Aggregate)
    for target,rows in [(a,early),(b,late)]:
        for row in rows:
            if row['opponent'] in {'latest','history'}: continue
            target[(row['opponent'],row['scenario'],row['side'])].add(row)
    matched=[]
    for key in sorted(a.keys()&b.keys()):
        before=a[key].summary();after=b[key].summary()
        matched.append(dict(opponent=key[0],scenario=key[1],side=key[2],early=before,late=after,
                            score_delta=after['score_fraction']-before['score_fraction']))
    return dict(total=total.summary(),by_opponent={k:v.summary() for k,v in groups.items()},
                early=summarize(early),late=summarize(late),matched_cells=matched,
                windows=bins.points(),notes=dict(notes))


def ppo_summaries(run):
    notes=defaultdict(int);samples=deque(maxlen=2000);recent=defaultdict(lambda:deque(maxlen=20))
    files=sorted((run/'logs/history').glob('progress_*.csv'))+[run/'logs/progress.csv']
    rows=0;previous=None
    for path in files:
        if not path.exists(): continue
        notes['csv_sessions']+=1
        try:
            for row in csv.DictReader(snapshot_lines(path,notes)):
                step=number(row.get('time/total_timesteps'))
                if step is None: continue
                if previous is not None and step<previous: notes['timestep_rewinds']+=1
                previous=step;rows+=1
                values=numbers(row,PPO_KEYS)
                for key in PPO_KEYS:
                    if row.get(key,'') not in ('',None) and number(row[key]) is None:
                        if key!='train/explained_variance': notes['nonfinite_optimizer_metrics']+=1
                for k,v in values.items(): recent[k].append(v)
                samples.append(dict(timesteps=int(step),**values))
        except (csv.Error,TypeError,ValueError): notes['invalid_csv_rows']+=1
    values=list(samples)
    if len(values)>250: values=values[::math.ceil(len(values)/250)]
    return dict(rows_read=rows,chart_scope='last 2000 optimizer log rows, sampled to at most 250 points',
                points=values,recent_mean={k:sum(v)/len(v) for k,v in recent.items()},notes=dict(notes))


def checkpoint_metadata(run):
    result=[]
    for path in sorted((run/'checkpoints').glob('step_*.zip.json')):
        if not re.fullmatch(r'step_[0-9]+\.zip\.json',path.name): continue
        meta=read_json(path);step=number(meta.get('timesteps'));digest=meta.get('sha256','')
        if step is not None and re.fullmatch(r'[0-9a-f]{64}',digest):
            result.append(dict(timesteps=int(step),sha256=digest))
    return result


def evaluation_summaries(reports,latest_hash,known_hashes):
    result=[]
    for file in sorted(Path(reports).glob('*.json'),key=lambda f:f.stat().st_mtime,reverse=True):
        data=read_json(file)
        if data.get('kind')!='first_goal_trials': continue
        digest=data.get('candidate_sha256','')
        if not re.fullmatch(r'[0-9a-f]{64}',digest) or digest not in known_hashes: continue
        def clean_trials(items):
            rows=[]
            for raw in items:
                if not isinstance(raw,dict): continue
                item=clean_episode(dict(raw,timesteps=0))
                if item:
                    row={k:item[k] for k in ['opponent','scenario','side','outcome','timeout','practice_success','touches']}
                    seed=number(raw.get('seed'))
                    if seed is not None: row['seed']=int(seed)
                    rows.append(row)
            return rows
        rows=clean_trials(data.get('trials',[]))
        result.append(dict(candidate_sha256=digest,matches_latest_checkpoint=digest==latest_hash,
            baseline_sha256=data.get('baseline_sha256') if re.fullmatch(r'[0-9a-f]{64}',str(data.get('baseline_sha256',''))) else None,
            summary=numbers(data.get('summary',{}),{'trials','first_goal_wins','first_goal_losses','timeouts',
                'first_goal_score_fraction','resolved_fraction','practice_success_fraction','touches_per_trial'}),
            baseline_summary=numbers(data.get('baseline_summary',{}),{'trials','first_goal_wins','first_goal_losses','timeouts','first_goal_score_fraction'}),
            baseline_trials=clean_trials(data.get('baseline_trials',[])),
            comparison=numbers(data,{'paired_mean_outcome_delta','paired_delta_standard_error',
                                      'seconds_per_trial','seed_start'}),trials=rows))
        if len(result)>=5: break
    return result


def review_flags(episodes,ppo,evaluations):
    flags=[]
    if episodes['total']['episodes']<100:
        flags.append('Few completed episodes: training trends are inconclusive. Errors can still be investigated now.')
    late=episodes['late'];early=episodes['early']
    if late['episodes']>=100:
        if late.get('contact_fraction',0)<.05:
            flags.append('Fewer than 5% of recent episodes contain a learner touch. Review observations, actions, teacher warm-start and starting positions.')
        if late.get('timeout_fraction',0)>.9:
            flags.append('Over 90% of recent episodes time out. Review ball contacts and episode horizons; this alone does not identify a bug.')
        if late.get('reward_mean',0)>early.get('reward_mean',0)+.5 and late.get('score_fraction',0)<=early.get('score_fraction',0):
            flags.append('Reward increased without a corresponding overall scoring increase. Check shaping and fixed-condition evaluations before calling this improvement.')
    recent=ppo['recent_mean']
    if recent.get('train/approx_kl',0)>.1:
        flags.append('Recent mean PPO KL exceeds 0.1. Review update size, learning rate and epoch count; appropriate values depend on the run.')
    if 'train/entropy_loss' in recent and abs(recent['train/entropy_loss'])<.1:
        flags.append('Recent policy entropy is very low. Check action diversity and performance before changing entropy settings.')
    if ppo['notes'].get('nonfinite_optimizer_metrics'):
        flags.append('Nonfinite optimizer metrics were recorded. Inspect the training console and optimization settings.')
    if not any(e['matches_latest_checkpoint'] for e in evaluations):
        flags.append('No included evaluation matches the newest recorded checkpoint. Use launcher 20 after pausing, then export again.')
    return flags


def csv_text(rows):
    if not rows: return ''
    keys=sorted({k for row in rows for k in row})
    out=io.StringIO();writer=csv.DictWriter(out,keys);writer.writeheader();writer.writerows(rows)
    return out.getvalue()


def html_report(report):
    payload=json.dumps(report,allow_nan=False).replace('<',r'\u003c')
    return '''<!doctype html><meta charset="utf-8"><title>NovaForge progress</title>
<style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:0 20px;color:#182232;background:#f7f9fc}article{background:white;padding:20px;border-radius:12px;margin:16px 0}svg{width:100%;height:260px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:8px;border-bottom:1px solid #ddd}select{font:inherit}li{margin:10px 0}.muted{color:#506176}</style>
<h1>NovaForge progression report</h1><p id="headline"></p>
<article><h2>Review notes</h2><ul id="flags"></ul><p class="muted">Training mixes, curriculum difficulty and self-play opponents change. These charts describe training; fixed-condition evaluations provide stronger evidence of playing-strength changes. No settings were changed by this exporter.</p></article>
<article><h2>Checkpoint evaluations</h2><p class="muted">Fixed opponents, paired seeds and both team sides. Score-first fractions include timeouts in the denominator. These are short simulator trials; they do not measure full-match win rate. Higher outcome delta favors the current checkpoint; outcome is +1 for score first, -1 for concede first and 0 for timeout. SE is a trial-level estimate; shared seeds can correlate trials.</p><table><thead><tr><th>Checkpoint</th><th>Candidate score first / n</th><th>Baseline score first / n</th><th>Candidate / baseline timeouts</th><th>Paired outcome delta (SE)</th></tr></thead><tbody id="evaluations"></tbody></table><p id="noEvaluations"></p></article>
<article><h2>Learning signals</h2><select id="metric"></select><svg id="chart" viewBox="0 0 900 260"></svg><p class="muted">X: learner decisions. Contact and first-goal fractions are episode statistics; timeouts are shown separately.</p></article>
<article><h2>Optimizer and throughput</h2><select id="ppoMetric"></select><svg id="ppoChart" viewBox="0 0 900 260"></svg><p class="muted">SPS/FPS counts learner decisions across all arenas, including rollout and PPO time. Each decision advances four physics ticks; teacher actions add no learner samples. SB3 n_updates counts training epochs. Entropy loss is negative categorical entropy (maximum entropy ln(276), about 5.62). PPO CSV coverage may be incomplete for sessions before v1.3.</p></article>
<article><h2>Opponent totals</h2><table><thead><tr><th>Opponent</th><th>Episodes</th><th>Score first</th><th>Timeout</th><th>Any touch</th></tr></thead><tbody id="opponents"></tbody></table></article>
<article><h2>Fixed-teacher cells: early vs late</h2><p class="muted">Grouped by bot, practice scenario and team side. First/last windows are disjoint, at most 2,000 episodes each. Difficulty can still change; small samples and positive deltas do not prove improvement.</p><table><thead><tr><th>Bot / scenario / side</th><th>Early n</th><th>Late n</th><th>Score-fraction change</th></tr></thead><tbody id="cells"></tbody></table></article>
<script id="data" type="application/json">'''+payload+'''</script><script>
const d=JSON.parse(document.getElementById('data').textContent),pct=v=>(100*(v||0)).toFixed(1)+'%';
document.getElementById('headline').textContent=`${d.run} | ${d.episodes.total.episodes} completed episodes | checkpoint step ${d.latest_checkpoint?.timesteps??'unknown'} | session average SPS ${d.status.fps_since_start?.toFixed(1)??'unavailable'}`;
for(const message of d.review_flags){const li=document.createElement('li');li.textContent=message;document.getElementById('flags').append(li)}
function row(target,values){const tr=document.createElement('tr');for(const v of values){const td=document.createElement('td');td.textContent=v;tr.append(td)}document.getElementById(target).append(tr)}
for(const [name,v] of Object.entries(d.episodes.by_opponent))row('opponents',[name,v.episodes,pct(v.score_fraction),pct(v.timeout_fraction),pct(v.contact_fraction)]);
for(const v of d.episodes.matched_cells)row('cells',[`${v.opponent} / ${v.scenario} / ${v.side}`,v.early.episodes,v.late.episodes,(100*v.score_delta).toFixed(1)+' percentage points']);
for(const e of d.evaluations){const a=e.summary,b=e.baseline_summary,c=e.comparison,delta=c.paired_mean_outcome_delta,se=c.paired_delta_standard_error;row('evaluations',[e.matches_latest_checkpoint?'latest recorded':e.candidate_sha256.slice(0,12),`${pct(a.first_goal_score_fraction)} / ${a.trials??0}`,b.trials?`${pct(b.first_goal_score_fraction)} / ${b.trials}`:'none',`${a.timeouts??0} / ${b.timeouts??'n/a'}`,delta===undefined?'n/a':`${delta.toFixed(3)} (${se===undefined?'n/a':se.toFixed(3)})`])}
if(!d.evaluations.length)document.getElementById('noEvaluations').textContent='No checkpoint evaluations included. Pause with launcher 15, then use launcher 20.';
function draw(id,points,key){const svg=document.getElementById(id);svg.replaceChildren();const ns='http://www.w3.org/2000/svg',add=(tag,attrs,text)=>{const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;svg.append(el);return el};const p=points.filter(v=>Number.isFinite(v[key]));if(!p.length){add('text',{x:40,y:100},'No data for this metric');return}let lo=Math.min(...p.map(v=>v[key])),hi=Math.max(...p.map(v=>v[key]));if(key.endsWith('_fraction')){lo=0;hi=1}else if(hi===lo){lo-=.5;hi+=.5}const xmin=Math.min(...p.map(v=>v.timesteps)),xmax=Math.max(...p.map(v=>v.timesteps)),x=v=>65+800*(v-xmin)/Math.max(1,xmax-xmin),y=v=>220-180*(v-lo)/(hi-lo);add('path',{d:'M65 35V220H870',fill:'none',stroke:'#8394a8'});add('polyline',{points:p.map(v=>`${x(v.timesteps)},${y(v[key])}`).join(' '),fill:'none',stroke:'#176bd4','stroke-width':2});for(const v of p){const dot=add('circle',{cx:x(v.timesteps),cy:y(v[key]),r:3,fill:'#176bd4'});const title=document.createElementNS(ns,'title');title.textContent=`step ${v.timesteps}: ${v[key]}`;dot.append(title)}add('text',{x:2,y:40},hi.toPrecision(4));add('text',{x:2,y:220},lo.toPrecision(4));add('text',{x:65,y:248},Math.round(xmin));add('text',{x:780,y:248},Math.round(xmax))}
function select(id,target,points,keys){const sel=document.getElementById(id);for(const key of keys){const o=document.createElement('option');o.value=key;o.textContent=key;sel.append(o)}sel.onchange=()=>draw(target,points,sel.value);sel.onchange()}
select('metric','chart',d.episodes.windows,['contact_fraction','score_fraction','timeout_fraction','practice_success_fraction','reward_mean','touches_mean']);select('ppoMetric','ppoChart',d.ppo.points,['time/fps','train/entropy_loss','train/approx_kl','train/clip_fraction','train/explained_variance','train/value_loss','train/policy_gradient_loss','train/loss','train/n_updates']);
</script>'''


def export_report(run_dir,out_dir):
    run=Path(run_dir);out_dir=Path(out_dir)
    if not (run/'config.json').exists(): raise FileNotFoundError('No training configuration found for this run')
    cfg=clean_config(read_json(run/'config.json'));raw_status=read_json(run/'status.json')
    status=numbers(raw_status,{'timesteps','fps_since_start','episodes_this_session','wins','losses','timeouts','session_seconds'})
    status['continuous']=bool(raw_status.get('continuous'))
    allowed_states={'training','saved','stopped','finished','error','interrupted; saved'}
    status['state']=raw_status.get('state') if raw_status.get('state') in allowed_states else 'unknown'
    tracking=read_json(run/'wandb_status.json')
    status['wandb_url']=safe_url(tracking.get('url'))
    status['wandb_mode']=tracking.get('mode') if tracking.get('mode') in {'online','offline','off'} else 'unknown'
    checkpoints=checkpoint_metadata(run)
    latest=checkpoints[-1] if checkpoints else {}
    episodes=episode_summaries(run/'episodes.jsonl',max(status.get('timesteps',0),latest.get('timesteps',0)))
    ppo=ppo_summaries(run)
    evaluations=evaluation_summaries(out_dir,latest.get('sha256'),{c['sha256'] for c in checkpoints})
    packages={}
    for key,value in read_json(run/'provenance.json').get('packages',{}).items():
        if key in {'torch','numpy','stable-baselines3','rlgym-rocket-league','rlgym-tools','RocketSim','onnxruntime'} and isinstance(value,str) and re.fullmatch(r'[0-9][0-9A-Za-z.+_-]{0,80}',value): packages[key]=value
    report=dict(schema_version=1,run=run.name,generated_utc=datetime.now(timezone.utc).isoformat(),
        config=cfg,status=status,packages=packages,checkpoint_count=len(checkpoints),
        sampling=dict(unit='one learner car decision',physics_ticks_per_decision=4,physics_ticks_per_sim_second=120,
            learner_cars_per_arena=1,decisions_per_sim_second_per_arena=30,teacher_decisions_counted=False,
            sps_scope='all arenas; rollout and PPO time included; status is session average, SB3 CSV is learn-call average',
            sb3_n_updates_unit='training epochs, not minibatch optimizer steps'),
        latest_checkpoint=latest,checkpoint_history=checkpoints,episodes=episodes,ppo=ppo,evaluations=evaluations,
        comparison_limits='Training metrics use evolving tasks/opponents. Held-out paired evaluations are separate. A reward rise or more SPS does not establish skill improvement.')
    report['review_flags']=review_flags(episodes,ppo,evaluations)
    rows=[dict(opponent=c['opponent'],scenario=c['scenario'],side=c['side'],
        early_episodes=c['early']['episodes'],late_episodes=c['late']['episodes'],
        early_score_fraction=c['early']['score_fraction'],late_score_fraction=c['late']['score_fraction'],
        score_delta=c['score_delta']) for c in episodes['matched_cells']]
    members={'report.json':json.dumps(report,indent=2,allow_nan=False),
        'progress.html':html_report(report),'training_windows.csv':csv_text(episodes['windows']),
        'opponent_comparisons.csv':csv_text(rows),'ppo_metrics.csv':csv_text(ppo['points']),
        'READ_ME.txt':'Open progress.html in a browser. Upload this ZIP in the chat for review.\n'
            'Optional: include a short clip and describe what the bot does badly.\n'
            'This bundle contains approved metrics/configuration and checkpoint hashes; no model weights, raw logs, replay files, W&B event files or credentials are copied.\n'
            'The exporter does not change or pause training. Export while paused for a quieter snapshot.\n'
            'Use launcher 20 while paused for an earliest-saved-checkpoint vs current-checkpoint evaluation, then export again.\n'}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_UTC')
    name=re.sub(r'[^A-Za-z0-9_-]','_',run.name)[:64]
    out_dir.mkdir(parents=True,exist_ok=True)
    destination=out_dir/f'{name}_progress_{stamp}_{uuid.uuid4().hex[:6]}.zip'
    fd,temp=tempfile.mkstemp(dir=out_dir,suffix='.tmp')
    try:
        with os.fdopen(fd,'w+b') as f:
            with zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as z:
                for filename,value in members.items(): z.writestr(filename,value)
            f.flush();os.fsync(f.fileno())
        os.replace(temp,destination)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return destination


def report_command(args):
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve(): raise ValueError('Run name must be one folder name')
    path=export_report(run,ROOT/'reports')
    print(f'PROGRESS_REPORT_READY: {path}')
    print('Upload this ZIP in the chat. Open progress.html inside it to view the charts.')


def compare_command(args):
    from filelock import FileLock, Timeout
    from .core import check_model
    from .training import resolve_model
    from .evaluation import evaluate
    from types import SimpleNamespace
    run=(ROOT/'runs'/args.run).resolve()
    if run.parent!=(ROOT/'runs').resolve(): raise ValueError('Invalid run name')
    if not (run/'config.json').exists(): raise FileNotFoundError('No such training run')
    try:
        with FileLock(str(run/'train.lock'),timeout=0):
            current=resolve_model(run);baseline=None
            for path in sorted((run/'checkpoints').glob('step_*.zip')):
                try: check_model(path)
                except (OSError,ValueError): continue
                baseline=path;break
            if baseline is None or baseline.resolve()==current.resolve():
                raise ValueError('Need an initial checkpoint and a later checkpoint before comparing progress')
            stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_UTC')
            out=ROOT/'reports'/f'{args.run}_eval_{stamp}_{uuid.uuid4().hex[:6]}.json'
            evaluate(SimpleNamespace(model=str(current),baseline=str(baseline),config=str(run/'config.json'),
                opponents=args.opponents,scenarios=args.scenarios,pairs=args.pairs,seconds=args.seconds,
                seed=args.seed,out=str(out)))
    except Timeout:
        raise RuntimeError('Pause this run with launcher 15 and wait for it to save/exit before running the comparison.') from None
