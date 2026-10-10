import os,sys,unittest,tempfile,pathlib,struct,json,types
from unittest.mock import patch
import numpy as np
HERE=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import replay_export as replay
import tas_audit, curriculum_core as core, install_cpp

class Phys:
    def __init__(self,pos=(100,0,100)):
        self.position=np.array(pos,dtype=float)
        self.linear_velocity=np.array([200.,30.,0.])
        self.angular_velocity=np.zeros(3)
        self.rotation_mtx=np.eye(3)
class Car:
    def __init__(self,team):
        self.team_num=team
        self.physics=Phys((100.,team*900.-500.,100.))
        self.boost_amount=87.5
        self.on_ground=True
class State:
    def __init__(self):self.ball=Phys((0.,0.,104.));self.cars={0:Car(0),1:Car(1)}

class Tests(unittest.TestCase):
    def test_action_table(self):
        self.assertEqual(replay.ACTIONS.shape,(90,8))
        self.assertIsNone(replay.approx_index([1,2],True,True))
        self.assertEqual(replay.approx_index([1,0,0,0,0,0,1,0],True,True)[0],18)

    def test_replay_line_native_width(self):
        st=State()
        x=replay.one_line(3,0,11,st,0.4)
        self.assertEqual(len(x.split()),53)
        self.assertEqual(float(x.split()[13+18]),87.5)
        self.assertIsNone(replay.one_line(3,0,11,type('X',(),{'cars':{0:Car(0)},'ball':Phys()})(),0.4))

    def test_tas_audit_never_enables_unverified_training(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'test.data'
            p.write_bytes(struct.pack('<II',1,2)+struct.pack('<I7f',2,*([0.]*7))*2+b'\0'*128)
            info=tas_audit.audit_file(p)
            self.assertEqual(info['frames'],2)
            self.assertFalse(info['training_ready'])
            report=tas_audit.audit([p],pathlib.Path(d)/'result.json')
            self.assertFalse(report['tas_imitation_enabled'])
            with self.assertRaises(FileExistsError):tas_audit.audit([p],pathlib.Path(d)/'result.json')

    def test_all_unattended_stages_block(self):
        with self.assertRaises(core.GateError):core.can_run_all()
        self.assertTrue(any(s['name']=='Frozen Nexto/Cycle9/Wavedash' and s['status']=='blocked' for s in core.stage_states()))

    def test_build_install_idempotent_non_destructive(self):
        with tempfile.TemporaryDirectory() as d:
            source=pathlib.Path(d)/'GigaLearn_Project'
            upstream=source/'upstream';(upstream/'src').mkdir(parents=True)
            (upstream/'src/ExampleMain.cpp').write_text('int main() {}')
            original='file(GLOB_RECURSE FILES_SRC "src/*.cpp")\nadd_executable(GigaLearnBot ${FILES_SRC})\n'
            (upstream/'CMakeLists.txt').write_text(original)
            old=install_cpp.UPSTREAM
            try:
                install_cpp.UPSTREAM=upstream
                first=install_cpp.install()
                self.assertTrue(first['cmake_changed'])
                self.assertTrue((upstream/'src/HubReplayBC.cpp').is_file())
                self.assertEqual((upstream/'CMakeLists.txt.before_curriculum_bc.bak').read_text(),original)
                second=install_cpp.install()
                self.assertFalse(second['cmake_changed'])
                (upstream/'src/HubReplayBC.cpp').write_text('user custom content')
                with self.assertRaises(RuntimeError):install_cpp.install()
            finally:install_cpp.UPSTREAM=old

    def test_replay_export_mock_end_to_end_group_split(self):
        # Synthetic states, not real replays. Tests dataset formatting, source-split,
        # action table compatibility, progress limits, and collision handling.
        from unittest.mock import patch
        class Frame:
            def __init__(self):
                self.state=State()
                self.actions={0:np.array([1,0,0,0,0,0,1,0]),1:np.array([1,0,0,0,0,0,1,0])}
                self.update_age={0:0.,1:0.}
        class PR:
            @staticmethod
            def load(path):return path
        pkgs={
            'rlgym_tools':types.ModuleType('rlgym_tools'),
            'rlgym_tools.rocket_league':types.ModuleType('rlgym_tools.rocket_league'),
            'rlgym_tools.rocket_league.replays':types.ModuleType('rlgym_tools.rocket_league.replays'),
            'rlgym_tools.rocket_league.replays.parsed_replay':types.ModuleType('parsed_replay'),
            'rlgym_tools.rocket_league.replays.convert':types.ModuleType('convert'),
        }
        pkgs['rlgym_tools.rocket_league.replays.parsed_replay'].ParsedReplay=PR
        pkgs['rlgym_tools.rocket_league.replays.convert'].replay_to_rlgym=lambda path:[Frame() for _ in range(10)]
        with tempfile.TemporaryDirectory() as d:
            data=pathlib.Path(d)/'replays';data.mkdir()
            for i in range(30):(data/f'rank_{i:03d}.replay').write_bytes(b'mock'+str(i).encode())
            output=pathlib.Path(d)/'fresh_output'
            with patch.dict(sys.modules,pkgs):
                meta=replay.convert([data],output,every=1,max_per_replay=20)
            self.assertGreaterEqual(meta['train'],100)
            self.assertGreaterEqual(meta['val'],20)
            trainlines=(output/'replay_train.txt').read_text().splitlines()
            vallines=(output/'replay_val.txt').read_text().splitlines()
            self.assertEqual(trainlines[0],'GL_REPLAY_1')
            self.assertEqual(vallines[0],'GL_REPLAY_1')
            self.assertEqual(len(trainlines)-1,meta['train'])
            self.assertTrue(all(len(line.split())==53 for line in trainlines[1:]))
            trainids={int(float(line.split()[0])) for line in trainlines[1:]}
            validids={int(float(line.split()[0])) for line in vallines[1:]}
            self.assertFalse(trainids & validids)

    def test_duplicate_output_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            # no parser import needed: path collision checked before writing
            with self.assertRaises(FileExistsError):
                replay.convert([d],d)

if __name__=='__main__':unittest.main()
