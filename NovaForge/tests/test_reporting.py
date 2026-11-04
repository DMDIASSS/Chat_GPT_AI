import csv
import io
import json
from pathlib import Path
import zipfile

from nova.reporting import export_report, episode_summaries, safe_url, ppo_summaries, evaluation_summaries
from nova.training import archive_progress_csv


def sample(step,outcome=0):
    return dict(timesteps=step,outcome=outcome,timeout=outcome==0,practice_success=outcome==1,
        opponent='chronos',scenario='shot',side=0,touches=1,seconds=10,episode={'r':outcome},
        reward_parts={'goal':10*outcome},api_key='DO_NOT_EXPORT_THIS_SECRET')


def test_report_excludes_secrets_raw_logs_paths_and_weights(tmp_path,cfg):
    run=tmp_path/'runs'/'diverse01';run.mkdir(parents=True)
    secret='DO_NOT_EXPORT_THIS_SECRET'
    cfg['api_key']=secret;cfg['env']['replay_bank']='C:/Users/private-person/replays.npz'
    (run/'config.json').write_text(json.dumps(cfg))
    (run/'status.json').write_text(json.dumps(dict(state='training',timesteps=100,api_key=secret)))
    (run/'wandb_status.json').write_text(json.dumps(dict(mode='online',api_key=secret,
        url='https://wandb.ai/account/project/runs/abc123?api_key='+secret)))
    (run/'episodes.jsonl').write_text(''.join(json.dumps(sample(i,i%3-1))+'\n' for i in range(100)))
    (run/'debug.log').write_text(secret)
    (run/'checkpoints').mkdir()
    (run/'checkpoints'/'step_000000000100.zip').write_bytes(secret.encode())
    (run/'checkpoints'/'step_000000000100.zip.json').write_text(json.dumps(dict(timesteps=100,sha256='a'*64,api_key=secret)))
    out=export_report(run,tmp_path/'reports')
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert set(z.namelist())=={'report.json','progress.html','training_windows.csv',
                                 'opponent_comparisons.csv','ppo_metrics.csv','READ_ME.txt'}
        all_text=''.join(z.read(n).decode() for n in z.namelist())
        assert secret not in all_text and 'private-person' not in all_text
        report=json.loads(z.read('report.json'))
        assert report['status']['wandb_url']=='https://wandb.ai/account/project/runs/abc123'
        assert report['episodes']['total']['episodes']==100
        assert report['latest_checkpoint']['sha256']=='a'*64


def test_disjoint_early_late_windows_and_censored_timeouts(tmp_path):
    path=tmp_path/'episodes.jsonl'
    rows=[sample(i,-1 if i<75 else 1) for i in range(150)]
    rows[-1]=sample(149,0)
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows)+'{"partial":')
    result=episode_summaries(path,150)
    assert result['early']['episodes']==75 and result['late']['episodes']==75
    assert result['early']['score_fraction']==0
    assert result['late']['score_fraction']==74/75
    assert result['late']['timeout_fraction']==1/75
    assert result['notes']['partial_or_oversize_lines']==1
    assert result['matched_cells'][0]['late']['episodes']==75
    assert sum(r['episodes'] for r in result['windows'])==150


def test_resume_csv_history_is_preserved_and_exported(tmp_path):
    log=tmp_path/'logs';log.mkdir()
    (log/'progress.csv').write_text('time/total_timesteps,time/fps,train/approx_kl\n100,200,0.01\n')
    archive_progress_csv(tmp_path)
    assert not (log/'progress.csv').exists()
    assert len(list((log/'history').glob('*.csv')))==1
    (log/'progress.csv').write_text('time/total_timesteps,time/fps,train/approx_kl\n200,220,0.02\n')
    result=ppo_summaries(tmp_path)
    assert result['rows_read']==2 and result['notes']['csv_sessions']==2
    assert [p['timesteps'] for p in result['points']]==[100,200]
    assert result['recent_mean']['time/fps']==210


def test_report_links_reject_credential_urls():
    assert safe_url('https://token@wandb.ai/me/project/runs/abc') is None
    assert safe_url('https://other.example/secret') is None
    assert safe_url('https://wandb.ai/me/project/runs/abc#token')=='https://wandb.ai/me/project/runs/abc'


def test_coreweave_forge_dashboard_link_is_retained_without_secrets():
    url='https://forge.coreweave.com/wandb/me/project/runs/abc123'
    assert safe_url(url+'?api_key=DO_NOT_EXPORT#private')==url
    assert safe_url('https://token@forge.coreweave.com/wandb/me/project/runs/abc123') is None
    assert safe_url('https://forge.coreweave.com.evil.example/wandb/me/project/runs/abc123') is None
    assert safe_url('https://forge.coreweave.com/me/project/runs/abc123') is None


def test_evaluations_match_this_runs_checkpoints_and_keep_paired_evidence(tmp_path):
    def trial(outcome):
        return dict(sample(0,outcome),raw_path='C:/private/DO_NOT_EXPORT',seed=910001)
    evaluation=dict(kind='first_goal_trials',candidate_sha256='a'*64,baseline_sha256='b'*64,
        candidate='C:/private/student.zip',trials=[trial(1),trial(0)],
        baseline_trials=[trial(-1),trial(0)],summary={'trials':2,'first_goal_score_fraction':.5},
        baseline_summary={'trials':2,'first_goal_score_fraction':0},
        paired_mean_outcome_delta=1.,paired_delta_standard_error=1.)
    (tmp_path/'matching.json').write_text(json.dumps(evaluation))
    (tmp_path/'unrelated.json').write_text(json.dumps(dict(evaluation,candidate_sha256='c'*64)))
    result=evaluation_summaries(tmp_path,'a'*64,{'a'*64,'b'*64})
    assert len(result)==1 and result[0]['matches_latest_checkpoint']
    assert result[0]['baseline_sha256']=='b'*64
    assert [r['outcome'] for r in result[0]['baseline_trials']]==[-1,0]
    assert all(r['seed']==910001 for r in result[0]['trials'])
    assert result[0]['comparison']['paired_mean_outcome_delta']==1.
    assert 'private' not in json.dumps(result) and 'DO_NOT_EXPORT' not in json.dumps(result)
