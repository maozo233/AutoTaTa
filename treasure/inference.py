"""Joint, non-overlapping silhouette hypotheses and conditional probabilities."""
import math,random
from collections import Counter
import numpy as np
import cv2

def options_for(n,template,cells,foreground):
    empty=sum(1<<i for i,v in enumerate(cells) if v==1)
    hits=[i for i,v in enumerate(cells) if v==2]
    options=[];seen=set()
    for turn in range(4):
        image=np.rot90(template['mask'],turn).copy();h,w=image.shape[0]//32,image.shape[1]//32
        key=(w,h,image.tobytes())
        if key in seen:continue
        seen.add(key)
        variants=[]
        for scale in (.9,1.,1.1):
            source=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)
            canvas=np.zeros_like(image);hh=min(len(source),len(canvas));ww=min(source.shape[1],canvas.shape[1])
            sy=max(0,(len(source)-hh)//2);sx=max(0,(source.shape[1]-ww)//2)
            dy=max(0,(len(canvas)-hh)//2);dx=max(0,(canvas.shape[1]-ww)//2)
            canvas[dy:dy+hh,dx:dx+ww]=source[sy:sy+hh,sx:sx+ww];variants.append(canvas)
        for y in range(n-h+1):
            for x in range(n-w+1):
                mask=sum(1<<((y+dy)*n+x+dx) for dy in range(h) for dx in range(w))
                if mask&empty:continue
                scores=[];evidence=0
                for variant in variants:
                    likelihood=0.;matched=0
                    for index in hits:
                        if not mask>>index&1:continue
                        r,c=divmod(index,n);pred=variant[(r-y)*32:(r-y+1)*32,(c-x)*32:(c-x+1)*32][5:27,5:27]>0
                        actual=foreground[r*32:(r+1)*32,c*32:(c+1)*32][5:27,5:27]>0
                        if not actual.any():continue
                        union=np.logical_or(pred,actual).sum()
                        iou=np.logical_and(pred,actual).sum()/max(1,union)
                        likelihood+=18*(iou-1);matched+=1
                    scores.append((likelihood,matched))
                likelihood,evidence=max(scores)
                options.append(dict(mask=mask,x=x,y=y,w=w,h=h,turn=turn,image=image,log_weight=likelihood,evidence=evidence))
    return options

def infer(n,templates,cells,foreground,node_limit=90000,samples=1200,attempts=180000,pins=None,stop_when_identified=False):
    pins=pins or {}
    choices=[options_for(n,t,cells,foreground) for t in templates]
    for item,pin in pins.items():
        if item>=len(choices):return None
        target=np.rot90(templates[item]['mask'],pin['turn'])
        choices[item]=[o for o in choices[item] if o['x']==pin['x'] and o['y']==pin['y'] and np.array_equal(o['image'],target)]
    hits=sum(1<<i for i,v in enumerate(cells) if v==2)
    if not choices or any(not c for c in choices):return None
    order=sorted(range(len(choices)),key=lambda i:len(choices[i]))
    layouts=[];nodes=0
    class Limit(Exception):pass
    def walk(remaining,used,path,weight):
        nonlocal nodes
        nodes+=1
        if nodes>node_limit:raise Limit()
        if not remaining:
            if used&hits==hits:layouts.append((used,tuple(path),weight))
            return
        uncovered=hits&~used
        if uncovered:
            # Every exposed tile must have exactly one owner. Branch on its
            # compatible owners first rather than filling unrelated hidden tiles.
            # The deterministic target makes each complete layout appear once.
            target_options=None
            while uncovered:
                bit=uncovered&-uncovered;uncovered^=bit
                viable=[(item,j) for item in remaining for j,o in enumerate(choices[item])
                        if o['mask']&bit and not o['mask']&used]
                if not viable:return
                if target_options is None or len(viable)<len(target_options):target_options=viable
            branches=target_options
        else:
            item=min(remaining,key=lambda i:len(choices[i]))
            branches=[(item,j) for j,o in enumerate(choices[item]) if not o['mask']&used]
        for item,j in branches:
            o=choices[item][j]
            walk(tuple(i for i in remaining if i!=item),used|o['mask'],path+[(item,j)],weight+o['log_weight'])
    exact=True
    try:walk(tuple(order),0,[],0.)
    except Limit:
        exact=False;layouts=[];rng=random.Random(1207)
        for _ in range(attempts):
            used=0;path=[];weight=0
            for item in order:
                j=rng.randrange(len(choices[item]));o=choices[item][j]
                if used&o['mask']:break
                used|=o['mask'];path.append((item,j));weight+=o['log_weight']
            else:
                if used&hits==hits:layouts.append((used,tuple(path),weight))
            if len(layouts)>=samples:break
    if not layouts:return None
    top=max(v[2] for v in layouts);weights=[math.exp(v[2]-top) for v in layouts];total=sum(weights)
    best=layouts[max(range(len(layouts)),key=lambda i:weights[i])][1]
    ghosts=[]
    for item,j in best:
        o=choices[item][j]
        if not o['evidence'] and item not in pins:continue
        # Identical treasures and rotations share a physical footprint. Aggregate
        # by footprint rather than one arbitrary object/rotation assignment.
        support=sum(weight for (_,path,_),weight in zip(layouts,weights) if any(choices[k][v]['mask']==o['mask'] for k,v in path))/total
        ghosts.append({**o,'support':support,'certain':exact and support>1-1e-8,'pinned':item in pins})
    # Object identity can be known while its precise footprint is still ambiguous.
    groups=Counter(tuple(sorted((t['mask'].shape[1]//32,t['mask'].shape[0]//32))) for t in templates)
    identified=[]
    for shape,maximum in sorted(groups.items()):
        counts=[]
        for _,path,_ in layouts:
            count=sum(1 for k,v in path if tuple(sorted((choices[k][v]['w'],choices[k][v]['h'])))==shape and (choices[k][v]['evidence'] or k in pins))
            counts.append(count)
        found=0
        for count in range(1,maximum+1):
            support=sum(weight for count_found,weight in zip(counts,weights) if count_found>=count)/total
            if support>=.75:found=count
        identified.append([*shape,found])
    from .presentation import pending_identified
    shapes=[[*shape,count] for shape,count in groups.items()]
    exploration_stopped=stop_when_identified and not pending_identified(shapes,identified)
    probability=[None]*(n*n) if exploration_stopped else [sum(w for (m,_,_),w in zip(layouts,weights) if m>>i&1)/total for i in range(n*n)]
    # Resample the weighted posterior for the existing consumption estimator.
    rng=random.Random(920);masks=rng.choices([v[0] for v in layouts],weights=weights,k=min(1800,len(layouts)))
    certain=[i for i in range(n*n) if exact and all(m & (1<<i) for m,_,_ in layouts)]
    from .presentation import trusted_ghosts
    candidates=ghosts;ghosts=trusted_ghosts(ghosts)
    return dict(masks=masks,probabilities=probability,certainCells=certain,candidateGhosts=candidates,identifiedShapes=identified,ghosts=ghosts,exact=exact,count=len(layouts),effective=total*total/sum(w*w for w in weights))
