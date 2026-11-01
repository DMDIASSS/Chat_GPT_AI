import json
from pathlib import Path
import csv

import compare_u271_checkpoints as comparison
import slater_model_selection as selector

ROOT=Path(__file__).resolve().parents[1]

def test_exact_ranges_all_models_formats_sides_and_whole_candidate_team():
    cfg=selector.validate_config(selector.merge_config(selector.DEFAULT,json.loads(comparison.CONFIG.read_text())))
    paths=comparison.expected_paths()
    assert len(paths)==len(set(paths))==566
    assert set(p for group in cfg['families'].values() for p in group)==set(paths)
    for cycle,group in enumerate(cfg['families'].values(),1):
        assert len(group)==(81 if cycle<=2 else 101)
        assert group[0].endswith('checkpoint_000000/actor.pt')
        assert group[-1].endswith(f'checkpoint_{80 if cycle<=2 else 100:06d}/actor.pt')
    inventory={'roles':{'baseline':'candidate0','rival:nexto':'nexto'}}
    protocol={'settings':cfg,'protocol_sha':'test','identity':{'native':{'binary_sha256':'test'}}}
    jobs=selector.expected_jobs(protocol,inventory,[f'candidate{i}' for i in range(566)],'screen')
    assert len(jobs)==566*3*2*2
    assert {tuple(j['format']) for j in jobs}=={(1,1),(2,2),(3,3)}
    assert all(j['reference_id']==j['candidate_id'] and j['team_policy']=='candidate_squad' for j in jobs)
    assert all(j['rival_id']=='nexto' and j['seconds']==30 for j in jobs)
    assert cfg['goal_race'] is None
    studio=json.loads((ROOT/'STUDIO_C0001_C0006_NEXTO_ALL.json').read_text())
    assert studio['selector']==json.loads(comparison.CONFIG.read_text())
    assert studio['max_games']>=len(jobs) and studio['until']=='screen'

def test_audit_reports_missing_and_csv_preserves_aliases_and_mode_results(tmp_path):
    report=comparison.audit(tmp_path)
    assert report['expected']==566 and report['present']==0 and len(report['missing'])==566
    cfg=selector.validate_config(selector.merge_config(selector.DEFAULT,json.loads(comparison.CONFIG.read_text())))
    protocol={'settings':cfg,'protocol_sha':'test','identity':{'native':{'binary_sha256':'test'}}}
    jobs=selector.expected_jobs(protocol,{'roles':{'baseline':'model','rival:nexto':'nexto'}},['model'],'screen')
    sources=[{'path':p,'families':['test']} for p in comparison.expected_paths()[:2]]
    selector.atomic_json(tmp_path/'inventory.json',{'models':{'model':{'source_paths':sources}}})
    selector.atomic_json(tmp_path/'stages/screen/plan.json',{'jobs':jobs})
    for job in jobs:
        selector.atomic_json(tmp_path/'cache/records'/(job['id']+'.json'),dict(job,finish='COMPLETE',goals_for=2,goals_against=1))
    path=comparison.export_csv(tmp_path)
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    assert len(rows)==6 and {r['format'] for r in rows}=={'1v1','2v2','3v3'}
    assert all(r['complete']=='True' and r['wins']=='4' and r['goals_for']=='8' for r in rows)
