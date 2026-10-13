from copy import deepcopy
from pathlib import Path
import json

import pytest

import slater_champion_campaign as campaign


def configuration():
    return {'cycles': 2, 'routines': ['match', 'wall-reset'], 'chunk_updates': 2,
            'branch_updates': 4, 'screen_every': 1, 'plateau_chunks': 2,
            'screen_seeds': 1, 'confirm_seeds': 8, 'screen_seconds': 1.,
            'confirm_seconds': 1., 'formats': ['1v1', '2v2'],
            'mode_weights': {'1v1': .5, '2v2': .5}, 'min_disk_gb': 0.,
            'native_profile': {'device': 'cpu', 'games': 2, 'steps': 16},
            'job_group': 3}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    root = tmp_path / 'campaigns'
    branch_root = tmp_path / 'native'
    source = tmp_path / 'source.pt'; source.write_bytes(b'initial')
    rival = tmp_path / 'rival.pt'; rival.write_bytes(b'rival')
    monkeypatch.setattr(campaign, 'BASE', root)
    monkeypatch.setattr(campaign.native, 'run_path', lambda name: branch_root / name)
    monkeypatch.setattr(campaign, 'campaign_identity', lambda build=None: {
        'native': {'binary_sha256': 'fixture'}, 'runtime': {'fixture': True}, 'code': {}})

    def portable(path, run, inventory):
        path = Path(path).resolve()
        digest = campaign.sha256(path); id = 'a_' + digest
        actor = run / 'actors' / (digest + '.pt')
        actor.parent.mkdir(parents=True, exist_ok=True)
        if not actor.exists():
            actor.write_bytes(path.read_bytes())
        entry = {'path': str(path), 'sha256': digest, 'families': ['campaign'], 'roles': []}
        model = inventory['models'].setdefault(id, {
            'id': id, 'actor_path': str(actor), 'exported_sha256': digest,
            'actor_weights_sha256': digest, 'source_paths': [], 'families': ['campaign'], 'roles': []})
        if entry not in model['source_paths']:
            model['source_paths'].append(entry)
        campaign.atomic_json(run / 'inventory.json', inventory)
        return id

    monkeypatch.setattr(campaign, 'portable_model', portable)
    calls = {'train': [], 'eval': [], 'pause_training': False,
             'pause_evaluation': False, 'strength': 1, 'confirmation_strength': None,
             'strength_by_update': None}

    def init(name, source, teacher=None, rival=None, profile=None, build_dir=None):
        folder = branch_root / name; folder.mkdir(parents=True)
        folder.joinpath('initial_actor.pt').write_bytes(Path(source).read_bytes())
        protocol = {'profile': profile, 'playing_model': str(source)}
        campaign.atomic_json(folder / 'protocol.json', protocol)
        return folder, protocol

    def check(name, build=None):
        folder = branch_root / name
        return folder, campaign.read_json(folder / 'protocol.json')

    def command(mode, run, profile, build_dir=None, checkpoint=None, updates=0):
        return ['fixture', '--out', run, '--pause', Path(run) / 'PAUSE', '--updates', updates]

    def checkpoint(folder, update, contents):
        saved = folder / 'checkpoints' / f'checkpoint_{update:06d}'
        saved.mkdir(parents=True, exist_ok=True)
        for name in campaign.native.CHECKPOINT_FILES:
            saved.joinpath(name).write_bytes(contents if name == 'actor.pt' else b'fixture')
        saved.joinpath('COMPLETE').write_text('complete')
        return saved

    def process(command, logfile, marker=None, pause=None):
        folder = Path(command[command.index('--out') + 1])
        budget = command[command.index('--updates') + 1]
        calls['train'].append((folder.name, budget))
        try:
            start = campaign.checkpoint_count(campaign.native.latest_checkpoint(folder))
        except ValueError:
            start = 0
            checkpoint(folder, 0, folder.joinpath('initial_actor.pt').read_bytes())
        count = 1 if calls['pause_training'] else budget
        for update in range(start + 1, start + count + 1):
            checkpoint(folder, update, folder.name.encode() + b':' + str(update).encode())
        if calls['pause_training']:
            Path(pause).touch(); calls['pause_training'] = False
        return {'status': 'PAUSED' if Path(pause).exists() else 'FINITE_TRAINING_COMPLETE',
                'updates': start + count}

    def evaluate(run, protocol, inventory, stage, jobs, build_dir=None):
        parent = inventory['roles']['baseline']
        calls['eval'].append({'stage': stage, 'jobs': deepcopy(jobs)})
        for index, job in enumerate(jobs):
            strength = calls['strength']
            if calls['strength_by_update'] and job['candidate_id'] != parent:
                source_name = Path(inventory['models'][job['candidate_id']]['source_paths'][0]['path']).parent.name
                update = int(source_name.removeprefix('checkpoint_'))
                strength = calls['strength_by_update'][update]
            if stage.endswith('_confirm') and calls['confirmation_strength'] is not None:
                strength = calls['confirmation_strength']
            score = 0 if job['candidate_id'] == parent else strength
            record = {**job, 'goals_for': max(0, score), 'goals_against': max(0, -score),
                      'finish': 'COMPLETE'}
            campaign.atomic_json(run / 'cache/records' / (job['id'] + '.json'), record)
            if calls['pause_evaluation']:
                (run / 'PAUSE').touch(); calls['pause_evaluation'] = False
                break
        return {'status': 'COMPLETE'}

    monkeypatch.setattr(campaign.native, 'initialize_run', init)
    monkeypatch.setattr(campaign.native, 'check_run', check)
    monkeypatch.setattr(campaign.native, 'native_command', command)
    monkeypatch.setattr(campaign.native, 'checked_process', process)
    monkeypatch.setattr(campaign.native, 'verify_protected', lambda protocol: None)
    monkeypatch.setattr(campaign.selector, 'execute_group', evaluate)
    cfg = configuration(); cfg['rivals'] = {'fixture': str(rival)}
    return {'source': source, 'rival': rival, 'config': cfg, 'calls': calls,
            'root': root, 'branches': branch_root}


def test_configuration_rejects_unbounded_runs_bad_weights_and_unknown_routines():
    with pytest.raises(ValueError, match='cycles=0'):
        campaign.validate_config({'cycles': 0})
    with pytest.raises(ValueError, match='implemented'):
        campaign.validate_config({'routines': ['imaginary-air-reset-network']})
    with pytest.raises(ValueError, match='Mode weights'):
        campaign.validate_config({'mode_weights': {'1v1': 0, '2v2': .5, '3v3': .5}})
    with pytest.raises(ValueError, match='Unknown champion'):
        campaign.validate_config({'unknown': True})
    with pytest.raises(ValueError, match='ASCII'):
        campaign.run_path('../unsafe')
    assert campaign.validate_config({'cycles': 0, 'max_minutes': 10})['cycles'] == 0


def test_fresh_confirmation_namespaces_never_overlap_and_spending_is_bounded():
    cfg = campaign.validate_config(configuration())
    seen = set()
    alphas = []
    for cycle in range(1, 1000):
        for stage in ('screen', 'confirm'):
            seeds = set(campaign.seed_namespace(cfg, cycle, stage))
            assert not seen & seeds
            seen |= seeds
        alphas.append(cfg['promotion_alpha'] / (cycle * (cycle + 1)))
    assert sum(alphas) < cfg['promotion_alpha']


def test_finite_campaign_promotes_confirmed_children_and_branches_from_champion(harness):
    h = harness
    before = campaign.sha256(h['source'])
    result = campaign.run_campaign('finite', source=h['source'], config=h['config'])
    assert result['status'] == 'FINITE_CAMPAIGN_COMPLETE'
    assert result['promotions'] == 2
    assert result['cycle'] == 2 and result['active'] is None
    assert result['branches'][1]['parent_id'] == result['branches'][0]['champion_after']
    assert result['branches'][0]['routine'] == 'match'
    assert result['branches'][1]['routine'] == 'wall-reset'
    assert before == campaign.sha256(h['source'])
    assert len(list(h['branches'].glob('*/checkpoints/checkpoint_*'))) == 10
    selected = campaign.status('finite')['selected']
    assert selected['playing_model'] == str(h['source'])
    assert selected['playing_model_unchanged'] and not selected['confirmed_best']


def test_parent_wins_ties_and_rotates_routine_without_destroying_checkpoints(harness):
    h = harness; h['calls']['strength'] = 0
    result = campaign.run_campaign('ties', source=h['source'], config=h['config'])
    assert result['promotions'] == 0
    assert result['champion_id'] == result['branches'][0]['parent_id']
    assert all(branch['result'] == 'PARENT_RETAINED' for branch in result['branches'])
    assert all(branch['best_id'] == branch['parent_id'] for branch in result['branches'])
    assert not any(call['stage'].endswith('_confirm') for call in h['calls']['eval'])
    assert len(list(h['branches'].glob('*/checkpoints/checkpoint_*'))) == 10


def test_promising_screen_cannot_promote_a_failed_fresh_confirmation(harness):
    h = harness; h['config']['cycles'] = 1
    h['calls']['confirmation_strength'] = -1
    result = campaign.run_campaign('failed_confirmation', source=h['source'], config=h['config'])
    assert result['promotions'] == 0
    assert result['branches'][0]['result'] == 'INCONCLUSIVE_OR_NO_IMPROVEMENT'
    assert result['branches'][0]['best_id'] != result['champion_id']
    assert any(call['stage'].endswith('_confirm') for call in h['calls']['eval'])


def test_regressing_branches_stop_before_their_large_budget_and_rotate(harness):
    h = harness; h['calls']['strength'] = -1
    h['config']['branch_updates'] = 50
    result = campaign.run_campaign('regression', source=h['source'], config=h['config'])
    assert result['promotions'] == 0 and result['train_updates'] == 8
    assert all(branch['updates'] == 4 for branch in result['branches'])
    assert all(branch['stop_reason'] == 'REGRESSING_BRANCH' for branch in result['branches'])
    assert [branch['routine'] for branch in result['branches']] == ['match', 'wall-reset']


def test_early_good_checkpoint_cannot_hide_collapse_of_latest_checkpoint(harness):
    h = harness; h['config']['cycles'] = 1; h['config']['branch_updates'] = 50
    h['calls']['strength_by_update'] = {1: 2, 2: -3, 3: -3, 4: -3}
    result = campaign.run_campaign('late_collapse', source=h['source'], config=h['config'])
    branch = result['branches'][0]
    assert branch['updates'] == 4 and branch['stop_reason'] == 'REGRESSING_BRANCH'
    assert branch['latest_mean'] < 0 and branch['best_mean'] > 0
    assert branch['best_id'] != branch['latest_id']
    assert branch['promotion']['promote']  # The useful earlier checkpoint remains eligible.


def test_training_pause_resume_consumes_remaining_chunk_not_a_fresh_budget(harness):
    h = harness; h['config']['cycles'] = 1; h['calls']['pause_training'] = True
    paused = campaign.run_campaign('pause_train', source=h['source'], config=h['config'])
    assert paused['status'] == 'PAUSED' and paused['active']['updates'] == 1
    assert paused['active']['chunk_target'] == 2
    resumed = campaign.run_campaign('pause_train', resume=True)
    assert resumed['status'] == 'FINITE_CAMPAIGN_COMPLETE'
    assert h['calls']['train'][0][1] == 2 and h['calls']['train'][1][1] == 1
    assert resumed['train_updates'] == 4


def test_evaluation_pause_resumes_cached_games_without_replaying_them(harness):
    h = harness; h['config']['cycles'] = 1; h['calls']['pause_evaluation'] = True
    paused = campaign.run_campaign('pause_eval', source=h['source'], config=h['config'])
    assert paused['status'] == 'PAUSED' and paused['phase'] == 'screen'
    first = h['calls']['eval'][0]['jobs'][0]['id']
    before = campaign.sha256(h['root'] / 'pause_eval/cache/records' / (first + '.json'))
    campaign.run_campaign('pause_eval', resume=True)
    assert before == campaign.sha256(h['root'] / 'pause_eval/cache/records' / (first + '.json'))
    assert not any(job['id'] == first for call in h['calls']['eval'][1:] for job in call['jobs'])


def test_resume_rejects_source_or_runtime_changes_and_keeps_folders(harness, monkeypatch):
    h = harness; h['calls']['pause_training'] = True
    campaign.run_campaign('protected', source=h['source'], config=h['config'])
    h['source'].write_bytes(b'changed')
    with pytest.raises(ValueError, match='Protected campaign input changed'):
        campaign.run_campaign('protected', resume=True)
    assert (h['root'] / 'protected/progress.json').is_file()
    h['source'].write_bytes(b'initial')
    monkeypatch.setattr(campaign, 'campaign_identity', lambda build=None: {'new': 'runtime'})
    with pytest.raises(ValueError, match='code, binary or runtime'):
        campaign.run_campaign('protected', resume=True)


def test_resume_rejects_changed_config_and_protocol(harness):
    h = harness; h['calls']['pause_training'] = True
    campaign.run_campaign('pins', source=h['source'], config=h['config'])
    with pytest.raises(ValueError, match='changed|change'):
        campaign.run_campaign('pins', resume=True, config={**h['config'], 'chunk_updates': 3})
    path = h['root'] / 'pins/protocol.json'
    protocol = campaign.read_json(path); protocol['playing_model'] = 'forged'
    campaign.atomic_json(path, protocol)
    with pytest.raises(ValueError, match='protocol changed'):
        campaign.run_campaign('pins', resume=True)


def test_resume_rejects_modified_private_portable_actor(harness):
    h = harness; h['calls']['pause_training'] = True
    campaign.run_campaign('actor_pin', source=h['source'], config=h['config'])
    selected = campaign.status('actor_pin')['selected']
    Path(selected['actor_path']).write_bytes(b'replaced-weights')
    with pytest.raises(ValueError, match='Private campaign actor changed'):
        campaign.run_campaign('actor_pin', resume=True)


def test_selection_is_snapshotted_and_a_later_origin_report_does_not_change_the_campaign(harness, monkeypatch):
    h = harness; h['calls']['pause_training'] = True
    report = h['root'].parent / 'selection.json'
    report.write_text(json.dumps({'checkpoint': str(h['source'])}))
    monkeypatch.setattr(campaign.native, 'source_from_selection', lambda path: (h['source'], {
        'path': str(report), 'sha256': campaign.sha256(report), 'playing_model': str(h['source']),
        'source_paths': [{'path': str(h['source']), 'sha256': campaign.sha256(h['source'])}],
        'status': 'EXPLORATORY', 'model_id': 'fixture'}))
    campaign.run_campaign('selection_copy', selection=report, config=h['config'])
    saved = h['root'] / 'selection_copy/source_selection.json'
    before = campaign.sha256(saved)
    report.write_text(json.dumps({'checkpoint': 'a newer independent selector result'}))
    result = campaign.run_campaign('selection_copy', resume=True)
    assert result['status'] == 'FINITE_CAMPAIGN_COMPLETE'
    assert campaign.sha256(saved) == before
    protocol = campaign.read_json(h['root'] / 'selection_copy/protocol.json')
    assert protocol['source_selection']['origin_path'] == str(report)
    assert protocol['source_selection']['path'] == str(saved)


def test_fewer_than_eight_clusters_stays_inconclusive(harness):
    h = harness; h['config']['cycles'] = 1; h['config']['confirm_seeds'] = 2
    result = campaign.run_campaign('tiny_confirmation', source=h['source'], config=h['config'])
    assert result['promotions'] == 0
    assert result['branches'][0]['result'] == 'INSUFFICIENT_INDEPENDENT_SEEDS'


def test_key_mode_regression_blocks_an_overall_positive_policy():
    cfg = campaign.validate_config(configuration())
    row = {'id': 'child', 'weighted_goal_difference_per_minute':
           {'mean': 1., 'lower': .2, 'upper': 2., 'independent_seeds': 8},
           'per_mode': {'1v1': {'lower': 2.}, '2v2': {'lower': -.6}}}
    decision = campaign.promotion_decision([row], 'parent', cfg, 1)
    assert not decision['promote']
    assert decision['reason'] == 'MODE_REGRESSION_OR_UNCERTAINTY'
    assert decision['modes'] == ['2v2']


def test_mode_weights_change_ranking_and_parent_wins_equal_scores():
    cfg = campaign.validate_config(configuration())
    records = []
    for candidate in ('parent', 'duelist', 'teamplayer'):
        for fmt in cfg['formats']:
            for seed in (1, 2):
                for side in ('blue', 'orange'):
                    score = 0 if candidate == 'parent' else 2 if (
                        candidate == 'duelist' and fmt == [1, 1] or
                        candidate == 'teamplayer' and fmt == [2, 2]) else -1
                    records.append({'candidate_id': candidate, 'rival_id': 'rival',
                                    'format': fmt, 'seed': seed, 'learner_team': side, 'seconds': 60.,
                                    'team_policy': 'candidate_squad', 'goals_for': max(score, 0),
                                    'goals_against': max(-score, 0)})
    cfg['mode_weights'] = {'1v1': .9, '2v2': .1}
    assert campaign.weighted_ranking(records, ('parent', 'duelist', 'teamplayer'), 'parent', cfg)[0]['id'] == 'duelist'
    cfg['mode_weights'] = {'1v1': .1, '2v2': .9}
    assert campaign.weighted_ranking(records, ('parent', 'duelist', 'teamplayer'), 'parent', cfg)[0]['id'] == 'teamplayer'


def test_routine_queue_overrides_a_legacy_wall_curriculum_base_profile():
    cfg = campaign.validate_config({**configuration(), 'native_profile': {
        'device': 'cpu', 'games': 2, 'steps': 16, 'curriculum': 'wall-reset'}})
    profile = campaign.branch_profile(cfg, 'match', 1)
    assert profile['curriculum'] == 'none'
    if 'routine' in profile:
        assert profile['routine'] == 'match'


def test_branch_training_seed_remains_valid_at_the_configured_integer_boundary():
    cfg = campaign.validate_config({**configuration(), 'native_profile': {
        'device': 'cpu', 'games': 2, 'steps': 16, 'seed': 2**31 - 1}})
    profile = campaign.branch_profile(cfg, 'match', 1)
    assert 1 <= profile['seed'] <= 2**31 - 1
    assert profile['seed'] != cfg['native_profile']['seed']


def test_request_pause_and_status_are_read_only_except_pause_file(harness):
    h = harness; h['calls']['pause_training'] = True
    campaign.run_campaign('ui', source=h['source'], config=h['config'])
    assert campaign.request_pause('ui')['status'] == 'PAUSE_REQUESTED'
    result = campaign.status('ui')
    assert result['progress']['status'] == 'PAUSED'
    assert Path(result['shortlist']).is_file()
    with pytest.raises(ValueError, match='No champion campaign'):
        campaign.request_pause('missing')


def test_explicit_source_required_and_existing_runs_are_preserved(harness):
    h = harness
    with pytest.raises(ValueError, match='exactly one'):
        campaign.run_campaign('required', config=h['config'])
    campaign.run_campaign('exists', source=h['source'], config={**h['config'], 'cycles': 1})
    before = campaign.sha256(h['root'] / 'exists/protocol.json')
    with pytest.raises(FileExistsError, match='exists'):
        campaign.run_campaign('exists', source=h['source'], config=h['config'])
    assert before == campaign.sha256(h['root'] / 'exists/protocol.json')
