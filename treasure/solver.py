"""Local rectangle-placement model. Exact enumeration, then uniform rejection sampling.
No webpage code is copied. Rotations are allowed; touching is allowed; overlap is not.
"""
from collections import Counter
import random

def placements(n,w,h):
    result=[]
    for width,height in sorted({(w,h),(h,w)}):
        for y in range(n-height+1):
            for x in range(n-width+1):
                result.append(sum(1<<((y+dy)*n+x+dx) for dy in range(height) for dx in range(width)))
    return result

def solve(n,shapes,cells,node_limit=150000,sample_limit=1800,attempt_limit=200000):
    empty=sum(1<<i for i,v in enumerate(cells) if v==1)
    hits=sum(1<<i for i,v in enumerate(cells) if v==2)
    groups=Counter()
    for w,h,count in shapes:groups[tuple(sorted((w,h)))]+=count
    items=[]
    for shape,count in sorted(groups.items(),key=lambda v:-(v[0][0]*v[0][1])):
        options=[m for m in placements(n,*shape) if not m&empty]
        items.extend((shape,options) for _ in range(count))
    if any(not opts for _,opts in items):return {'masks':[],'exact':True,'probabilities':[None]*(n*n)}
    masks=[];nodes=0
    class Limit(Exception):pass
    def visit(depth,used,last):
        nonlocal nodes
        nodes+=1
        if nodes>node_limit:raise Limit()
        if depth==len(items):
            if used&hits==hits:masks.append(used)
            return
        shape,options=items[depth]
        start=last+1 if depth and items[depth-1][0]==shape else 0
        for idx in range(start,len(options)):
            mask=options[idx]
            if not mask&used:visit(depth+1,used|mask,idx)
    exact=True
    try:visit(0,0,-1)
    except Limit:
        # Discard the truncated DFS prefix: it is spatially biased.
        exact=False;masks=[];rng=random.Random(1941)
        for _ in range(attempt_limit):
            used=0
            for _,options in items:
                mask=rng.choice(options)
                if mask&used:break
                used|=mask
            else:
                if used&hits==hits:masks.append(used)
            if len(masks)>=sample_limit:break
    p=[sum(bool(m&(1<<i)) for m in masks)/len(masks) if masks else None for i in range(n*n)]
    return {'masks':masks,'exact':exact,'probabilities':p}

def estimate(masks,cells,cost):
    """Reference policy: random order without replacement until all treasure cells dug.
    Expected last-success position = K*(N+1)/(K+1). No optimal-policy claim.
    """
    unknown=sum(v==0 for v in cells)
    unopened=sum(1<<i for i,v in enumerate(cells) if v==0)
    if not masks:return None
    counts=[(m&unopened).bit_count() for m in masks]
    mean=sum(k*(unknown+1)/(k+1) for k in counts)/len(counts)
    return {'cells':round(mean,1),'cost':round(mean*cost),'minimum':min(counts)*cost,'maximum':unknown*cost}


def estimate_guided(masks,cells,cost,trials=48,deferred=()):
    """Finite-posterior greedy rollout; approximate, not a guaranteed optimal plan."""
    if not masks:return None
    rng=random.Random(607)
    pool=rng.sample(masks,min(1200,len(masks)))
    unknown=sum(1<<i for i,v in enumerate(cells) if v==0)
    deferred_mask=sum(1<<i for i in set(deferred))
    results=[]
    for _ in range(trials):
        truth=rng.choice(pool);belief=pool[:];remaining=unknown;steps=0
        while truth&remaining:
            scores=[]
            for i in range(len(cells)):
                bit=1<<i
                if remaining&bit:
                    score=sum(bool(m&bit) for m in belief)
                    scores.append((bool(score and not deferred_mask&bit),score,rng.random(),bit))
            bit=max(scores)[3];hit=bool(truth&bit);steps+=1;remaining^=bit
            belief=[m for m in belief if bool(m&bit)==hit]
        results.append(steps)
    return {'cells':round(sum(results)/len(results),1),'cost':round(sum(results)*cost/len(results))}
