"""Conservative board observations and session-local silhouette templates."""
from dataclasses import dataclass
import cv2
import numpy as np

@dataclass
class Observation:
    rect: tuple
    size: int
    cells: list
    tray: tuple | None
    silhouettes: list
    foreground: np.ndarray
    frame_size: tuple = ()
    pending_cells: tuple = ()
    completed_cells: tuple = ()
    transient_cells: tuple = ()

def board_rect(frame):
    h,w=frame.shape[:2]
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(75,60,70),(125,255,255));mask[:int(h*.38)]=0
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for c in contours:
        x,y,bw,bh=cv2.boundingRect(c)
        if .3*w<bw<.94*w and .85<bw/bh<1.15 and y>h*.38 and bh>h*.2:
            gray=cv2.cvtColor(frame[y:y+bh,x:x+bw],cv2.COLOR_BGR2GRAY).astype(float)
            scores=[]
            for n in range(5,10):
                values=[]
                for axis,length in [(0,bw),(1,bh)]:
                    profile=gray.mean(axis=axis);step=length/n
                    for k in range(1,n):
                        q=round(k*step);r=max(1,round(step*.035));d=max(r+2,int(step*.3))
                        values.append((profile[q-d:q-r].mean()+profile[q+r+1:q+d+1].mean())/2-profile[q-r:q+r+1].min())
                scores.append((float(np.mean(values)),n))
            score,n=max(scores)
            if score>20:candidates.append((score,(x,y,bw,bh),n))
    if not candidates:return sparse_board_rect(frame)
    _,rect,n=max(candidates)
    return rect,n

def _current_grid_extent(frame, blue, panel):
    """Use current covered tile extents; accept only an unambiguous size.

    Connected tile groups contribute their full extent. Missing outer rows are
    not padded using another board's geometry.
    """
    x,y,bw,bh=panel
    cs,_=cv2.findContours(blue,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[cv2.boundingRect(c) for c in cs]
    boxes=[b for b in boxes if b[0]>bw*.035 and b[1]>bh*.035
           and b[0]+b[2]<bw*.965 and b[1]+b[3]<bh*.965
           and b[2]>bw*.06 and b[3]>bh*.06]
    singles=[b for b in boxes if .065*bw<b[2]<.22*bw and .85<b[2]/b[3]<1.15]
    kernel=max(3,round(bw*.012))
    if kernel%2==0:kernel+=1
    separated=cv2.erode(blue,np.ones((kernel,kernel),np.uint8))
    parts,_=cv2.findContours(separated,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    singles=[cv2.boundingRect(c) for c in parts]
    singles=[(a-(kernel-1)/2,b-(kernel-1)/2,c+kernel-1,d+kernel-1)
             for a,b,c,d in singles if .065*bw<c<.22*bw and .8<c/d<1.2]
    if len(singles)<2:return None
    tile=max((min(b[2:]) for b in singles),key=lambda t:sum(abs(min(b[2:])-t)<t*.12 for b in singles))
    singles=[b for b in singles if abs(min(b[2:])-tile)<tile*.12]
    if len(singles)<2:return None
    tile=float(np.median([min(b[2:]) for b in singles]))
    left=min(b[0] for b in boxes);top=min(b[1] for b in boxes)
    right=max(b[0]+b[2] for b in boxes);bottom=max(b[1]+b[3] for b in boxes)
    width=right-left;height=bottom-top;candidates=[]
    for n in range(5,10):
        pitch=np.array([width/n,height/n])
        if np.any(pitch<tile*.88) or np.any(pitch>tile*1.12):continue
        if abs(left+width/2-bw/2)>pitch[0]*.22 or abs(top+height/2-bh/2)>pitch[1]*.22:continue
        centers=np.array([(a+c/2,b+d/2) for a,b,c,d in singles])
        indices=np.round((centers-[left,top])/pitch-.5)
        if np.any(np.abs(centers-[left,top]-(indices+.5)*pitch)>pitch*.15):continue
        rect=(x+left,y+top,width,height);tray,_=read_tray(frame,rect)
        if tray is not None:candidates.append((rect,n))
    return candidates[0] if len(candidates)==1 else None

def sparse_board_rect(frame):
    """Locate separated covered tiles inside the dirt panel, with tray validation."""
    h,w=frame.shape[:2];hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    dirt=cv2.inRange(hsv,(140,25,45),(179,170,150));dirt[:int(h*.4)]=0
    contours,_=cv2.findContours(dirt,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours,key=cv2.contourArea,reverse=True):
        x,y,bw,bh=cv2.boundingRect(contour)
        if not (.45*w<bw<.95*w and .85<bw/bh<1.15 and cv2.contourArea(contour)>.65*bw*bh):continue
        blue=cv2.inRange(hsv[y:y+bh,x:x+bw],(75,60,70),(140,255,255))
        current=_current_grid_extent(frame,blue,(x,y,bw,bh))
        if current is not None:return current
        # Adjacent blue tile borders may form one connected blob. Erode only
        # for locating their centers; classification still uses original pixels.
        boxes=[]
        for kernel in (1,max(3,round(bw*.012)),max(5,round(bw*.022))):
            separated=cv2.erode(blue,np.ones((kernel,kernel),np.uint8)) if kernel>1 else blue
            cs,_=cv2.findContours(separated,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            candidates=[cv2.boundingRect(c) for c in cs]
            candidates=[b for b in candidates if .065*bw<b[2]<.22*bw and .8<b[2]/b[3]<1.2]
            if len(candidates)>=3:
                boxes=candidates;break
        if len(boxes)<3:continue
        tile=float(np.median([min(b[2:]) for b in boxes]))
        boxes=[b for b in boxes if .8*tile<min(b[2:])<1.2*tile]
        if len(boxes)<3:continue
        centers=np.array([(x+a+c/2,y+b+d/2) for a,b,c,d in boxes]);steps=[]
        for axis in (0,1):
            values=sorted(centers[:,axis]);deltas=[b-a for a,b in zip(values,values[1:]) if .7*tile<b-a<1.2*tile]
            if not deltas:break
            steps.append(float(np.median(deltas)))
        if len(steps)!=2:continue
        pitch=np.array(steps)
        if max(steps)/min(steps)<1.1:pitch[:]=max(steps)
        for n in range(5,10):
            side=n*pitch
            if np.any(side>np.array([bw,bh])*.95):continue
            origin=np.array([x+bw/2,y+bh/2])-side/2
            # Snap the centered lattice to covered-tile centers.
            indices=np.round((centers-origin)/pitch-.5)
            origin=np.median(centers-(indices+.5)*pitch,axis=0)
            if np.any(indices<0) or np.any(indices>=n):continue
            if np.any(np.abs(centers-origin-(indices+.5)*pitch)>pitch*.12):continue
            rect=(round(origin[0]),round(origin[1]),round(side[0]),round(side[1]))
            # When outer covered tiles remain, use their actual border extents
            # to remove the few-pixel center bias introduced by erosion.
            pad=round(max(pitch)*.12)
            rx,ry,rw,rh=rect
            ax=max(x,rx-pad);ay=max(y,ry-pad);ex=min(x+bw,rx+rw+pad);ey=min(y+bh,ry+rh+pad)
            region=blue[ay-y:ey-y,ax-x:ex-x]
            sy,sx=np.where(region>0)
            if len(sx):
                extent=(int(sx.max()-sx.min()+1),int(sy.max()-sy.min()+1))
                if .9*rw<extent[0]<1.1*rw and .9*rh<extent[1]<1.1*rh:
                    rect=(ax+int(sx.min()),ay+int(sy.min()),*extent)
            tray,_=read_tray(frame,rect)
            if tray is not None:return rect,n
    return None

def read_tray(frame,board):
    x,y,w,h=board;hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(0,0,55),(179,95,130));mask[y:]=0
    contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    choices=[]
    for c in contours:
        a,b,cw,ch=cv2.boundingRect(c)
        if cv2.contourArea(c)>.65*cw*ch and .35*w<cw<.9*w and .85<cw/ch<1.5 and abs(a+cw/2-x-w/2)<w*.12 and b+ch<y:
            choices.append((cw*ch,(a,b,cw,ch)))
    if not choices:return None,[]
    _,rect=max(choices);a,b,cw,ch=rect
    gray=cv2.cvtColor(frame[b:b+ch,a:a+cw],cv2.COLOR_BGR2GRAY)
    background=float(np.percentile(gray,70));sil=(gray<background-12).astype('uint8')
    tray_hsv=hsv[b:b+ch,a:a+cw]
    filled=(tray_hsv[:,:,1]>70)&(tray_hsv[:,:,2]>90)
    sil=np.maximum(sil,filled.astype('uint8'))
    sil=cv2.morphologyEx(sil,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    edge=max(2,round(cw*.03));sil[:edge]=0;sil[-edge:]=0;sil[:,:edge]=0;sil[:,-edge:]=0
    count,labels,stats,_=cv2.connectedComponentsWithStats(sil)
    shapes=[]
    for label in range(1,count):
        sx,sy,sw,sh,area=stats[label]
        border_artifact=(sw>cw*.8 or sh>ch*.9) and area<sw*sh*.4
        if not border_artifact and area>cw*ch*.008 and sw>cw*.035 and sh>ch*.08:
            colored=cv2.cvtColor(frame[b+sy:b+sy+sh,a+sx:a+sx+sw],cv2.COLOR_BGR2HSV)
            component=labels[sy:sy+sh,sx:sx+sw]==label
            colored_pixels=((colored[:,:,1]>65)&(colored[:,:,2]>75)&component).sum()
            completed=colored_pixels>=max(3,cw*ch*.0005) and colored_pixels/max(1,component.sum())>.12
            shapes.append({'completed':completed,'mask':(labels[sy:sy+sh,sx:sx+sw]==label).astype('uint8'),'box':(int(sx),int(sy),int(sw),int(sh))})
    return rect,sorted(shapes,key=lambda s:(s['box'][0],s['box'][1]))

def observe(frame,hint=None):
    found=board_rect(frame)
    # An already verified grid remains valid as blue covered cells disappear.
    if hint is not None and hint.frame_size==frame.shape[:2]:
        old=hint.rect
        shrinking=found is not None and found[1]==hint.size and found[0][2]*found[0][3]<old[2]*old[3]*.8
        if found is None or shrinking:
            tray,_=read_tray(frame,old)
            if tray is not None:found=(old,hint.size)
    if found is None:return None
    rect,n=found;x,y,w,h=rect
    crop=frame[y:y+h,x:x+w];hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    cells=[];foreground=np.zeros((n*32,n*32),np.uint8)
    for row in range(n):
        for col in range(n):
            tile=hsv[round(row*h/n):round((row+1)*h/n),round(col*w/n):round((col+1)*w/n)]
            th,tw=tile.shape[:2];mx=max(1,round(tw*.15));my=max(1,round(th*.15));inner=tile[my:th-my,mx:tw-mx]
            blue=(inner[:,:,0]>=75)&(inner[:,:,0]<=140)&(inner[:,:,1]>45)&(inner[:,:,2]>80)
            # Opened dirt is muted reddish gray; treasure sits on that dirt.
            dirt=((inner[:,:,0]>145)|(inner[:,:,1]<35))&(inner[:,:,2]<135)
            if blue.mean()>.72:value=0
            elif dirt.mean()>.88 and np.std(inner[:,:,2])<16:value=1
            else:value=2  # A non-blue tile is opened; treasure may cover all dirt.
            cells.append(value)
            if value==2:
                whole_dirt=(((tile[:,:,0]>145)|(tile[:,:,1]<35))&(tile[:,:,2]<135))
                fg=(~whole_dirt).astype('uint8');fg[:my]=0;fg[-my:]=0;fg[:,:mx]=0;fg[:,-mx:]=0
                foreground[row*32:(row+1)*32,col*32:(col+1)*32]=cv2.resize(fg,(32,32),interpolation=cv2.INTER_NEAREST)
    tray,silhouettes=read_tray(frame,rect)
    return Observation(rect,n,cells,tray,silhouettes,foreground,frame.shape[:2])

def assign_templates(silhouettes,shapes):
    """Match tray components to configured dimensions; tolerate icon padding.
    Returns no templates when counts conflict. Never invent missing objects.
    """
    dims=[(w,h) for w,h,count in shapes for _ in range(count)]
    if len(dims)!=len(silhouettes) or len(dims)>12:return []
    # Bitmask assignment minimizes aspect ratio error, independent of tray scale.
    from functools import lru_cache
    import math
    @lru_cache(None)
    def visit(i,used):
        if i==len(dims):return 0,()
        sw,sh=silhouettes[i]['box'][2:];best=(float('inf'),())
        for j,(w,h) in enumerate(dims):
            if used>>j&1:continue
            for a,b in {(w,h),(h,w)}:
                error=abs(math.log((sw/sh)/(a/b)))
                rest,path=visit(i+1,used|1<<j)
                candidate=(error+rest,((j,a,b),)+path)
                if candidate[0]<best[0]:best=candidate
        return best
    error,path=visit(0,0)
    if error/max(1,len(dims))>.48:return []
    if any(abs(math.log((source['box'][2]/source['box'][3])/(w/h)))>.48 for source,(_,w,h) in zip(silhouettes,path)):return []
    templates=[]
    for source,(_,w,h) in zip(silhouettes,path):
        # Keep a small transparent margin around the original silhouette.
        target=np.zeros((h*32,w*32),np.uint8)
        mask=source['mask'];scale=min((w*32-4)/mask.shape[1],(h*32-4)/mask.shape[0])
        resized=cv2.resize(mask,(max(1,round(mask.shape[1]*scale)),max(1,round(mask.shape[0]*scale))),interpolation=cv2.INTER_NEAREST)
        oy=(len(target)-len(resized))//2;ox=(target.shape[1]-resized.shape[1])//2
        target[oy:oy+len(resized),ox:ox+resized.shape[1]]=resized
        templates.append({'width':w,'height':h,'mask':target})
    return templates

def read_stage(frame,tray,ocr):
    import re
    if not tray:return None
    x,y,w,h=tray
    crop=frame[max(0,y-round(h*.8)):y,max(0,x-round(w*.4)):min(frame.shape[1],x+round(w*1.4))]
    if not crop.size:return None
    result,_=ocr(cv2.resize(crop,None,fx=max(1,600/crop.shape[1]),fy=max(1,600/crop.shape[1])))
    chinese={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    for entry in result or []:
        if entry[2]<.6:continue
        match=re.search(r'第\s*([0-9一二三四五六七八九十]+)\s*[关關]',entry[1])
        if not match:continue
        value=match[1]
        if value.isdigit():number=int(value)
        elif '十' in value:
            a,b=value.split('十');number=(chinese.get(a,1))*10+chinese.get(b,0)
        else:number=chinese.get(value,0)
        if 1<=number<=24:return number
    return None

def silhouette_occupancy(mask,pitch):
    """Split a cleaned silhouette into pitch-sized tiles; retain any intersected tile.

    Keep the main connected silhouette including thin tips. Detached single-pixel
    specks are excluded. Pitch remains an estimate when the tray has no grid lines.
    """
    mask=(np.asarray(mask)>0).astype(np.uint8)
    if not mask.any() or pitch<1:return np.zeros((0,0),np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask)
    largest=max(stats[1:,cv2.CC_STAT_AREA],default=0)
    clean=np.zeros_like(mask)
    for label in range(1,count):
        if stats[label,cv2.CC_STAT_AREA]>=max(2,largest*.002):clean[labels==label]=1
    ys,xs=np.where(clean)
    if not len(xs):return np.zeros((0,0),np.uint8)
    clean=clean[ys.min():ys.max()+1,xs.min():xs.max()+1]
    import math
    rows=math.ceil(clean.shape[0]/pitch);cols=math.ceil(clean.shape[1]/pitch)
    occupied=np.zeros((rows,cols),np.uint8)
    for row in range(rows):
        for col in range(cols):
            tile=clean[round(row*pitch):round((row+1)*pitch),round(col*pitch):round((col+1)*pitch)]
            occupied[row,col]=bool(tile.any())
    return occupied


def infer_dimensions(silhouettes,n,tray=None):
    """Infer rectangular spans from occupied silhouette tiles, not area ratios."""
    if not silhouettes:return []
    spans=[min(s['box'][2:]) for s in silhouettes]
    pitch=tray[2]/7 if tray else float(np.median(spans))
    if pitch<3:return []
    from collections import Counter
    dimensions=Counter()
    for source in silhouettes:
        occupied=silhouette_occupancy(source['mask'],pitch)
        if not occupied.any():return []
        rows,cols=np.where(occupied)
        a,b=int(cols.max()+1),int(rows.max()+1)
        if max(a,b)>n:return []
        dimensions[tuple(sorted((a,b)))]+=1
    if sum(w*h*count for (w,h),count in dimensions.items())>n*n:return []
    return [[w,h,count] for (w,h),count in sorted(dimensions.items())]


def read_cost(frame,rect,ocr):
    import re
    x,y,w,h=rect
    crop=frame[min(frame.shape[0],y+h):,max(0,x):min(frame.shape[1],x+w)]
    if not crop.size:return None
    result,_=ocr(cv2.resize(crop,None,fx=max(1,500/crop.shape[1]),fy=max(1,500/crop.shape[1])))
    for entry in result or []:
        if entry[2]<.7:continue
        match=re.search(r'[0-9]+\s*[/／]\s*([0-9]+)',entry[1])
        if match and 0<int(match[1])<10000:return int(match[1])
    return None
