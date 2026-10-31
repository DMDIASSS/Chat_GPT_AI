"""Cross-process forecast parity, lifecycle and partial-pipe reliability."""
import io
import struct
import numpy as np
import pytest
from replay_il_pipe import read_frame,write_frame,LIMIT
from replay_il_processes import ForecastProcesses
from test_replay_runtime import model_book,state_fixture


def test_private_frames_handle_partial_reads_writes_and_reject_corruption():
    class PartialIO(io.BytesIO):
        def write(self,data):return super().write(data[:7])
        def read(self,count=-1):return super().read(min(count,5))
    channel=PartialIO();payload={'name':'тест','array':np.arange(300,dtype=np.float32)}
    write_frame(channel,payload);channel.seek(0);received=read_frame(channel)
    assert received['name']==payload['name'];np.testing.assert_array_equal(received['array'],payload['array'])
    for size in (0,LIMIT+1):
        with pytest.raises(ValueError,match='frame size'):read_frame(io.BytesIO(struct.pack('<I',size)))
    with pytest.raises(EOFError):read_frame(io.BytesIO(b'\x01\x00'))


def test_workers_do_not_load_torch_and_close_after_a_child_failure(model_book):
    _,book=model_book;pool=ForecastProcesses(book,2)
    processes=list(pool.processes)
    try:
        assert all(not info['torch_loaded'] for info in pool.worker_info)
        processes[0].kill();processes[0].wait(timeout=3)
        state=state_fixture();ours=next(iter(state.cars))
        with pytest.raises(RuntimeError,match='worker failed'):
            pool.prepare(state,{},ours,[0,1],1)
        assert pool.closed and all(process.poll() is not None for process in processes)
    finally:pool.close()
    pool.close() # Cleanup is idempotent after a failed request.


def test_compact_and_multicore_benchmark_compare_same_network_and_keep_training_files(tmp_path,model_book):
    import torch
    from pathlib import Path
    from replay_il_native_runtime import benchmark
    from slater_v041_core import atomic_json,sha256
    model,book=model_book
    torch.save({'config':model.config,'model':model.state_dict()},tmp_path/'best.pt')
    np.save(tmp_path/'tokens.npy',book)
    atomic_json(tmp_path/'selected.json',{'sha256':sha256(tmp_path/'best.pt')})
    atomic_json(tmp_path/'tokenizer.json',{'book_sha256':sha256(tmp_path/'tokens.npy')})
    root=Path(__file__).resolve().parents[1]
    paths=list((root/'replay_il').glob('*.py'))+list(tmp_path.iterdir());before={path:sha256(path) for path in paths}
    report=benchmark(tmp_path,device='cpu',network='frozen',stepping='processes',workers=2,
        candidate_counts=[2],repeats=2,warmups=1,compare_reference=False,compare_compact=True)
    assert report['validation_status']=='passed'
    assert {row['backend'] for row in report['results']}=={'policy','native-compact-frozen','native-processes-frozen'}
    comparison=report['comparisons'][0]
    assert comparison['reference_backend']=='native-compact-frozen' and comparison['status']=='passed'
    assert comparison['parity']['same_selected_token'] and comparison['parity']['same_candidate_set']
    result=next(row for row in report['results'] if row['backend']=='native-processes-frozen')
    assert result['workers']==2 and result['worker_torch_loaded']==[False,False]
    assert result['execute_first_ticks']==8 and result['horizon_seconds']==1
    assert len(result['latency_samples_ms'])==2
    assert {path:sha256(path) for path in paths}==before
