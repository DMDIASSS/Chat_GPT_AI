import math
from pathlib import Path
import pytest

from slater_v039_throughput import (
    DECISIONS_PER_SIM_HOUR, MODES, estimates, safe_output, validate_options,
)


def test_time_conversion():
    assert DECISIONS_PER_SIM_HOUR == 54_000
    assert math.isclose(1_000_000 / DECISIONS_PER_SIM_HOUR, 18.5185185185)


def test_estimates_basic():
    x = estimates(10_000)
    assert len(x) == 4
    assert x[0]['simulated_agent_hours'] == 18.52
    assert x[3]['wallclock_hours_at_measured_rollout_rate'] == 27.78


@pytest.mark.parametrize('rate', [0, -1, float('inf'), float('nan')])
def test_bad_rates(rate):
    with pytest.raises(ValueError):
        estimates(rate)


def test_validate_good():
    validate_options(256, 16, 600, ('old_script', 'tick_stock'))


@pytest.mark.parametrize('modes', [(), ('old_script', 'old_script'), ('invalid',)])
def test_validate_bad_modes(modes):
    with pytest.raises(ValueError):
        validate_options(256, 16, 600, modes)


def test_validate_budget_bounds():
    with pytest.raises(ValueError): validate_options(0, 16, 600, ('old_script',))
    with pytest.raises(ValueError): validate_options(256, 300, 600, ('old_script',))
    with pytest.raises(ValueError): validate_options(256, 16, 12, ('old_script',))


def test_output_isolated(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    a = safe_output(root, 'data/isolated/v039_test01.json')
    assert a == (root / 'data/isolated/v039_test01.json').resolve()
    for name in ('../escape.json', 'data/other/x.json', 'data/isolated/out.pt'):
        with pytest.raises(ValueError):
            safe_output(root, name)
    a.parent.mkdir(parents=True)
    a.write_text('{}')
    with pytest.raises(FileExistsError):
        safe_output(root, 'data/isolated/v039_test01.json')
