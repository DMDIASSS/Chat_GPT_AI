"""Hardware probe independent of the game simulator. No drivers are installed."""
from __future__ import annotations


def available_devices():
    try:
        import torch
        if torch.cuda.is_available():
            return (['cuda:0','cpu'],f'CUDA GPU: {torch.cuda.get_device_name(0)} (PyTorch {torch.__version__})')
        return (['cpu'],'CPU only. CUDA is not available to this PyTorch environment.')
    except ImportError:
        return (['cpu'],'PyTorch not installed in the selected environment.')
    except Exception as exc:
        return (['cpu'],f'Could not query CUDA: {exc}')


def validate_device(name, valid):
    if name not in valid:
        raise ValueError(f'{name} is unavailable here; available: {", ".join(valid)}')
