"""Compile frozen CPU inference without changing precision or model parameters."""
import torch


def frozen_inference(model):
    model.eval()
    for parameter in model.parameters():parameter.requires_grad_(False)
    if not isinstance(model,torch.jit.ScriptModule):model=torch.jit.script(model)
    # No quantization, half precision or optimize_for_inference kernel rewrites.
    return torch.jit.freeze(model.eval())
