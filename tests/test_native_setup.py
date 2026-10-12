from pathlib import Path
import importlib.util
import pytest


def load():
    path=Path(__file__).resolve().parents[1]/'GigaLearn_Project/Native_Backend/native_setup.py'
    spec=importlib.util.spec_from_file_location('native_setup_test',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_zero_exit_without_completion_is_not_success():
    m=load()
    with pytest.raises(ValueError):m.parse_log('RG FATAL ERROR: failed')
    with pytest.raises(ValueError):m.parse_log('Collection Steps/Second: 100\nOverall Steps/Second: 50\n')


def test_warm_throughput_parser_counts_agent_decisions():
    m=load();text='Collection Steps/Second: 1,000\nOverall Steps/Second: 500\nCollection Steps/Second: 2,000\nOverall Steps/Second: 800\nSLATER_GIGA_COMPLETE iterations=2 timesteps=4096'
    r=m.parse_log(text)
    assert r['Collection Steps/Second']['warm_median']==2000
    assert r['total_timesteps']==4096 and r['total_iterations']==2


def test_python_headers_and_tools_are_real():
    m=load();library,include=m.python_paths()
    assert library.is_file() and (include/'Python.h').is_file()
    assert Path(m.tool('cmake')).is_file()
