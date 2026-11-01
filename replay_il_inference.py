"""FP32 inference kernels for the existing chunk model; no trained weights change."""
import torch
from torch import nn
from torch.nn import functional as F


def attention_last_or_cross(module,query,key_value,mask=None):
    """Packed KV projection with one-query SDPA; same learned MHA parameters."""
    width=module.embed_dim;heads=module.num_heads;head_width=width//heads
    weight=module.in_proj_weight;bias=module.in_proj_bias
    q=F.linear(query,weight[:width],None if bias is None else bias[:width])
    k,v=F.linear(key_value,weight[width:],None if bias is None else bias[width:]).chunk(2,-1)
    def split(value):return value.reshape(value.shape[0],value.shape[1],heads,head_width).transpose(1,2)
    padding=None if mask is None else mask[:,None,None,:]
    out=F.scaled_dot_product_attention(split(q),split(k),split(v),attn_mask=padding,dropout_p=0.)
    out=out.transpose(1,2).reshape(query.shape[0],query.shape[1],width)
    return F.linear(out,module.out_proj.weight,module.out_proj.bias)


class InferenceKernel(nn.Module):
    """Unchanged spatial blocks and causal context; final temporal query only.

    The last query can attend to every causal history position, so its final
    attention row requires no causal mask. Earlier layers still calculate the
    full masked history. Only unused final-layer outputs are omitted.
    """
    def __init__(self,model):
        super().__init__();self.model=model
        layers=model.temporal.layers
        if not len(layers) or model.temporal.norm is not None:
            raise ValueError('Unsupported temporal encoder structure')
        for layer in layers:
            if not layer.norm_first or layer.activation_relu_or_gelu!=2 or any(
                    isinstance(module,nn.Dropout) and module.p!=0 for module in layer.modules()):
                raise ValueError('Inference kernels require the existing norm-first GELU, zero-dropout model')
        self.register_buffer('causal',torch.ones(model.history,model.history,dtype=torch.bool,
                             device=next(model.parameters()).device).triu(1),persistent=False)
        self.eval()

    def encode(self,observations):
        q,kv,mask=observations;encoder=self.model.encoder
        q=encoder.query_preprocess(q);kv=encoder.key_value_preprocess(kv)
        for block in encoder.blocks:
            normalized=block.norm2(kv)
            q=q+attention_last_or_cross(block.attention,block.norm1(q),normalized,mask)
            q=q+block.linear2(torch.relu(block.linear1(block.norm3(q))))
        return q[:,0]

    def decode(self,history):
        model=self.model;x=model.project(history)+model.position[:,:history.shape[1]]
        causal=self.causal[:history.shape[1],:history.shape[1]]
        for layer in model.temporal.layers[:-1]:x=layer(x,src_mask=causal)
        last=model.temporal.layers[-1];normalized=last.norm1(x)
        x=x[:,-1:]+attention_last_or_cross(last.self_attn,normalized[:,-1:],normalized)
        x=x+last.linear2(F.gelu(last.linear1(last.norm2(x))))
        x=model.norm(x[:,0])
        return model.policy(x),torch.cat([head(x).tanh() for head in model.values],-1)


def freeze_kernel(kernel):
    """Compile the inference graph in memory; no checkpoint/export is written."""
    import warnings
    model=kernel.model;device=next(model.parameters()).device
    example=(torch.zeros(2,1,32,device=device),torch.zeros(2,41,24,device=device),torch.zeros(2,41,device=device))
    history=torch.zeros(2,model.history,128,device=device)
    with torch.inference_mode(),warnings.catch_warnings():
        # Architecture guards are fixed; batch/history sizes remain tensor sizes.
        warnings.simplefilter('ignore',torch.jit.TracerWarning)
        warnings.filterwarnings('ignore',message='.*torch.jit.*deprecated.*',category=FutureWarning)
        traced=torch.jit.trace_module(kernel,{'encode':(example,),'decode':(history,)},check_trace=False)
        return torch.jit.freeze(traced,preserved_attrs=['encode','decode'])
