import importlib.util
from pathlib import Path
import tempfile,shutil,unittest,sys
HERE=Path(__file__).resolve().parents[1]
class TeacherWatchTests(unittest.TestCase):
 def test_cpp_has_actual_bridge_and_teacher_actions(self):
  t=(HERE/'HubWatchTeacher.cpp').read_text()
  for marker in ('GGL::FrozenNextoBridge teacherBridge(env)','teacherBridge.Infer(env.state',
                 'actionIDs.push_back(ti);','TEACHER_EPISODE','boostTicks','jumpTicks','teacherTouches',
                 'pybind11::scoped_interpreter pythonInterpreter'):
   self.assertIn(marker,t,marker)
 def test_python_selects_new_binary(self):
  s=(HERE/'watch_teacher_core.py').read_text()
  for marker in ('GigaLearnWatchTeacher.exe','GL_FROZEN_BRIDGE_DIR','GL_FROZEN_PYTHON_EXE',
                 'GL_FROZEN_NEXTO_PT','GL_FROZEN_WAVEDASH_PT','TEACHER_EPISODE'):
   self.assertIn(marker,s)
 def test_gui_supports_all_teachers(self):
  s=(HERE/'watch_teacher_gui.py').read_text()
  for m in ('frozen:nexto','frozen:cycle9','frozen:wavedash','tri_teacher_challenger_01'):
   self.assertIn(m,s)
 def test_installer_idempotent_and_separate_target(self):
  with tempfile.TemporaryDirectory() as td:
   td=Path(td)
   folder=td/'GigaLearn_Project/Research_Hub/Watch_GigaLearn'
   folder.mkdir(parents=True)
   shutil.copyfile(HERE/'install_teacher_watch.py',folder/'install_teacher_watch.py')
   shutil.copyfile(HERE/'HubWatchTeacher.cpp',folder/'HubWatchTeacher.cpp')
   upstream=td/'GigaLearn_Project/upstream'
   (upstream/'src').mkdir(parents=True)
   (upstream/'src/ExampleMain.cpp').write_text('// trainer placeholder',encoding='utf-8')
   original='set(FILES_SRC src/ExampleMain.cpp)\nadd_executable(GigaLearnBot ${FILES_SRC})\n'
   (upstream/'CMakeLists.txt').write_text(original,encoding='utf-8')
   spec=importlib.util.spec_from_file_location('installer_testing',folder/'install_teacher_watch.py')
   module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
   module.install()
   after=(upstream/'CMakeLists.txt').read_text()
   self.assertIn('add_executable(GigaLearnWatchTeacher',after)
   self.assertIn('list(FILTER FILES_SRC EXCLUDE REGEX',after)
   self.assertEqual((upstream/'CMakeLists.txt.before_frozen_teacher_watch_v1.bak').read_text(),original)
   module.install()
   self.assertEqual((upstream/'CMakeLists.txt').read_text(),after)
   self.assertEqual((upstream/'src/ExampleMain.cpp').read_text(),'// trainer placeholder')
 def test_doesnt_load_torch_into_cpp_process(self):
  s=(HERE/'HubWatchTeacher.cpp').read_text()
  self.assertNotIn('torch.jit.load',s)
  self.assertNotIn('torch.load(',s)
  self.assertIn('teacherBridge.Select',s)
if __name__=='__main__':unittest.main()
