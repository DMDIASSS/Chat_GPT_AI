"""Fourth expert: a hash-locked local Fusion actor, frozen for selector training."""
import numpy as np
import torch
from .chronos_fusion import TeacherFusion
from .chronos import CHRONOS_CONTRACT
from .core import check_model
from .giga_teachers import TABLE,native_action_mask


class ExpertPool(TeacherFusion):
    names=('chronos','galactus','ripple','fusion')
    def __init__(self,path):
        check_model(path,CHRONOS_CONTRACT)
        super().__init__()
        self.fusion=torch.jit.load(str(path),map_location='cpu').eval()
        for parameter in self.fusion.parameters():parameter.requires_grad_(False)
        with torch.inference_mode():out=self.fusion(torch.zeros(1,225))
        if out.shape!=(1,90) or not torch.isfinite(out).all():raise ValueError('Fusion actor must be finite 225 -> 90')
    def proposals(self,state,previous,chronos_features,mirror):
        original=super().proposals(state,previous,chronos_features,mirror)
        with torch.inference_mode():logits=self.fusion(torch.from_numpy(chronos_features)[None,:])[0].numpy()
        if logits.shape!=(90,) or not np.isfinite(logits).all():raise ValueError('Invalid frozen Fusion proposal')
        mask=native_action_mask(state.cars[self.agent]);command=TABLE[int(np.where(mask,logits,-np.inf).argmax())].copy()
        if mirror:command[[1,3,4]]*=-1
        return np.vstack((original,command))
