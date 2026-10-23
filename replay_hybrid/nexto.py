"""Optional original Nexto opponent using local, fingerprinted weights."""
import numpy as np
import torch


class NextoOpponent:
    def __init__(self,path,device='cpu'):
        self.device=device;self.actor=torch.jit.load(str(path),map_location=device).eval()

    @torch.inference_mode()
    def logits(self,views):
        values=tuple(torch.as_tensor(np.stack([v[i] for v in views]),device=self.device,dtype=torch.float32) for i in range(3))
        result=self.actor(values)[0]
        if result.shape!=(len(views),90) or not torch.isfinite(result).all():raise ValueError('Invalid Nexto opponent logits')
        return result.cpu().numpy()
