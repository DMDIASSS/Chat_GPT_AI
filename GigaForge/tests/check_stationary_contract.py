"""Native objective contract and actual all-player reward cancellation regression."""
from pathlib import Path
import importlib.util, json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('stationary_native_runner',ROOT/'run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for flag in ('--stationary-contract','--stationary-selftest'):
 result=subprocess.run([str(m.binary()),flag],env=m.environment(),capture_output=True,text=True,check=True)
 row=json.loads(result.stdout.strip())
 if flag=='--stationary-contract':
  assert row['version']=='stationary-pilot-v1' and row['temperature_consistent']
  assert row['objectives']==['goal_only','goal_potential']
 else:
  assert row['stationary_goal_signs_pass'] and row['legacy_counter_cancellation_reproduced']
  assert row['legacy_test_blue_goals']==100 and row['legacy_reported_win_rate']==.5
  assert row['legacy_training_rejected']
 print(flag,json.dumps(row),flush=True)
print('NATIVE_STATIONARY_OBJECTIVE_CONTRACT_PASS',flush=True)
