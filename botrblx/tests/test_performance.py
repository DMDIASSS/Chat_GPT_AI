"""Frame slicing, latency bounds and reversible rendering under synthetic APIs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
LUAU=os.environ.get('LUAU_BIN')or shutil.which('luau')


@unittest.skipUnless(LUAU,'Set LUAU_BIN to run frame-budget tests')
class PerformanceTests(unittest.TestCase):
    def run_lua(self,modules,body,mock=False):
        prefix=(ROOT/'tests/fixtures/roblox_mock.luau').read_text()if mock else ''
        source=prefix+'\n'
        for name,file in modules.items():
            source+='local '+name+'=(function()\n'+(ROOT/'templates'/file).read_text()+'\nend)()\n'
        with tempfile.TemporaryDirectory()as directory:
            p=Path(directory)/'performance.luau';p.write_text(source+body)
            r=subprocess.run([LUAU,str(p)],capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        return r.stdout

    def test_one_slice_per_frame_same_output_and_cancellation(self):
        self.run_lua({'Worker':'local_cooperative.lua'},'''
local time=0
local finished=0
local function predict(obs,context,checkpoint)
 local sum=0
 for i=1,100 do time+=.0004;sum+=i;checkpoint()end
 finished+=1
 return context.index,{sum}
end
local w=Worker.new(predict,function()return time end)
w:start({}, {index=7}, {epoch=1})
local result
for frame=1,100 do
 local before=time
 result=w:step(.0015)
 assert(time-before<.00191,'Blocked past one work unit over the frame budget')
 if result then break end
 time+=.005
end
assert(result and result.index==7 and result.logits[1]==5050)
assert(result.slices>20 and result.wall>result.cpu and finished==1)
w:start({}, {index=99}, {epoch=2});w:step(.0015);w:cancel()
assert(not w:step(.0015)and finished==1,'Cancelled work resumed')
w:start({}, {index=3}, {epoch=3})
repeat result=w:step(.0015)until result
assert(result.index==3 and finished==2,'Old output survived cancellation')
assert(w:report().cancelled==1)
''')

    def test_observation_preparation_is_in_the_same_budget_and_errors_clear_job(self):
        self.run_lua({'Worker':'local_cooperative.lua'},'''
local time=0
local w=Worker.new(function(q,c,checkpoint)return c.index,{q[1]}end,function()return time end)
w:start(function(checkpoint)
 for i=1,100 do time+=.0004;checkpoint()end
 return {42},{index=2}
end,nil,{})
local r
repeat local before=time;r=w:step(.001);assert(time-before<.00141)until r
assert(r.index==2 and r.logits[1]==42 and r.slices>25)
local broken=Worker.new(function(q,c,checkpoint)time+=.01;checkpoint();error('expected failure')end,function()return time end)
broken:start({}, {}, {});broken:step(.001)
assert(not pcall(function()broken:step(.001)end)and broken.job==nil)
''')

    def test_ping_and_jitter_do_not_double_extrapolate_predicted_game_state(self):
        self.run_lua({'Latency':'local_latency.lua'},'''
local ping=.05
local l=Latency.new({GetNetworkPing=function()return ping end})
l:sample(0,.01);assert(l.ping==.05)
local packet={sample_dt=.02}
local a=l:lead(packet,.04)
ping=.2;l:sample(.6,.01)
local b=l:lead(packet,.04)
assert(math.abs(a-b)<.003,'Added network ping to already-predicted positions')
l.input=.025;assert(math.abs(l:lead(packet,.04)-b-.025)<1e-6,'Ignored measured input-call delay')
assert(l:report().network_lead_ms==0 and l:report().ping_ms>50)
l.ping=.5;l.jitter=.1
assert(l:lead(packet,.4)<=.08,'Unbounded lookahead on a bad connection')
l.enabled=false;assert(l:lead(packet,1)==0)
assert(l:budget()>=.00075 and l:budget()<=.003)
''')

    def test_bounded_projection_is_immutable_and_stale_actions_are_rejected(self):
        self.run_lua({'Latency':'local_latency.lua'},'''
local p={team=0,scene_token='match-1',ground_estimate=false,sample_dt=.02,
 car={position={0,0,600},velocity={100,200,30},forward={1,0,0},up={0,0,1},angular_velocity={0,0,2}},
 ball={position={0,100,400},velocity={0,300,30},angular_velocity={0,0,0}},other_cars={}}
local l=Latency.new({})
local physics={gravity=-650,profile={physics={BALL_RADIUS=91.25}},predict=function(self,ball,r,h)
 return {{position={ball.position[1],ball.position[2]+ball.velocity[2]*h,ball.position[3]},velocity=table.clone(ball.velocity)}}
end}
local q=l:project(p,physics,.03)
assert(q~=p and q.car~=p.car and p.car.position[1]==0 and p.ball.position[2]==100)
assert(q.car.position[1]>0 and q.ball.position[2]>100)
local f,u=q.car.forward,q.car.up
assert(math.abs(f[1]*u[1]+f[2]*u[2]+f[3]*u[3])<1e-6)
local m={at=0,targetAt=0,epoch=2,team=0,scene='match-1',ground=false,car=p.car,ball=p.ball}
local job={metadata=m}
assert(l:fresh(job,p,.05,2))
assert(not l:fresh(job,p,.5,2),'Applied a stale inference')
assert(not l:fresh(job,p,.05,3),'Applied a previous run inference')
p.scene_token='match-2';assert(not l:fresh(job,p,.05,2),'Applied output across a respawn')
p=table.clone(p);p.scene_token='match-1';p.ball=table.clone(p.ball);p.ball.position={1500,100,400}
assert(not l:fresh(job,p,.05,2),'Accepted a large network correction')
''')

    def test_graphics_preserve_car_ball_pad_cues_and_restore_original_values(self):
        self.run_lua({'Graphics':'local_graphics.lua'},'''
Enum.Material={SmoothPlastic='plastic'}
workspace.DescendantAdded=event()
local lighting=object('Lighting','Lighting');lighting.Parent=workspace;lighting.GlobalShadows=true
lighting.DescendantAdded=event()
local bloom=object('PostEffect','Bloom');bloom.Parent=lighting;bloom.Enabled=true
local wall=object('Part','ArenaWall');wall.Parent=scene;wall.Material='stone';wall.Reflectance=.5;wall.CastShadow=true
local decal=object('Decal','WallTexture');decal.Parent=wall;decal.Transparency=.1
local trim=object('Part','Body');trim.Parent=car;trim.Material='paint';trim.CastShadow=true
local ring=object('Part','PadRing');ring.Parent=scene;ring.Material='neon';ring.Color={R=1,G=.8,B=.2};ring.CastShadow=true
local fx=object('ParticleEmitter','Dust');fx.Parent=scene;fx.Enabled=true;fx.Rate=50
local g=Graphics.new(workspace,lighting);g:setEnabled(true)
for i=1,50 do g:step(.001)end
assert(not lighting.GlobalShadows and not bloom.Enabled and not fx.Enabled and fx.Rate==0)
assert(wall.Material=='plastic'and decal.Transparency==1 and not wall.CastShadow)
assert(trim.Material=='paint'and ring.Material=='neon'and ring.Color.R==1,'Destroyed a gameplay cue')
local later=object('ParticleEmitter','NewEffect');later.Parent=scene;later.Enabled=true;later.Rate=30
workspace.DescendantAdded:Fire(later)
for i=1,5 do g:step(.001)end
assert(not later.Enabled and later.Rate==0,'Missed a streamed-in effect')
wall.Material='user-choice'
g:setEnabled(false)
assert(lighting.GlobalShadows and bloom.Enabled and fx.Enabled and fx.Rate==50 and later.Enabled and later.Rate==30)
assert(wall.Material=='user-choice'and wall.CastShadow and decal.Transparency==.1,'Bad restoration')
g:setEnabled(true);for i=1,50 do g:step(.001)end;g:close()
assert(wall.Material=='user-choice'and lighting.GlobalShadows and fx.Enabled)
assert(g:report().changed_properties==0)
''',mock=True)


if __name__=='__main__':unittest.main()
