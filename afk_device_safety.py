"""Conservative device selection for native Nexto TorchScript policies.

The original traced ControlsPredictorDot has a fixed torch.device('cpu')
constant for the action lookup. Moving the policy weights to CUDA leads to a
CPU/CUDA matmul mismatch. No silent GPU promises: fall back to CPU until a
compatible model has been exported and parity-tested.
"""
from __future__ import annotations
from pathlib import Path


def hardcoded_cpu_ops(scripted_model) -> list[str]:
    """Identify embedded CPU device constants anywhere in a JIT actor tree."""
    found=[]
    for name, sub in scripted_model.named_modules():
        try:
            code = str(sub.code)
        except (AttributeError, RuntimeError):
            continue
        if 'device=torch.device("cpu")' in code or "device=torch.device('cpu')" in code:
            found.append(name or '<root>')
    return found


def check_cpu_policy(source_model: Path) -> str:
    """Real no-simulator inference smoke-test of bundled policy contract."""
    import torch
    actor=torch.jit.load(str(source_model),map_location='cpu').eval()
    with torch.inference_mode():
        logits, _ = actor((torch.zeros(1,1,32),torch.zeros(1,37,24),torch.zeros(1,37)))
    if logits.shape != (1,90) or not torch.isfinite(logits).all():
        raise RuntimeError(f'Policy shape/finite check failed: {tuple(logits.shape)}')
    return 'Native policy CPU forward-check OK: logits [1,90] finite.'


def choose_device(requested: str, source_model: Path) -> tuple[str,str]:
    if requested == 'cpu':
        return 'cpu', 'Using CPU for native Nexto TorchScript training.'
    if requested != 'cuda:0':
        raise ValueError(f'Invalid device {requested!r}; expected cpu or cuda:0')
    import torch
    if not torch.cuda.is_available():
        return 'cpu', 'CUDA requested but CUDA-enabled PyTorch/NVIDIA device unavailable. Safe fallback to CPU.'
    actor = torch.jit.load(str(source_model), map_location='cpu').eval()
    forced = hardcoded_cpu_ops(actor)
    if forced:
        return 'cpu', ('CUDA requested but the pretrained Nexto TorchScript has fixed CPU tensors '
                       f'in {", ".join(forced[:3])}; CUDA would crash. SAFE FALLBACK to CPU. '
                       'A GPU-compatible actor conversion plus output parity test is required.')
    # If a later policy removes these constants, run a real forward sanity-check.
    # The model's intended observation shapes are Bx1x32, Bx37x24, Bx37.
    try:
        gpu = actor.to('cuda:0')
        q = torch.zeros(1,1,32, device='cuda:0')
        kv = torch.zeros(1,37,24, device='cuda:0')
        mask = torch.zeros(1,37, device='cuda:0')
        with torch.inference_mode(): out,_ = gpu((q,kv,mask))
        if out.shape != (1,90) or not torch.isfinite(out).all():
            raise RuntimeError('invalid actor output')
    except (RuntimeError,ValueError) as exc:
        return 'cpu', f'CUDA actor forward-check failed ({str(exc)[:180]}). SAFE FALLBACK to CPU.'
    finally:
        # Allow CUDA memory to be freed before full training begins.
        del actor
    return 'cuda:0', 'CUDA native actor forward-check passed (experimental).'
