"""Training-only medoid vocabulary. Every token is a feasible recorded chunk."""
import numpy as np

WEIGHTS=np.array([1,1,1,1,1,6,6,2],np.float32)

def distances(chunks,book):
    a=np.asarray(chunks,np.float32).reshape(len(chunks),-1)*np.sqrt(np.tile(WEIGHTS,chunks.shape[1]))
    b=np.asarray(book,np.float32).reshape(len(book),-1)*np.sqrt(np.tile(WEIGHTS,book.shape[1]))
    return np.maximum((a*a).sum(1)[:,None]+(b*b).sum(1)[None]-2*a@b.T,0)

def tokenize(chunks,book,batch=1024):
    ids=[];errors=[]
    for start in range(0,len(chunks),batch):
        d=distances(chunks[start:start+batch],book);indices=d.argmin(1)
        ids.extend(indices);errors.extend(d[np.arange(len(indices)),indices]/chunks.shape[1])
    return np.asarray(ids,np.int64),np.asarray(errors,np.float32)

def fit(chunks,size=256,seed=20261016):
    chunks=np.asarray(chunks,np.float32)
    if chunks.ndim!=3 or chunks.shape[-1]!=8 or not np.isfinite(chunks).all():raise ValueError('Invalid action chunks')
    if np.any(np.abs(chunks)>1.001) or not np.all(np.isin(chunks[:,:,5:],[0,1])):raise ValueError('Invalid buttons')
    rng=np.random.default_rng(seed)
    if len(chunks)>20000:chunks=chunks[rng.choice(len(chunks),20000,replace=False)]
    # Seed with common rounded chunks; refine medoids, retaining rare examples
    # when they have the largest reconstruction error. No fractional jump keys.
    rounded=chunks.copy();rounded[:,:,:5]=np.round(rounded[:,:,:5]*4)/4
    _,first,counts=np.unique(rounded.reshape(len(chunks),-1),axis=0,return_index=True,return_counts=True)
    target=min(size,len(first));order=np.argsort(-counts,kind='stable')
    selected=list(first[order[:max(1,target*2//3)]])
    nearest=np.min(distances(chunks,chunks[selected]),axis=1)
    while len(selected)<target:
        index=int(nearest.argmax());selected.append(index)
        nearest=np.minimum(nearest,distances(chunks,chunks[index:index+1])[:,0]);nearest[selected]=0
    book=chunks[selected].copy()
    for _ in range(4):
        ids,error=tokenize(chunks,book)
        updated=[]
        for group in range(len(book)):
            members=np.flatnonzero(ids==group)
            if not len(members):updated.append(book[group]);continue
            centroid=chunks[members].mean(0,keepdims=True)
            best=distances(chunks[members],centroid).argmin();updated.append(chunks[members[best]])
        book=np.asarray(updated,np.float32)
    _,errors=tokenize(chunks,book)
    return book,{'tokens':len(book),'training_chunks':len(chunks),'mean_weighted_error':float(errors.mean()),
                 'p95_weighted_error':float(np.quantile(errors,.95)),'fit_split':'train_only'}
