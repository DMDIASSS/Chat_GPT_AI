"""Compiler-free FP32 inference for small GPUs; never alters training weights.

CUDA graphs replay a fixed GPU command sequence. This reduces Python/driver
launch overhead; it does not replace RocketSim or approximate its physics.
"""
from collections import OrderedDict
import time
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from replay_il_inference import InferenceKernel,attention_last_or_cross


def causal_attention(module,x):
    """One packed QKV projection, with a native causal SDPA mask."""
    batch,length,width=x.shape;heads=module.num_heads;depth=width//heads
    q,k,v=F.linear(x,module.in_proj_weight,module.in_proj_bias).reshape(
        batch,length,3,heads,depth).permute(2,0,3,1,4).unbind(0)
    x=F.scaled_dot_product_attention(q,k,v,is_causal=True,dropout_p=0.)
    return F.linear(x.transpose(1,2).reshape(batch,length,width),
                    module.out_proj.weight,module.out_proj.bias)


class TurboKernel(InferenceKernel):
    """Same attention, GELUs and value ensemble with fewer dispatches/copies."""
    def __init__(self,model):
        super().__init__(model)
        for head in model.values:
            if len(head)!=3 or not isinstance(head[1],nn.GELU) or head[1].approximate!='none':
                raise ValueError('Turbo inference requires the existing exact-GELU value heads')
        # Inference-owned copies only. The checkpoint and live model parameters
        # retain their original layout, values and source fingerprints.
        self.register_buffer('value_weight',torch.cat([h[0].weight.detach() for h in model.values]),persistent=False)
        self.register_buffer('value_bias',torch.cat([h[0].bias.detach() for h in model.values]),persistent=False)
        self.register_buffer('value_out',torch.stack([h[2].weight.detach()[0] for h in model.values]),persistent=False)
        self.register_buffer('value_out_bias',torch.cat([h[2].bias.detach() for h in model.values]),persistent=False)

    def decode(self,history):
        model=self.model;x=model.project(history)+model.position[:,:history.shape[1]]
        for layer in model.temporal.layers[:-1]:
            x=x+causal_attention(layer.self_attn,layer.norm1(x))
            x=x+layer.linear2(F.gelu(layer.linear1(layer.norm2(x))))
        last=model.temporal.layers[-1];normalized=last.norm1(x)
        x=x[:,-1:]+attention_last_or_cross(last.self_attn,normalized[:,-1:],normalized)
        x=x+last.linear2(F.gelu(last.linear1(last.norm2(x))))
        x=model.norm(x[:,0])
        hidden=F.gelu(F.linear(x,self.value_weight,self.value_bias)).reshape(x.shape[0],len(model.values),-1)
        values=((hidden*self.value_out).sum(-1)+self.value_out_bias).tanh()
        return model.policy(x),values


def pack_observations(views):
    """One contiguous transfer instead of three separately synchronized copies."""
    count=len(views);packed=np.empty(count*1057,np.float32)
    if count:
        # Store each field contiguously, so GPU linear layers do not need to
        # materialize copies of interleaved/strided query and entity inputs.
        packed[:count*32]=np.stack([v[0] for v in views]).reshape(-1)
        packed[count*32:count*1016]=np.stack([v[1] for v in views]).reshape(-1)
        packed[count*1016:]=np.stack([v[2] for v in views]).reshape(-1)
    return packed


def unpack_observations(packed):
    packed=packed.reshape(-1);count=packed.numel()//1057
    return packed[:count*32].reshape(count,1,32),packed[count*32:count*1016].reshape(count,41,24),packed[count*1016:].reshape(count,41)


class FeatureStep:
    """GPU-only spatial encoding, feature-bank update, history gather and heads."""
    def __init__(self,kernel,bank,new_count,batch,history):
        self.kernel=kernel;self.bank=bank;self.new_count=new_count;self.batch=batch;self.history=history
        self.observation_size=new_count*1057
        self.input_size=self.observation_size+new_count+batch*history

    def __call__(self,packed):
        count=self.new_count;offset=self.observation_size
        if count:
            features=self.kernel.encode(unpack_observations(packed[:offset]))
            indices=packed[offset:offset+count].to(torch.int64)
            self.bank.index_copy_(0,indices,features)
        indices=packed[offset+count:].to(torch.int64).reshape(self.batch,self.history)
        return self.kernel.decode(self.bank[indices])


class CapturedStep:
    """One bounded, shape-specific CUDA graph, with pinned host staging."""
    def __init__(self,step,example,device,pool):
        self.host=torch.empty(step.input_size,dtype=torch.float32,pin_memory=True)
        self.input=torch.empty(step.input_size,dtype=torch.float32,device=device)
        self.host.copy_(torch.from_numpy(example));self.input.copy_(self.host,non_blocking=True)
        self.copied=torch.cuda.Event();self.copied.record()
        stream=torch.cuda.Stream(device=device);stream.wait_stream(torch.cuda.current_stream(device))
        with torch.cuda.stream(stream),torch.inference_mode():
            for _ in range(3):step(self.input)
        torch.cuda.current_stream(device).wait_stream(stream)
        self.graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph,pool=pool),torch.inference_mode():
            self.output=step(self.input)
        self.graph.replay()

    def __call__(self,packed):
        # CPU staging may be rewritten only after its preceding H2D has finished.
        # The model's output consumption usually already enforces this boundary.
        self.copied.synchronize()
        self.host.copy_(torch.from_numpy(packed))
        self.input.copy_(self.host,non_blocking=True)
        self.copied.record()
        self.graph.replay()
        return self.output


class GraphFeatures:
    """Persistent feature bank and bounded graphs; irregular shapes use eager FP32.

    Sequential graphs share a pool and bank. A planner is single-threaded and
    consumes each returned output before another inference call. Graph outputs
    are borrowed, just like the preceding reusable feature-bank storage.
    """
    def __init__(self,kernel,device,capacity,history,max_graphs=6):
        self.device=torch.device(device)
        if self.device.type!='cuda' or not torch.cuda.is_available():
            raise ValueError('CUDA graphs require an available CUDA device')
        self.kernel=kernel;self.capacity=capacity;self.history=history;self.max_graphs=max_graphs
        self.bank=torch.zeros((capacity,128),device=self.device)
        self.graphs=OrderedDict();self.pool=torch.cuda.graph_pool_handle();self.features={};self.count=0
        self.capture_ms=0.;self.replays=0;self.eager_calls=0;self._allow_capture=False
        self.failure=None

    def begin(self,allow_capture=False):
        self.features.clear();self.count=0;self._allow_capture=allow_capture

    @torch.inference_mode()
    def infer(self,histories):
        padded=[];new={}
        for history in histories:
            views=list(history)[-self.history:]
            if not views:raise ValueError('Planner requires current observations')
            views=[views[0]]*(self.history-len(views))+views;padded.append(views)
            for view in views:
                if id(view) not in self.features:new[id(view)]=view
        if not padded:raise ValueError('Planner requires at least one history')
        offset=self.count;new_views=list(new.values());count=len(new_views)
        if offset+count>self.capacity:raise ValueError('Inference feature-bank capacity exceeded')
        for index,view in enumerate(new_views):self.features[id(view)]=(view,offset+index)
        self.count+=count
        step=FeatureStep(self.kernel,self.bank,count,len(padded),self.history)
        packed=np.empty(step.input_size,np.float32)
        if count:packed[:step.observation_size]=pack_observations(new_views).reshape(-1)
        packed[step.observation_size:step.observation_size+count]=np.arange(offset,offset+count)
        packed[step.observation_size+count:]=[self.features[id(view)][1] for views in padded for view in views]
        key=(count,len(padded));captured=self.graphs.get(key)
        if captured is None and self._allow_capture and len(self.graphs)<self.max_graphs and self.failure is None:
            started=time.perf_counter()
            try:
                captured=CapturedStep(step,packed,self.device,self.pool);self.graphs[key]=captured
            except RuntimeError as error:
                # Capture is an optional inference optimization. Report its
                # failure, preserve outputs through the ordinary FP32 path.
                self.failure=str(error)[:500]
            self.capture_ms+=(time.perf_counter()-started)*1000
        if captured is not None:
            self.replays+=1;return captured(packed)
        self.eager_calls+=1
        return step(torch.as_tensor(packed,device=self.device))

    def report(self):
        return {'captured_shapes':len(self.graphs),'replays':self.replays,'eager_calls':self.eager_calls,
                'capture_ms':self.capture_ms,'capture_failure':self.failure,
                'feature_bank_mib':self.bank.numel()*self.bank.element_size()/2**20}

    def close(self):
        torch.cuda.synchronize(self.device)
        self.graphs.clear();self.features.clear();self.bank=None
