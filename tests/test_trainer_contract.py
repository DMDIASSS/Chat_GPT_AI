"""Portable source/launcher contract tests. No RocketSim or weights required."""
from pathlib import Path
import ast
p = Path(__file__).resolve().parents[1]


def test_training_defaults_and_guards():
    s = (p/'mechanics_train.py').read_text(encoding='utf-8')
    assert 'best_10k.pt' in s
    assert "p.add_argument('--resume'" in s
    assert 'FileExistsError' in s
    assert 'load_actor' in s
    assert 'checkpoint.resolve() == source' in s


def test_all_scripts_compile():
    for f in p.glob('mechanics_*.py'):
        ast.parse(f.read_text(encoding='utf-8'))


def test_batch_doesnt_delete_user_checkpoints():
    for f in p.glob('*.bat'):
        contents=f.read_text(encoding='utf-8').lower()
        assert 'rmdir /s /q' not in contents
        assert 'del /f ' not in contents
