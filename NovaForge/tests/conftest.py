import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def pytest_addoption(parser):
    parser.addoption('--chronos',action='store_true',help='Exercise actual Chronos initialization and native trajectory parity')
    parser.addoption('--teachers',action='store_true',help='Exercise downloaded actual Nexto/Ripple models')
    parser.addoption('--viewer-udp',action='store_true',help='Opt in to the native RLViser UDP integration check; stop all viewers/senders first')


@pytest.fixture
def cfg():
    from nova.training import load_config
    c=load_config()
    c['workers']=1
    c['env'].update(episode_seconds=.15,no_touch_seconds=1)
    return c
