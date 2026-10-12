"""Slater v0.2.9 — watch an ACTUAL frozen Nexto vs Cycle9 / v027 match.

Reuses exactly Native1v1 / RoleSwap1v1 and greedy action selection from the
existing benchmark.  Creates a standalone offline, top-down HTML replay.
Optionally streams SAME simulator state to RLViser in 3D in real time.
NEVER trains, never modifies source checkpoints, never promotes candidates.

Windows example:
  .venv\\Scripts\\python.exe slater_watch_sim_v029.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --side blue --seed 1700420699 --max-episode-steps 450 --out data/isolated/slater_watch_v029_blue01.html
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import time
import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_paired_eval_v026_fixed as paired

NEXTO_SHA = paired.EXPECTED_NEXTO_SHA256


def checked_output(path, root):
    resolved = Path(path).resolve()
    isolated = (root / 'data' / 'isolated').resolve()
    if not resolved.is_relative_to(isolated) or resolved.suffix.lower() != '.html':
        raise ValueError('HTML output must be under data/isolated and end with .html')
    if resolved.exists():
        raise FileExistsError(f'No overwriting existing replay: {resolved}')
    return resolved


def numbers(x, n=3):
    a = np.asarray(x, dtype=float).reshape(-1)
    if not np.isfinite(a).all():
        raise FloatingPointError('Nonfinite RocketSim coordinates')
    return [round(float(v), n) for v in a]


def capture(state, step, side, actions=None):
    ball = state.ball
    snap = {
        'step': int(step),
        'ball': {'p': numbers(ball.position), 'v': numbers(ball.linear_velocity)},
        'goal': bool(state.goal_scored),
        'cars': {},
    }
    for name in ('blue-0', 'orange-0'):
        car = state.cars[name]
        p = car.physics
        snap['cars'][name] = {
            'p': numbers(p.position), 'v': numbers(p.linear_velocity),
            'f': numbers(p.forward), 'boost':round(float(car.boost_amount),2),
            'touch': int(car.ball_touches), 'ground': bool(car.on_ground),
        }
    if actions:
        for name in ('blue-0','orange-0'):
            if name in actions:
                snap['cars'][name]['action'] = numbers(actions[name], 2)
    return snap


def outcome_from_frame(frame, side):
    if not frame['goal']:
        return 0
    return paired.result_for_side(True,frame['ball']['p'][1],side)


def make_renderer():
    try:
        from rlgym.rocket_league.rlviser import RLViserRenderer
    except ImportError as exc:
        raise RuntimeError('RLViser not installed. Run: .venv\\Scripts\\python.exe -m pip install "rlgym[rl-rlviser]" ; then get Windows rlviser executable from https://github.com/VirxEC/rlviser/releases') from exc
    return RLViserRenderer(tick_rate=120 / base.ACTION_REPEAT)


def record_game(actor, nexto, actions, observer, seed, side, max_steps, renderer=None, pace=1.0):
    env = (base.Native1v1 if side == 'blue' else paired.RoleSwap1v1)(
        actions, observer, nexto, max_steps=max_steps, device='cpu'
    )
    try:
        random.seed(seed); np.random.seed(seed % (2**32)); torch.manual_seed(seed)
        obs = env.reset(seed)
        frames = [capture(env.state, 0, side)]
        if renderer:
            renderer.render(env.state, {})
        start_wall = time.monotonic()
        for step in range(1,max_steps+1):
            a = paired.greedy_action(actor,obs,env.device)
            obs,_,done,info = env.step(a)
            frames.append(capture(env.state, step, side, env.previous))
            if renderer:
                renderer.render(env.state,{})
                # Native RocketSim advances 8 ticks per decision (120 Hz physics).
                delay = step * base.ACTION_REPEAT / (120.0 * pace) - (time.monotonic()-start_wall)
                if delay > 0: time.sleep(delay)
            if done:break
        return {
            'side':side,'seed':seed,'frames':frames,
            'student_touches':int(info['student_touches']),
            'nexto_touches':int(info['opponent_touches']),
            'steps':int(info['steps']),
            'outcome':int(info['outcome']),
            'timeout':bool(info['timeout']),
            'final_ball_y':round(float(info['ball_y']),3),
        }
    finally:
        env.close()


HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Slater — RocketSim Gameplay Inspection</title>
<style>
:root{color-scheme:dark;font:14px system-ui,sans-serif}body{background:#0b1019;color:#e8edf5;margin:0;padding:22px;max-width:1160px;margin-inline:auto}h1{font-size:22px;margin-bottom:8px}p{color:#adb9ca;margin:6px 0 18px;line-height:1.5}
.bar{display:flex;flex-wrap:wrap;align-items:center;gap:12px;background:#151f2e;border:1px solid #28354b;border-radius:12px;padding:13px;margin:15px 0}.bar label{display:inline-flex;gap:7px;align-items:center}.bar button,.bar select{background:#2c3d59;color:#fff;border:1px solid #435979;border-radius:8px;padding:8px;cursor:pointer}.bar input[type=range]{flex:1;min-width:160px;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:16px}.panel{background:#151f2e;border:1px solid #28354b;border-radius:14px;padding:12px}.head{display:flex;justify-content:space-between;gap:8px;align-items:baseline}.head strong{font-size:17px}.head span{color:#afbbca;font-size:12px}.court{width:100%;height:auto;display:block;aspect-ratio: .79;background:#122e20;border-radius:7px}.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:10px;color:#c3cad4;font-size:12px}.stats b{color:white}.key{color:#97a6bf;font-size:12px}.note{padding:10px 0 24px;color:#b5c4d3}
</style></head><body>
<h1>Slater / RocketSim — Recorded Real Physics</h1>
<p>This is NOT a generated match and NOT the Rocket League client. These positions, velocities and controls were recorded directly from the <strong>same RocketSim evaluator</strong> running frozen Nexto. Top-down projection; read the Z values for jumps/aerials. The blue team attacks the <strong>top (+Y)</strong> goal, orange attacks the <strong>bottom (−Y)</strong> goal.</p>
<div class="bar"><button id="play">▶ Play</button><label>Speed <select id="speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option selected value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></label><label><input id="trails" type="checkbox" checked/> Trails</label><span id="clock">0.0 s</span><input aria-label="Scrub replay timeline" id="seek" type="range" min="0" value="0"/><span id="counter"></span></div>
<div id="panels" class="grid"></div>
<p class="note">Inspect: does kickoff look normal? Are cars driving toward the correct goals? Do they jump/boost? Do they drive through walls or teleport? Does the GOAL event match the ball entering a net? Compare <b>Original Cycle 9</b> and <b>trained u60</b> on the same seed and team side. For 3D inspection, use the optional RLViser mode.</p>
<script>
const GAMES = __DATA__;
const CANVAS_W=540, CANVAS_H=684;
let playing=false, cursor=0, speed=1, showTrails=true, lastTime=0;
let duration=Math.max(...GAMES.map(g=>g.frames.length-1));
const panels=document.getElementById('panels');
function el(tag,attrs={}){const x=document.createElement(tag);Object.entries(attrs).forEach(([k,v])=>x[k]=v);return x}
const P=GAMES.map((g,i)=>{let shell=el('div',{className:'panel'});let head=el('div',{className:'head'});head.append(el('strong',{textContent:g.policy}),el('span',{textContent:g.side.toUpperCase()+' · kickoff '+g.seed}));shell.append(head);let cv=el('canvas',{width:CANVAS_W,height:CANVAS_H,className:'court'});shell.append(cv);let st=el('div',{className:'stats'});shell.append(st);panels.append(shell);return {cv,ctx:cv.getContext('2d'),st}});
function screen(x,y){const margin=36;return [CANVAS_W/2+x/4096*(CANVAS_W/2-margin),CANVAS_H/2-y/5120*(CANVAS_H/2-margin)]}
function trail(ctx,g,end,fn,color){ctx.beginPath();let first=true;for(let i=Math.max(0,end-85);i<=end;i+=3){let q=fn(g.frames[i]);if(!q)continue;const [x,y]=screen(q[0],q[1]);if(first){ctx.moveTo(x,y);first=false}else ctx.lineTo(x,y)}ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke()}
function draw(g,pp,index){const ctx=pp.ctx, f=g.frames[Math.min(index,g.frames.length-1)];const W=CANVAS_W,H=CANVAS_H;ctx.clearRect(0,0,W,H);ctx.fillStyle='#163e2c';ctx.fillRect(0,0,W,H);
const [xL,yT]=screen(-4096,5120),[xR,yB]=screen(4096,-5120);ctx.strokeStyle='#779e87';ctx.lineWidth=2;ctx.strokeRect(xL,yT,xR-xL,yB-yT);const mid=screen(0,0);ctx.beginPath();ctx.moveTo(xL,mid[1]);ctx.lineTo(xR,mid[1]);ctx.stroke();ctx.beginPath();ctx.arc(mid[0],mid[1],47,0,Math.PI*2);ctx.stroke();
for(const goalY of [-5120,5120]){const [a,b]=screen(-893,goalY);const [c,d]=screen(893,goalY);ctx.strokeStyle=goalY>0?'#52a7ff':'#ffad57';ctx.lineWidth=7;ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke()}
if(showTrails){trail(ctx,g,Math.min(index,g.frames.length-1),f=>f.ball.p,'rgba(253,240,137,.75)');trail(ctx,g,Math.min(index,g.frames.length-1),f=>f.cars['blue-0'].p,'rgba(82,167,255,.50)');trail(ctx,g,Math.min(index,g.frames.length-1),f=>f.cars['orange-0'].p,'rgba(255,173,87,.50)')}
for(const [name,color] of [['blue-0','#52a7ff'],['orange-0','#ffad57']]){const c=f.cars[name];let [x,y]=screen(c.p[0],c.p[1]);let fx=c.f[0],fy=c.f[1],mag=Math.hypot(fx,fy)||1;fx/=mag;fy/=mag;ctx.save();ctx.translate(x,y);ctx.rotate(Math.atan2(-fy,fx));ctx.fillStyle=color;ctx.strokeStyle='#0c1421';ctx.lineWidth=2;ctx.fillRect(-11,-7,22,14);ctx.strokeRect(-11,-7,22,14);ctx.beginPath();ctx.moveTo(18,0);ctx.lineTo(5,-5);ctx.lineTo(5,5);ctx.closePath();ctx.fillStyle='white';ctx.fill();ctx.restore();ctx.fillStyle='#e8f0ff';ctx.font='12px system-ui';ctx.fillText(name==='blue-0'?'BLUE':'ORANGE',x+12,y-12)}
const b=f.ball.p,xy=screen(b[0],b[1]);ctx.beginPath();ctx.arc(xy[0],xy[1],Math.max(5,6+b[2]/150),0,Math.PI*2);ctx.fillStyle='#fff0a1';ctx.fill();ctx.strokeStyle='#705b2b';ctx.lineWidth=2;ctx.stroke();ctx.fillStyle='#e9f3ff';ctx.font='12px system-ui';ctx.fillText('Z '+Math.round(b[2]),xy[0]+12,xy[1]-8);
if(f.goal){ctx.fillStyle='rgba(10,10,18,.78)';ctx.fillRect(45,H/2-40,W-90,80);ctx.fillStyle='#fff';ctx.textAlign='center';ctx.font='bold 34px system-ui';ctx.fillText('GOAL — '+(b[1]>0?'BLUE':'ORANGE'),W/2,H/2+10);ctx.textAlign='left'}
const side=g.side==='blue'?'blue-0':'orange-0';const st=f.cars[side], opp=f.cars[g.side==='blue'?'orange-0':'blue-0'];let act=st.action||[];const stopped=index>=g.frames.length-1;
pp.st.innerHTML=`<span>State: <b>${f.goal?'GOAL':stopped?(g.timeout?'TIMEOUT':'END'):'PLAYING'}</b></span><span>Game time: <b>${(f.step*8/120).toFixed(2)}s</b></span><span>Slater height: <b>${Math.round(st.p[2])} uu</b></span><span>Ball height: <b>${Math.round(b[2])} uu</b></span><span>Slater boost: <b>${st.boost}</b></span><span>Nexto boost: <b>${opp.boost}</b></span><span>Slater touches total: <b>${g.student_touches}</b></span><span>Nexto touches total: <b>${g.nexto_touches}</b></span><span>Slater speed: <b>${Math.round(Math.hypot(...st.v))} uu/s</b></span><span>Ball speed: <b>${Math.round(Math.hypot(...f.ball.v))} uu/s</b></span><span>Slater controls: <b>${act.length?act.join(', '):'kickoff'}</b></span><span>Result: <b>${g.outcome===1?'WIN':g.outcome===-1?'LOSS':'NO GOAL'}</b></span>`;
}
function update(){let frame=Math.floor(cursor);document.getElementById('seek').value=frame;document.getElementById('clock').textContent=(frame*8/120).toFixed(2)+' s';document.getElementById('counter').textContent=frame+'/'+duration;GAMES.forEach((g,i)=>draw(g,P[i],frame))}
const seek=document.getElementById('seek');seek.max=duration;seek.addEventListener('input',()=>{cursor=+seek.value;playing=false;document.getElementById('play').textContent='▶ Play';update()});
document.getElementById('play').onclick=()=>{if(cursor>=duration)cursor=0;playing=!playing;document.getElementById('play').textContent=playing?'❚❚ Pause':'▶ Play';lastTime=performance.now()};
document.getElementById('speed').onchange=e=>{speed=+e.target.value};document.getElementById('trails').onchange=e=>{showTrails=e.target.checked;update()};
function tick(now){if(playing){cursor+=Math.min((now-lastTime)/1000,0.2)*15*speed;if(cursor>=duration){cursor=duration;playing=false;document.getElementById('play').textContent='▶ Play'}update()}lastTime=now;requestAnimationFrame(tick)}update();requestAnimationFrame(tick);
</script></body></html>'''


def make_html(records):
    raw=json.dumps(records,ensure_ascii=True,separators=(',',':')).replace('</','<\\/')
    return HTML_TEMPLATE.replace('__DATA__',raw)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',required=True,help='Existing v027 checkpoint under data/isolated')
    parser.add_argument('--side',choices=['blue','orange'],default='blue')
    parser.add_argument('--seed',type=int,default=1700420699)
    parser.add_argument('--max-episode-steps',type=int,default=450)
    parser.add_argument('--policy',choices=['both','original','candidate'],default='both')
    parser.add_argument('--viewer',choices=['html','rlviser'],default='html', help='rlviser is live 3D, one policy only')
    parser.add_argument('--speed',type=float,default=1.0,help='3D viewer play speed (0.25..4)')
    parser.add_argument('--out',default='data/isolated/slater_watch_v029_01.html')
    args=parser.parse_args()
    if not (1<=args.seed<2**31 and 1<=args.max_episode_steps<=1800 and 0.25<=args.speed<=4):
        parser.error('invalid seed/episode length/viewer speed')
    if args.viewer=='rlviser' and args.policy=='both':
        parser.error('RLViser live view can show one policy at once: --policy original or candidate')
    root=Path.cwd().resolve()
    out=checked_output(args.out,root) if args.viewer=='html' else None
    from slater_research.checkpoint import CYCLE9,CYCLE9_SHA,cycle9_pair
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    source=root/CYCLE9
    nexto_file=root/'vendor'/'nexto'/'nexto-model.pt'
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(nexto_file)!=NEXTO_SHA:
        raise RuntimeError('Frozen Cycle9 or Nexto source checksum mismatch')
    path=Path(args.checkpoint).resolve()
    isolated=(root/'data'/'isolated').resolve()
    if not path.is_relative_to(isolated) or path.suffix!='.pt' or not path.is_file():
        raise ValueError('Candidate must be an existing .pt file under data/isolated')
    # Only tensor/primitive checkpoint content, no arbitrary pickle execution.
    doc=torch.load(path,map_location='cpu',weights_only=True)
    if (not isinstance(doc,dict) or doc.get('stage')!='slater_v027' or doc.get('source_sha')!=CYCLE9_SHA or
        not isinstance(doc.get('actor'),dict) or doc.get('meta',{}).get('nexto_sha')!=NEXTO_SHA):
        raise ValueError('Checkpoint failed isolated v027/Cycle9/Nexto guards')
    student,original=cycle9_pair(root)
    student.load_state_dict(doc['actor'],strict=True)
    student.eval();original.eval()
    for p in list(student.parameters())+list(original.parameters()):p.requires_grad_(False)
    nexto=torch.jit.load(str(nexto_file),map_location='cpu')
    nexto.eval()
    for p in nexto.parameters():p.requires_grad_(False)
    lookup=nexto_actions()
    actions=np.stack([np.asarray(lookup[i],dtype=np.float32).reshape(8) for i in range(90)])
    torch.set_num_threads(2)
    if actions.shape!=(90,8) or not np.isfinite(actions).all():
        raise RuntimeError('Bad Nexto action table')
    actors={'original Cycle 9':original,'trained u'+str(doc['global_updates']):student}
    if args.policy=='original':actors={'original Cycle 9':original}
    if args.policy=='candidate':actors={'trained u'+str(doc['global_updates']):student}
    renderer=make_renderer() if args.viewer=='rlviser' else None
    records=[]
    print('WATCH_REAL_ROCKETSIM','viewer',args.viewer,'side',args.side,'seed',args.seed, 'models',list(actors),flush=True)
    try:
        for name, actor in actors.items():
            result=record_game(actor,nexto,actions,TeamObserver(),args.seed,args.side,args.max_episode_steps,renderer,args.speed)
            result['policy']=name
            records.append(result)
            print('MATCH',name,json.dumps({k:v for k,v in result.items() if k!='frames'},sort_keys=True),flush=True)
    finally:
        if renderer:renderer.close()
    if base.sha256(source)!=CYCLE9_SHA or base.sha256(nexto_file)!=NEXTO_SHA:
        raise RuntimeError('Frozen source changed; refusing to report')
    if out is not None:
        out.parent.mkdir(parents=True,exist_ok=True)
        with out.open('x',encoding='utf8') as f:f.write(make_html(records))
        print('OPEN_IN_BROWSER',out,'FRAMES',sum(len(x['frames']) for x in records),flush=True)
    print('NO_TRAINING_NO_PROMOTION_FROZEN_SOURCES_UNCHANGED',flush=True)

if __name__=='__main__':main()
