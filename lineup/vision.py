"""Grayscale grid geometry and independently recognized formation controls."""
from dataclasses import dataclass, field
import hashlib
import re
from functools import lru_cache
import cv2
import numpy as np
from autotata.paths import ASSETS
from .recognition import identify, read_image


@dataclass
class Grid:
    rect: tuple
    columns: int
    rows: int
    score: float = 0.

    def center(self, index):
        x,y,w,h = self.rect; row,col = divmod(index,self.columns)
        return (x+(col+.5)*w/self.columns,y+(row+.5)*h/self.rows)

    def tile(self, index, padding=.05):
        x,y,w,h = self.rect; row,col = divmod(index,self.columns)
        cw,ch = w/self.columns,h/self.rows
        return (round(x+(col+padding)*cw),round(y+(row+padding)*ch),
                round(x+(col+1-padding)*cw),round(y+(row+1-padding)*ch))


def grayscale_grid(image, columns=5, rows=5, hint=None, cancel=None):
    """Find repeated square borders or checker steps, exclusively in grayscale."""
    gray = cv2.cvtColor(image[:,:,:3],cv2.COLOR_BGR2GRAY)
    h,w = gray.shape
    candidates = []
    # Rounded reference cells have complete repeated rectangular borders.
    edges = cv2.Canny(gray,25,75)
    contours,_ = cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x,y,bw,bh = cv2.boundingRect(contour)
        if max(18,w*.07) <= bw <= w*.27 and .78 <= bw/bh <= 1.22:
            boxes.append((x,y,bw,bh))
    for x,y,bw,bh in (boxes if hint is None else []):
        if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
        for step in (bw,bw+3,bw+5):
            for col in range(columns):
                for row in range(rows):
                    bx,by = x-col*step,y-row*step
                    if bx<0 or by<0 or bx+columns*step>w or by+rows*step>h: continue
                    matched = sum(any(abs(xx-(bx+c*step))<5 and abs(yy-(by+r*step))<5 and abs(ww-bw)<5
                                      for xx,yy,ww,hh in boxes) for r in range(rows) for c in range(columns))
                    if matched >= max(6,rows*columns*.42):
                        candidates.append(Grid((bx,by,columns*step,rows*step),columns,rows,matched/(rows*columns)))
    if candidates:
        return max(candidates,key=lambda g:(g.score,g.rect[2]*g.rect[3]))
    if hint is None:
        return None
    # Live checkerboard: estimate width/bottom near independently found controls.
    # Maximize repeated grayscale step edges; no hue or element color is used.
    hx,hy,hw,hh = hint
    rr,cc=np.indices((rows,columns));rr=rr.ravel();cc=cc.ravel()
    parity=(rr+cc)%2==0
    dx=np.array((.12,.88,.12,.88));dy=np.array((.12,.12,.88,.88))
    pixels=gray.astype(np.float32)
    for size in np.arange(hw/columns*.96,hw/columns*1.05,1):
        bw,bh = round(size*columns),round(size*rows)
        for bx in range(max(0,round(hx-16)),min(w-bw,round(hx+16))+1,3):
            for by in range(max(0,round(hy-16)),min(h-bh,round(hy+16))+1,3):
                # Independently recognized controls anchor the board's center
                # and bottom. Large sprites must not expand/shift the field.
                if abs(bx+bw/2-(hx+hw/2))>4 or abs(by+bh-(hy+hh))>5:continue
                # Sample corners: deployed portraits occupy cell centers and
                # must not pull the grid toward their stronger outline edges.
                xs=np.rint(bx+(cc[:,None]+dx)*size).astype(int)
                ys=np.rint(by+(rr[:,None]+dy)*size).astype(int)
                samples=sum(pixels[np.minimum(ys+oy,h-1),np.minimum(xs+ox,w-1)] for ox in range(3) for oy in range(3))/9
                values=np.median(samples,axis=1);even,odd=values[parity],values[~parity]
                contrast=abs(float(np.median(even)-np.median(odd)))
                scatter=float(np.median(abs(even-np.median(even)))+np.median(abs(odd-np.median(odd))))
                score=contrast-.6*scatter-.02*(abs(bx-hx)+abs(by-hy))-.10*abs(size-hw/columns)
                candidates.append(Grid((bx,by,bw,bh),columns,rows,score))
    best = max(candidates,key=lambda g:g.score,default=None)
    return best if best and best.score>4 else None


def inventory_boxes(game, top, bottom):
    gray = cv2.cvtColor(game,cv2.COLOR_BGR2GRAY)
    mask = cv2.inRange(gray,0,65)
    contours,_ = cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        # Adjacent rows can share a black border, producing one tall contour
        # per column. Split only when both the aspect and middle rail agree.
        if y>=top and y+h<=bottom and 65<=w<=120 and 160<=h<=300 and .8<=h/(2*w)<=1.5:
            middle=y+h//2
            rails=[yy for yy in range(middle-4,middle+5)
                   if np.mean(mask[yy,x:x+w]>0)>=.75]
            if rails:
                seam=min(rails,key=lambda yy:abs(yy-middle))
                found.extend(((x,y,w,seam-y),(x,seam,w,y+h-seam)))
                continue
        if y>=top and y+h<=bottom and 65<=w<=120 and 80<=h<=150 and .65<=w/h<=1.2:
            if not any(abs(x-a)<6 and abs(y-b)<6 for a,b,_,_ in found): found.append((x,y,w,h))
    # A split outer frame also contains portrait/checkmark contours. Those
    # interior rectangles must not create extra columns or jitter the lattice.
    found=[b for b in found if not any(
        a!=b and a[2]*a[3]>b[2]*b[3]*1.12
        and a[0]-3<=b[0] and a[1]-5<=b[1]
        and b[0]+b[2]<=a[0]+a[2]+3 and b[1]+b[3]<=a[1]+a[3]+5
        for a in found)]
    # Borders can be faded or obscured by artwork. Recover missing full cards
    # only from a supported, regular row lattice; never drag a clipped edge card.
    rows=[]
    for box in sorted(found,key=lambda b:(b[1],b[0])):
        row=next((r for r in rows if abs(r[0][1]-box[1])<8),None)
        if row is None:rows.append([box])
        else:row.append(box)
    complete=[];lattices=[]
    for row in rows:
        row.sort();xs=np.array([b[0] for b in row])
        if len(xs)<3:complete.extend(row);continue
        bw=round(np.median([b[2] for b in row]));bh=round(np.median([b[3] for b in row]));gaps=np.diff(xs)
        adjacent=gaps[(gaps>=bw+4)&(gaps<=bw+25)]
        if not len(adjacent):complete.extend(row);continue
        pitch=float(np.median(adjacent));multiples=np.rint(gaps/pitch)
        if max(abs(gaps-multiples*pitch))>6 or max(multiples)>3:
            complete.extend(row);continue
        origin=float(np.median(xs-np.rint((xs-xs[0])/pitch)*pitch));y=round(np.median([b[1] for b in row]))
        start=origin-np.floor(origin/pitch)*pitch
        lattices.append((len(row),start,pitch,bw,bh))
        for x in np.arange(start,game.shape[1]-bw-4,pitch):complete.append((round(x),y,bw,bh))
    if lattices:
        # Both inventory rows share columns. Artwork sometimes breaks a border
        # inward, making one row's apparent first gap too short. Anchor it to the
        # independently supported other row instead of dropping its last card.
        _,start,pitch,bw,bh=max(lattices)
        aligned=[]
        for row in rows:
            good=[b for b in row if abs(b[0]-(start+round((b[0]-start)/pitch)*pitch))<=pitch*.15
                  and abs(b[2]-bw)<=bw*.18 and abs(b[3]-bh)<=bh*.18]
            if len(good)>=2 and len(good)>=len(row)*.8:
                y=round(np.median([b[1] for b in good]))
                aligned.extend((round(x),y,bw,bh) for x in np.arange(start,game.shape[1]-bw-4,pitch))
            else:aligned.extend(b for b in complete if abs(b[1]-row[0][1])<8)
        complete=aligned
    return sorted(complete,key=lambda b:(round(b[1]/35),b[0]))


def inventory_lane(game, top):
    """White list margin verified in pixels, rather than swiping the count bar."""
    gray=cv2.cvtColor(game,cv2.COLOR_BGR2GRAY)
    ys=[]
    for y in range(max(0,top-16),top):
        stripe=gray[y,round(game.shape[1]*.2):round(game.shape[1]*.8)]
        if stripe.mean()>210 and stripe.std()<20:ys.append(y)
    return ys[len(ys)//2] if len(ys)>=3 else None


@lru_cache(maxsize=1)
def badge_shapes():
    return {key:cv2.cvtColor(read_image(ASSETS/'lineup/filters'/f'{key}.png'),cv2.COLOR_BGR2GRAY)
            for key in ('rock','lightning')}


def badge_element(game, box):
    """Read the independent top-left element badge, never the portrait hue."""
    x,y,w,h=box
    roi=game[max(0,y-2):y+18,max(0,x-2):x+18]
    hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
    hue,saturation,value=cv2.split(hsv);valid=(saturation>110)&(value>55)
    masks={'water':(hue>=90)&(hue<=125),'fire':(hue<=8)|(hue>=170),
           'grass':(hue>=35)&(hue<=85),'rock':(hue>8)&(hue<23)&(value<215),
           'lightning':(hue>=18)&(hue<35)&(value>=215)}
    scores=sorted(((int(np.sum(valid&m)),k) for k,m in masks.items()),reverse=True)
    result=scores[0][1] if scores[0][0]>=20 and scores[0][0]>scores[1][0]*1.5 else None
    # Deployed cards are dimmed: a yellow bolt's brightness then overlaps rock.
    # Compare the actual white symbol with normalized grayscale templates,
    # rather than relaxing the element majority or trusting the selected tab.
    if result in ('rock','lightning'):
        gray=cv2.cvtColor(game[max(0,y-5):y+27,max(0,x-5):x+27],cv2.COLOR_BGR2GRAY)
        shapes=[]
        for key,template in badge_shapes().items():
            best=0.
            for size in range(15,23):
                if min(gray.shape)<size:continue
                t=cv2.resize(template,(size,size))
                best=max(best,float(cv2.minMaxLoc(cv2.matchTemplate(gray,t,cv2.TM_CCOEFF_NORMED))[1]))
            shapes.append((best,key))
        shapes.sort(reverse=True)
        if shapes[0][0]>=.78 and shapes[0][0]-shapes[1][0]>=.08:result=shapes[0][1]
    return result


def card_reference_grid(image,columns=5,rows=5):
    grid=card_border_grid(image,columns,rows)
    if grid is not None:return grid
    return card_lattice_grid(image,columns,rows)


def card_border_grid(image,columns=5,rows=5):
    """Repeated card borders, independent of portrait hue and star count."""
    gray=cv2.cvtColor(image[:,:,:3],cv2.COLOR_BGR2GRAY);height,width=gray.shape
    contours,_=cv2.findContours(cv2.inRange(gray,0,75),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[cv2.boundingRect(c) for c in contours]
    boxes=[b for b in boxes if width*.12<b[2]<width*.30 and 1.12<b[3]/b[2]<1.5]
    best=max(([b for b in boxes if abs(b[2]-a[2])<3 and abs(b[3]-a[3])<3] for a in boxes),key=len,default=[])
    if len(best)<8:return None
    def clustered(values):
        result=[]
        for value in sorted(values):
            if not result or value-result[-1]>5:result.append(value)
        return result
    xs=clustered([b[0] for b in best]);ys=clustered([b[1] for b in best])
    if len(xs)!=columns or len(ys)<3:return None
    dx=float(np.median(np.diff(xs)));dy=float(np.median(np.diff(ys)))
    if max(abs(np.diff(xs)-dx))>5 or max(abs(np.diff(ys)-dy))>5:return None
    rect=(xs[0]-3,ys[0]-3,dx*columns,dy*rows)
    if min(rect[:2])<0 or rect[0]+rect[2]>width or rect[1]+rect[3]>height:return None
    return Grid(rect,columns,rows,.9)


def card_lattice_grid(image,columns=5,rows=5):
    """Fit card centers even when evolution decorations enlarge outer borders.

    Require a complete set of row and column centers, regular spacing and at
    least ten distinct occupied cells. Inner portrait frames cannot substitute
    for missing rows, and empty cells keep their original lattice positions.
    """
    gray=cv2.cvtColor(image[:,:,:3],cv2.COLOR_BGR2GRAY);height,width=gray.shape
    contours,_=cv2.findContours(cv2.inRange(gray,0,75),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[cv2.boundingRect(c) for c in contours]
    boxes=[b for b in boxes if 18<b[2]<width*.30 and 1.10<b[3]/b[2]<1.5]
    best=max(([b for b in boxes if abs(b[2]-a[2])<a[2]*.10 and abs(b[3]-a[3])<a[3]*.10] for a in boxes),key=len,default=[])
    if len(best)<10:return None
    def clustered(values,tolerance):
        groups=[]
        for value in sorted(values):
            if not groups or value-groups[-1][-1]>tolerance:groups.append([value])
            else:groups[-1].append(value)
        return [float(np.median(group)) for group in groups]
    xs=clustered([x+w/2 for x,y,w,h in best],max(4,float(np.median([b[2] for b in best]))*.06))
    ys=clustered([y+h/2 for x,y,w,h in best],max(4,float(np.median([b[3] for b in best]))*.06))
    if len(xs)!=columns or len(ys)!=rows:return None
    dx=float(np.median(np.diff(xs)));dy=float(np.median(np.diff(ys)))
    if max(abs(np.diff(xs)-dx))>dx*.06 or max(abs(np.diff(ys)-dy))>dy*.06:return None
    if not 1.05<dy/dx<1.5:return None
    cells={(int(np.argmin(abs(np.asarray(xs)-(x+w/2)))),int(np.argmin(abs(np.asarray(ys)-(y+h/2))))) for x,y,w,h in best}
    if len(cells)<10:return None
    rect=(xs[0]-dx/2,ys[0]-dy/2,dx*columns,dy*rows)
    if min(rect[:2])<0 or rect[0]+rect[2]>width or rect[1]+rect[3]>height:return None
    return Grid(rect,columns,rows,.9)


def checker_reference_grid(image,columns=5,rows=5,cancel=None):
    """Locate a borderless reference panel using repeated grayscale shading.

    The panel supplies side bounds only. Its header/footer are not rows; scan
    the vertical phase and require consistent checker contrast in both axes.
    Artwork is excluded by sampling cell corners instead of sprite centers.
    """
    gray=cv2.cvtColor(image[:,:,:3],cv2.COLOR_BGR2GRAY);height,width=gray.shape
    contours,_=cv2.findContours(cv2.Canny(gray,10,30),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    panels=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if w>=width*.65 and h>=w*rows/columns*.82 and h<=w*rows/columns*1.8:
            if not any(abs(x-a)+abs(y-b)+abs(w-c)<8 for a,b,c,_ in panels):panels.append((x,y,w,h))
    if not panels and width*rows/columns*.82<=height<=width*rows/columns*1.8:
        panels=[(0,0,width,height)]
    rr,cc=np.indices((rows,columns));rr=rr.ravel();cc=cc.ravel();parity=(rr+cc)%2==0
    dx=np.array((.08,.92,.08,.92));dy=np.array((.08,.08,.92,.92))
    pixels=cv2.blur(gray,(3,3)).astype(np.float32);best=None
    smooth_pixels=cv2.morphologyEx(gray,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))<10
    # Keep the established square-board path first. Shared screenshots can
    # compress the vertical axis while retaining the complete five-row board.
    # Such boards need independent cell height and dense background support;
    # corner samples alone can mistake sprites or the river for a shifted row.
    for aspects in ((1.,),tuple(np.arange(.84,1.,.02))+tuple(np.arange(1.02,1.13,.02))):
        for left,top,pw,ph in panels:
            for size,aspect in ((s,a) for s in np.arange(pw/columns*.96,pw/columns+1,.6) for a in aspects):
                if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
                cell_height=size*aspect;bw,bh=round(size*columns),round(cell_height*rows)
                for x in range(max(0,left-2),min(width-bw,left+6)+1,2):
                    ys=np.arange(max(0,top),min(height-bh,top+ph-bh)+1,2)
                    if not len(ys):continue
                    sx=np.rint(x+(cc[:,None]+dx)*size).astype(int)
                    sy=np.rint(ys[:,None,None]+(rr[None,:,None]+dy)*cell_height).astype(int)
                    values=np.percentile(pixels[sy,sx[None,:,:]],75,axis=2)
                    even,odd=values[:,parity],values[:,~parity]
                    em,om=np.median(even,axis=1),np.median(odd,axis=1)
                    contrast=abs(em-om)
                    scatter=np.median(abs(even-em[:,None]),axis=1)+np.median(abs(odd-om[:,None]),axis=1)
                    scores=contrast-.6*scatter
                    for k in np.argsort(scores)[-3:]:
                        if scores[k]<4 or contrast[k]<5:continue
                        sign=np.sign(em[k]-om[k]);matrix=values[k].reshape(rows,columns)
                        row_support=sum(sign*(np.median(matrix[r,(np.arange(columns)+r)%2==0])-np.median(matrix[r,(np.arange(columns)+r)%2!=0]))>2 for r in range(rows))
                        col_support=sum(sign*(np.median(matrix[(np.arange(rows)+c)%2==0,c])-np.median(matrix[(np.arange(rows)+c)%2!=0,c]))>2 for c in range(columns))
                        if row_support<rows-1 or col_support<columns-1:continue
                        score=float(scores[k])
                        yy,xx=np.mgrid[int(ys[k]):int(ys[k])+bh:3,x:x+bw:3]
                        sample=pixels[yy,xx]
                        # A local grayscale mode removes dark artwork and
                        # high-contrast edges without relying on board hue.
                        smooth=smooth_pixels[yy,xx]
                        levels=sample[smooth].astype(np.uint8)
                        if levels.size<100:continue
                        histogram=np.bincount(levels,minlength=256);histogram[:30]=0;histogram[240:]=0
                        mode=int(histogram.argmax());valid=smooth&(abs(sample-mode)<18)
                        parity_sample=((xx-x)*columns//bw+(yy-int(ys[k]))*rows//bh)%2==0
                        a,b=sample[valid&parity_sample],sample[valid&~parity_sample]
                        if min(a.size,b.size)<100:continue
                        am,bm=np.median(a),np.median(b);delta=abs(am-bm)
                        score=float(delta-np.mean(np.minimum(abs(a-am),15))-np.mean(np.minimum(abs(b-bm),15)))
                        if delta<5 or score<3:continue
                        if aspects==(1.,):score=float(scores[k])
                        candidate=Grid((x,int(ys[k]),bw,bh),columns,rows,score)
                        if best is None or candidate.score>best.score:best=candidate
        if best is not None:break
    if best is None and columns==5 and rows==5:
        best=cropped_checker_grid(image,cancel)
        if best is None or best.rect[3]>best.rect[2]*1.08:
            local=local_checker_grid(image,cancel)
            # Both fallback scores measure the same fraction of smooth checker
            # evidence. Extra scenery must not stretch five rows into terrain.
            if local is not None and (best is None or local.score>best.score+.08):best=local
    return best


def cropped_checker_grid(image,cancel=None):
    """Recover a tightly cropped square board when portraits cover its corners.

    Only smooth pixels near the two dominant background levels vote. Require
    alternating support across every row and column, including the empty rows;
    sprite outlines and scenery cannot define the grid by themselves.
    """
    height,width=image.shape[:2]
    if min(height,width)<100 or not .88<=height/width<=1.14:return None
    scale=min(1.,320/width)
    gray=cv2.cvtColor(image[:,:,:3],cv2.COLOR_BGR2GRAY)
    if scale<1:gray=cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    height,width=gray.shape
    smooth=cv2.morphologyEx(gray,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))<10
    histogram=np.bincount(gray[smooth],minlength=256);histogram[:30]=0;histogram[240:]=0
    first=int(histogram.argmax());other=histogram.copy()
    other[max(0,first-4):first+5]=0
    other[:max(0,first-18)]=0;other[first+19:]=0
    second=int(other.argmax())
    if min(histogram[first],other[second])<height*width*.03:return None
    low,high=sorted((first,second));pixels=gray.astype(float)
    valid=smooth&(np.minimum(abs(pixels-low),abs(pixels-high))<=2)
    evidence=np.where(valid,np.where(pixels>(low+high)/2,1.,-1.),0.)
    integral=cv2.integral(evidence);area=cv2.integral(valid.astype(float))
    rr,cc=np.indices((5,5));rr=rr.ravel();cc=cc.ravel()
    parity=np.where((rr+cc)%2==0,1.,-1.);best=None
    for bw in range(round(width*.88),width+1,2):
        if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
        for bh in range(max(round(bw*.88),round(height*.88)),min(height,round(bw*1.12))+1,2):
            xx,yy=np.meshgrid(np.arange(0,width-bw+1,2),np.arange(0,height-bh+1,2))
            xs=xx.ravel()[:,None];ys=yy.ravel()[:,None]
            x0=np.rint(xs+cc*bw/5).astype(int);x1=np.rint(xs+(cc+1)*bw/5).astype(int)
            y0=np.rint(ys+rr*bh/5).astype(int);y1=np.rint(ys+(rr+1)*bh/5).astype(int)
            sums=integral[y1,x1]-integral[y0,x1]-integral[y1,x0]+integral[y0,x0]
            counts=area[y1,x1]-area[y0,x1]-area[y1,x0]+area[y0,x0]
            signed=sums*parity;sign=np.sign(signed.sum(axis=1))
            strength=signed*sign[:,None]/np.maximum(counts,1)
            support=(strength>.2).reshape(-1,5,5)
            eligible=((support.sum(axis=1).min(axis=1)>=3)&(support.sum(axis=2).min(axis=1)>=3)
                      &((counts>bw*bh/25*.10).sum(axis=1)>=20))
            scores=(signed*sign[:,None]).sum(axis=1)/(bw*bh);scores[~eligible]=-1
            k=int(scores.argmax());score=float(scores[k])
            if score>=.30 and (best is None or score>best.score):
                best=Grid(tuple(v/scale for v in (int(xs[k,0]),int(ys[k,0]),bw,bh)),5,5,score)
    return best


def local_checker_grid(image,cancel=None):
    """Find a player board inside scenery, UI or a larger desktop capture.

    Propose connected regions of the two smooth checker levels, then verify
    all five rows/columns on original pixels. The lower boundary of a region
    anchors the player's five rows when extra checker rows extend above them.
    Separate plausible boards remain ambiguous and require manual selection.
    """
    if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
    ratio=min(1.,800/max(image.shape[:2]))
    sample=cv2.resize(image,None,fx=ratio,fy=ratio,interpolation=cv2.INTER_AREA) if ratio<1 else image
    gray=cv2.cvtColor(sample[:,:,:3],cv2.COLOR_BGR2GRAY);pixels=gray.astype(float)
    height,width=gray.shape
    smooth=cv2.morphologyEx(gray,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))<10
    histogram=np.bincount(gray[smooth],minlength=256);histogram[:30]=0;histogram[240:]=0
    peaks=[];remaining=histogram.copy()
    for _ in range(12):
        level=int(remaining.argmax())
        if remaining[level]<max(10,height*width*.0005):break
        peaks.append(level);remaining[max(0,level-3):level+4]=0
    boxes=[]
    for low in peaks:
        for high in peaks:
            if not 5<=high-low<=18:continue
            if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
            mask=(smooth&(np.minimum(abs(pixels-low),abs(pixels-high))<=2)).astype(np.uint8)
            joined=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
            _,_,stats,_=cv2.connectedComponentsWithStats(joined)
            for x,y,w,h,area in stats[1:]:
                if w<50 or h<w*.85 or h>w*3 or area<w*h*.20:continue
                rect=(int(x),int(y),int(w),int(h))
                if not any(max(abs(v-u) for v,u in zip(rect,old))<6 for old in boxes):boxes.append(rect)
    candidates=[]
    for x,y,w,h in boxes:
        if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
        top=y+h-min(h,w)
        left=max(0,round((x-2)/ratio));right=min(image.shape[1],round((x+w+2)/ratio))
        top=max(0,round((top-2)/ratio));bottom=min(image.shape[0],round((y+h+2)/ratio))
        grid=cropped_checker_grid(image[top:bottom,left:right],cancel)
        if grid is not None:
            gx,gy,gw,gh=grid.rect
            candidates.append(Grid((gx+left,gy+top,gw,gh),5,5,grid.score))
    if not candidates:return None
    best=max(candidates,key=lambda g:g.score)
    x,y,w,h=best.rect
    for other in candidates:
        a,b,c,d=other.rect
        overlap=max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b))
        if other.score>=best.score*.85 and overlap/min(w*h,c*d)<.30:return None
    return best


def narrow_reference_grid(image,cancel=None):
    """3×4 player lane, anchored by the clear icon or both enclosing rails.

    Evaluate square checker cells in grayscale. The bottom anchor excludes the
    opposing team in a full screenshot; bilateral rails exclude scenery grids.
    """
    scale=image.shape[1]/540
    game=cv2.resize(image[:,:,:3],(540,round(image.shape[0]/scale)))
    gray=cv2.cvtColor(game,cv2.COLOR_BGR2GRAY);height,width=gray.shape
    best_icon=(0,None)
    for name in ('clear-five.png',):
        template=read_image(ASSETS/'lineup'/name)
        if template is None:continue
        for factor in (.75,1.,1.25):
            t=cv2.resize(cv2.cvtColor(template[:,:,:3],cv2.COLOR_BGR2GRAY),None,fx=factor,fy=factor)
            top=round(height*.45);roi=gray[top:,420:]
            if roi.shape[0]<len(t) or roi.shape[1]<t.shape[1]:continue
            _,score,_,p=cv2.minMaxLoc(cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED))
            if score>best_icon[0]:best_icon=(score,top+p[1]+len(t)/2)
    anchored=best_icon[0]>=.88
    if not anchored and not .85<=height/width<=1.8:return None
    bottoms=np.arange(round(best_icon[1]-28),round(best_icon[1]+5),2) if anchored else np.arange(round(height*.84),round(height*.98),2)
    pixels=cv2.blur(gray,(3,3)).astype(np.float32)
    rr,cc=np.indices((4,3));rr=rr.ravel();cc=cc.ravel();parity=(rr+cc)%2==0
    dx=np.array((.10,.90,.10,.90));dy=np.array((.10,.10,.90,.90))
    best=None
    for size in np.arange(44 if anchored else 65,88 if anchored else 130,1):
        if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
        for left in range(max(0,round(270-3*size/2-26)),min(width-round(3*size),round(270-3*size/2+26))+1,2):
            tops=bottoms-4*size;valid=(tops>=0)&(bottoms<height)
            ys=tops[valid]
            if not len(ys):continue
            sx=np.rint(left+(cc[:,None]+dx)*size).astype(int)
            sy=np.rint(ys[:,None,None]+(rr[None,:,None]+dy)*size).astype(int)
            values=np.median(pixels[sy,sx[None,:,:]],axis=2)
            even,odd=values[:,parity],values[:,~parity]
            em,om=np.median(even,axis=1),np.median(odd,axis=1)
            contrast=abs(em-om);scatter=np.median(abs(even-em[:,None]),axis=1)+np.median(abs(odd-om[:,None]),axis=1)
            scores=contrast-.6*scatter
            for k in np.argsort(scores)[-2:]:
                if contrast[k]<5 or scores[k]<4:continue
                sign=np.sign(em[k]-om[k]);matrix=values[k].reshape(4,3)
                row_support=sum(sign*(np.median(matrix[r,(np.arange(3)+r)%2==0])-np.median(matrix[r,(np.arange(3)+r)%2!=0]))>2 for r in range(4))
                col_support=sum(sign*(np.median(matrix[(np.arange(4)+c)%2==0,c])-np.median(matrix[(np.arange(4)+c)%2!=0,c]))>2 for c in range(3))
                if row_support<3 or col_support<3:continue
                top=int(ys[k]);bottom=round(top+4*size);right=round(left+3*size)
                edges=np.median(abs(np.diff(pixels[top:bottom],axis=1)),axis=0)
                rails=min(float(edges[max(0,left-5):left+6].max()),float(edges[right-6:min(width-1,right+5)].max()))
                if rails<4:continue
                # Flat cell interiors permit several equally good phases. Fit
                # the internal step edges as well so portraits do not move the
                # inferred origins a quarter of a cell toward their outlines.
                horizontal=np.median(abs(np.diff(pixels[top:bottom,left:right],axis=0)),axis=1)
                vertical=[float(edges[round(left+c*size)-2:round(left+c*size)+3].max()) for c in (1,2)]
                across=[float(horizontal[round(r*size)-2:round(r*size)+3].max()) for r in (1,2,3)]
                step_support=float(np.median(vertical)+np.median(across))
                score=float(scores[k])+min(rails,25)*.35+step_support*2
                candidate=Grid(tuple(v*scale for v in (left,top,3*size,4*size)),3,4,score)
                if best is None or score>best.score:best=candidate
    return best


@dataclass
class Observation:
    state: str = 'unknown'
    multiplier: int | None = None  # Shared device/display selection interface.
    grid: Grid | None = None
    count: int | None = None
    limit: int | None = None
    clear: tuple | None = None
    cards: list = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    inventory_rect: tuple | None = None
    scroll_line: float | None = None
    scale: float = 1.
    count_y: float | None = None


def occupied_cell(frame,grid,index,center_required=True):
    x,y,right,bottom=grid.tile(index,.10)
    gray=cv2.cvtColor(frame[y:bottom,x:right,:3],cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,45,100)
    if edges.mean()/255<.035 or np.mean(gray<40)<.008:return False
    if not center_required:return True
    # A neighbor's tail, head or approval badge can cross a cell edge. Require
    # outline pixels in the central half as well before treating it as a unit.
    x,y,right,bottom=grid.tile(index,.25)
    center=cv2.cvtColor(frame[y:bottom,x:right,:3],cv2.COLOR_BGR2GRAY)
    return np.mean(center<40)>=.008


class Vision:
    def __init__(self,crop_top=0,crop_bottom=0):
        self.ocr = None; self.crop_top=crop_top;self.crop_bottom=crop_bottom
        self.count_cache=None
        self.unit_cache={}
        self.filter_cache=None
        self.clear_templates = [read_image(ASSETS/'lineup'/name) for name in ('clear-five.png','clear-fifteen.png')]
        self.filter_templates={p.stem:read_image(p) for p in (ASSETS/'lineup/filters').glob('*.png')}

    def unit(self,frame,obs,index,expected=None,allowed_ids=None):
        """Allow a sprite to extend beyond its tile, but reject adjacent sprites."""
        x,y,right,bottom=obs.grid.tile(index,-.30)
        patch=frame[max(0,y):min(frame.shape[0],bottom),max(0,x):min(frame.shape[1],right),:3]
        key=(obs.grid.rect,obs.grid.columns,obs.grid.rows,index,expected,tuple(sorted(allowed_ids)) if allowed_ids is not None else None,patch.shape,hashlib.sha256(patch.tobytes()).digest())
        if key in self.unit_cache:return self.unit_cache[key]
        result=self._unit(frame,obs,index,expected,allowed_ids)
        if len(self.unit_cache)>=128:self.unit_cache.clear()
        self.unit_cache[key]=result
        return result

    def _unit(self,frame,obs,index,expected=None,allowed_ids=None):
        best={'id':'?','score':0.,'candidates':[]}
        probe=allowed_ids is not None and expected is None
        for padding in ((-.15,) if probe else (-.15,0,-.30)):
            x,y,right,bottom=obs.grid.tile(index,padding)
            x,y=max(0,x),max(0,y);right,bottom=min(frame.shape[1],right),min(frame.shape[0],bottom)
            cx,cy=obs.grid.center(index);cw=obs.grid.rect[2]/obs.grid.columns;ch=obs.grid.rect[3]/obs.grid.rows
            region=(cx-cw*.4-x,cy-ch*.4-y,cx+cw*.4-x,cy+ch*.4-y)
            allowed={expected} if expected else allowed_ids
            result=identify(frame[y:bottom,x:right,:3],allowed_ids=allowed,center_region=region,animated=True)
            if result['id']!='?':return result
            if result['score']>best['score']:best=result
            # Retry a plausible body on a neutral surface before expanding the
            # crop again. Weak outlines and empty neighbors skip this extra pass.
            if not probe and (result['score']>=.60 or expected is not None or (obs.grid.columns==3 and padding==-.30)):
                rendered=identify(frame[y:bottom,x:right,:3],allowed_ids=allowed,center_region=region,animated=True,background=180)
                if rendered['id']!='?':return rendered
                if rendered['score']>best['score']:best=rendered
        return best

    def board(self,frame,obs,check=None,preferred_ids=None):
        """Read only the player's grayscale grid, excluding enemies and inventory."""
        if not obs.count:return []
        units=[]
        for index in range(obs.grid.columns*obs.grid.rows):
            if check:check()
            # Empty live cells are softly shaded; characters have dark outlines.
            if not occupied_cell(frame,obs.grid,index):continue
            result=self.unit(frame,obs,index,allowed_ids=preferred_ids) if preferred_ids else None
            if result is None or result['id']=='?' or result['score']<.90:
                result=self.unit(frame,obs,index)
            units.append({'index':index,**result})
        return units

    def find_filters(self,game,top,bottom):
        gray=cv2.cvtColor(game,cv2.COLOR_BGR2GRAY);roi=gray[top:bottom];found={}
        cached=self.filter_cache
        if cached is not None and cached[:2]==(top,bottom) and np.array_equal(cached[2],roi):return dict(cached[3])
        for key,template in self.filter_templates.items():
            t=cv2.cvtColor(template,cv2.COLOR_BGR2GRAY);best=(0,None)
            for factor in (.9,1.,1.1):
                resized=cv2.resize(t,None,fx=factor,fy=factor)
                if roi.shape[0]<resized.shape[0] or roi.shape[1]<resized.shape[1]:continue
                _,score,_,p=cv2.minMaxLoc(cv2.matchTemplate(roi,resized,cv2.TM_CCOEFF_NORMED))
                if score>best[0]:best=(score,(p[0]+resized.shape[1]/2,top+p[1]+resized.shape[0]/2))
            if best[0]>=.88:found[key]=best[1]
        elements=[found.get(k) for k in ('water','fire','grass','rock','lightning')]
        if any(p is None for p in elements):
            self.filter_cache=(top,bottom,roi.copy(),{});return {}
        xs=[p[0] for p in elements];ys=[p[1] for p in elements]
        if max(ys)-min(ys)>5 or not all(50<d<90 for d in np.diff(xs)):return {}
        self.filter_cache=(top,bottom,roi.copy(),dict(found))
        return found

    def text(self,roi):
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
        result,_=self.ocr(cv2.resize(roi,None,fx=2,fy=2))
        return result or []

    def observe(self,frame,read_cards=False,grid_hint=None):
        h,w=frame.shape[:2]; scale=w/540
        bottom=h-self.crop_bottom
        if self.crop_top<0 or self.crop_bottom<0 or self.crop_top>=bottom:return Observation(scale=scale)
        game=cv2.resize(frame[self.crop_top:bottom],(540,round((bottom-self.crop_top)/scale)))
        gh=len(game); gray=cv2.cvtColor(game,cv2.COLOR_BGR2GRAY)
        obs=Observation(scale=scale)
        best=(0.,None)
        for template in self.clear_templates:
            if template is None: continue
            tgray=cv2.cvtColor(template[:,:,:3],cv2.COLOR_BGR2GRAY)
            for factor in (.75,1.,1.25):
                t=cv2.resize(tgray,None,fx=factor,fy=factor)
                roi=gray[round(gh*.42):round(gh*.68),420:]
                if roi.shape[0]<len(t) or roi.shape[1]<t.shape[1]:continue
                _,confidence,_,position=cv2.minMaxLoc(cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED))
                if confidence>best[0]:best=(confidence,(420+position[0]+t.shape[1]/2,round(gh*.42)+position[1]+t.shape[0]/2))
        if best[0]<.78:return obs
        cx,cy=best[1]
        # Extra mode/settings buttons can move the clear control up a row.
        # Locate the labeled count in the lower UI independently of that icon.
        y0=round(gh*.45); y1=round(gh*.78)
        cache=self.count_cache
        if cache is not None:
            shape,clear,strip_rect,strip,old_count,old_limit,old_bar=cache
            sx,sy,sw,sh=strip_rect
            if (shape==game.shape and np.linalg.norm(np.subtract(clear,(cx,cy)))<=1.5
                    and np.array_equal(game[sy:sy+sh,sx:sx+sw],strip)):
                words=None;count,limit,bar=old_count,old_limit,old_bar
            else:words=self.text(game[y0:y1,:])
        else:words=self.text(game[y0:y1,:])
        lines=[]
        for box,text,confidence in words or []:
            if confidence<.60:continue
            top=float(np.min(np.asarray(box)[:,1]))/2+y0
            lines.append((top,text))
        # Never concatenate unrelated inventory numbers with the limit.
        matches=[(y,re.search(r'(?:上阵|阵塔|阵容).*?(\d+)\s*[/／]\s*(\d+)',t)) for y,t in lines]
        if words is not None:
            match=next((m for _,m in matches if m),None)
            if not match:self.count_cache=None;return obs
            count,limit=map(int,match.groups())
            if not 0<=count<=limit<=25:self.count_cache=None;return obs
            bar=next(y for y,m in matches if m)
            sy=max(0,round(bar-5));sh=min(gh-sy,32)
            self.count_cache=(game.shape,(cx,cy),(55,sy,300,sh),game[sy:sy+sh,55:355].copy(),count,limit,bar)
        columns=3 if limit<=5 else 5
        rows=4 if columns==3 else 5
        size=57 if columns==3 else 60
        # The labeled inventory separator anchors the field regardless of how
        # many right-side controls the current game mode displays.
        board_bottom=bar-(48 if columns==3 else 42)
        hint=(270-columns*size/2,board_bottom-rows*size,columns*size,rows*size)
        grid=None
        if grid_hint is not None:
            old,old_clear,old_limit,old_bar=grid_hint
            current_clear=(cx*scale,cy*scale+self.crop_top);current_bar=bar*scale+self.crop_top
            if old_limit==limit and old.columns==columns and old.rows==rows and np.linalg.norm(np.subtract(current_clear,old_clear))<=5*scale and (old_bar is None or abs(current_bar-old_bar)<=5*scale):
                rect=tuple((v-(self.crop_top if i==1 else 0))/scale for i,v in enumerate(old.rect))
                grid=Grid(rect,columns,rows,old.score)
        if grid is None:grid=grayscale_grid(game,columns,rows,hint)
        if grid is None:return obs
        # Inventory and controls prove this is deployment, not a battle screenshot.
        top=round(bar+27); end=gh-100
        filters=self.find_filters(game,round(bar+140),gh-75)
        if filters:end=min(end,round(min(p[1] for p in filters.values())-32))
        boxes=inventory_boxes(game,top,end)
        if not boxes and count==0 and not filters:return obs
        lane=inventory_lane(game,min(b[1] for b in boxes)) if boxes else None
        if boxes:
            top=min(b[1] for b in boxes);end=max(b[1]+b[3] for b in boxes)
        if lane is not None:top=lane-2
        obs.state='ready';obs.count=count;obs.limit=limit
        obs.count_y=bar*scale+self.crop_top
        obs.clear=(cx*scale,cy*scale+self.crop_top)
        obs.grid=Grid(tuple(v*scale+(self.crop_top if i==1 else 0) for i,v in enumerate(grid.rect)),columns,rows,grid.score)
        obs.inventory_rect=(0,top*scale+self.crop_top,w,(end-top)*scale)
        obs.scroll_line=lane*scale+self.crop_top if lane is not None else None
        obs.filters={key:(p[0]*scale,p[1]*scale+self.crop_top) for key,p in filters.items()}
        for x,y,bw,bh in boxes:
            card={'point':((x+bw*.70)*scale,(y+bh*.60)*scale+self.crop_top),'bounds':(x*scale,y*scale+self.crop_top,bw*scale,bh*scale),'element':badge_element(game,(x,y,bw,bh))}
            if read_cards:card.update(identify(game[y+round(bh*.16):y+round(bh*.84),x+4:x+bw-4]))
            obs.cards.append(card)
        return obs


def incomplete_reference(image):
    """Detect cropped battle rows from repeated approval badges, not identities.

    Their square pitch can prove that five rows do not fit in the picture.
    A genuinely compressed complete board has a different vertical pitch and
    must not be confused with missing rows. No missing row is invented.
    """
    height,width=image.shape[:2]
    if min(height,width)<100 or height>width*1.15:return False
    scale=min(1.,500/width)
    sample=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA) if scale<1 else image
    height,width=sample.shape[:2]
    hsv=cv2.cvtColor(sample[:,:,:3],cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(45,100,60),(95,255,255))
    mask|=cv2.inRange(hsv,(0,120,70),(10,255,255))
    mask|=cv2.inRange(hsv,(170,120,70),(179,255,255))
    _,_,stats,_=cv2.connectedComponentsWithStats(mask)
    points=[]
    for x,y,w,h,area in stats[1:]:
        if not width*.025<=w<=width*.075 or not .75<=w/h<=1.3 or not .30<=area/(w*h)<=.85:continue
        if np.mean(np.min(sample[y:y+h,x:x+w,:3],axis=2)>185)<.06:continue
        points.append((x+w/2,y+h/2,w))
    # This is a small reference-panel check. Unrelated desktop icons must not
    # create an unbounded lattice search before the normal board locator runs.
    if not 8<=len(points)<=48:return False
    points=np.asarray(points);diameter=np.median(points[:,2])
    points=points[abs(points[:,2]-diameter)<=diameter*.25,:2]
    for step in np.unique(np.round(abs(points[:,None,0]-points[None,:,0]),1)):
        if not width*.14<=step<=width*.22 or height>=step*4.8:continue
        for x in points[:,0]:
            columns=np.rint((points[:,0]-x)/step)
            horizontal=abs(points[:,0]-x-columns*step)<step*.075
            if horizontal.sum()<8:continue
            for y in points[horizontal,1]:
                row=np.rint((points[:,1]-y)/step)
                matched=horizontal&(abs(points[:,1]-y-row*step)<step*.075)
                cols=columns[matched];rows=row[matched]
                if (matched.sum()>=max(8,len(points)*.70) and len(set(cols))>=4
                        and np.ptp(cols)==4 and len(set(rows))>=3):return True
    return False


def import_formation(image,columns=5,rows=None,manual_rect=None,progress=None,cancel=None,cell_ready=None):
    rows=rows if rows is not None else (4 if columns==3 else 5)
    if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
    if columns==5 and rows==5:
        selection=image
        if manual_rect:
            mx,my,mw,mh=map(round,manual_rect)
            selection=image[max(0,my):my+mh,max(0,mx):mx+mw]
        if selection.size and incomplete_reference(selection):
            raise ValueError('截图缺少完整五行场地，请保留空行重新截图；框选不能把三四行当作五行')
    # Locate small boards before shrinking a large capture, so unrelated margins
    # cannot erase portrait details. Manual selections use their own resolution.
    located=None;located_borderless=False
    if manual_rect is None and columns==5 and rows==5 and max(image.shape[:2])>1200:
        located=card_reference_grid(image,columns,rows)
        if located is None:
            located=local_checker_grid(image,cancel);located_borderless=located is not None
    extent=manual_rect[2:] if manual_rect else located.rect[2:] if located is not None else image.shape[:2]
    ratio=min(1.,1200/max(extent))
    if ratio<1:
        image=cv2.resize(image,None,fx=ratio,fy=ratio,interpolation=cv2.INTER_AREA)
        if manual_rect:manual_rect=tuple(v*ratio for v in manual_rect)
        if located is not None:located=Grid(tuple(v*ratio for v in located.rect),columns,rows,located.score)
    grid=Grid(tuple(manual_rect),columns,rows,1.) if manual_rect else located or grayscale_grid(image,columns,rows,cancel=cancel)
    if grid is None and manual_rect is None:grid=card_reference_grid(image,columns,rows)
    borderless=located_borderless
    if grid is None and manual_rect is None and columns==3:
        grid=narrow_reference_grid(image,cancel);borderless=grid is not None
    if grid is None and manual_rect is None:
        grid=checker_reference_grid(image,columns,rows,cancel);borderless=grid is not None
    if grid is None:raise ValueError('未找到完整阵型格子，请在图片上框选阵型区域')
    if manual_rect:
        mx,my,mw,mh=map(round,manual_rect)
        selection=image[max(0,my):my+mh,max(0,mx):mx+mw]
        # A manual rectangle supplies geometry, not a different artwork style.
        # Battle sprites still require animated matching and center checks.
        borderless=(selection.size>0 and grayscale_grid(selection,columns,rows,cancel=cancel) is None
                    and card_reference_grid(selection,columns,rows) is None)
    compressed=(borderless and columns==5 and grid.rect[2]/columns<65
                and grid.rect[3]/rows<grid.rect[2]/columns*.94)
    def match(patch,center_region=None,**options):
        if compressed:
            height=round(patch.shape[0]*grid.rect[2]*rows/(grid.rect[3]*columns))
            stretch=height/patch.shape[0]
            patch=cv2.resize(patch,(patch.shape[1],height),interpolation=cv2.INTER_CUBIC)
            if center_region is not None:
                a,b,c,d=center_region;center_region=(a,b*stretch,c,d*stretch)
        return identify(patch,center_region=center_region,**options)
    cells=[]; details=[]
    gray=cv2.cvtColor(image[:,:,:3],cv2.COLOR_BGR2GRAY)
    gx,gy,gw,gh=map(round,grid.rect)
    small_reference=borderless and columns==5 and grid.rect[2]/columns<45
    dark_reference=small_reference and np.median(gray[gy:gy+gh,gx:gx+gw])<130
    dark_surface=borderless and columns==5 and np.median(gray[gy:gy+gh,gx:gx+gw])<130
    for index in range(columns*rows):
        if cancel is not None and cancel.is_set():raise RuntimeError('已停止识别')
        if progress:progress(index,columns*rows)
        x,y,right,bottom=grid.tile(index,.0);roi=image[y:bottom,x:right,:3]
        # Empty rounded cells/checker cells have little internal edge content.
        ex,ey,er,eb=grid.tile(index,.20 if borderless else .13)
        edges=cv2.Canny(gray[ey:eb,ex:er],20 if dark_reference else 45,45 if dark_reference else 100)
        # Pale bodies can have very few near-black pixels. Central texture
        # distinguishes them from a neighbor's outline entering a cell edge.
        cx0,cy0,cx1,cy1=grid.tile(index,.25)
        central_edges=cv2.Canny(gray[cy0:cy1,cx0:cx1],20,45)
        low_outline=np.mean(gray[ey:eb,ex:er]<(80 if dark_reference else 65 if compressed or small_reference else 50))<.01
        empty_center=central_edges.mean()/255<(.12 if low_outline else .015)
        if edges.mean()/255<(.015 if dark_reference else .035) or (borderless and ((columns==5 and empty_center) or (columns==3 and not occupied_cell(image,grid,index,center_required=False)))):
            result={'id':None,'score':1.,'candidates':[]}
        else:
            center=None
            if borderless:
                cx,cy=grid.center(index);cw=grid.rect[2]/columns;ch=grid.rect[3]/rows
                center=(cx-cw*.4-x,cy-ch*.4-y,cx+cw*.4-x,cy+ch*.4-y)
            result=match(roi,center_region=center,animated=borderless)
            if result['id']=='?':
                # Card artwork can extend a few pixels outside the inferred
                # border. Expand only uncertain cells and constrain the inferred
                # character center to the original tile to exclude neighbors.
                for pad in (-.15,-.30):
                    px,py,pr,pb=grid.tile(index,pad)
                    px,py=max(0,px),max(0,py);pr,pb=min(image.shape[1],pr),min(image.shape[0],pb)
                    cx,cy=grid.center(index);cw=grid.rect[2]/columns;ch=grid.rect[3]/rows
                    region=(cx-cw*.4-px,cy-ch*.4-py,cx+cw*.4-px,cy+ch*.4-py)
                    expanded=match(image[py:pb,px:pr,:3],center_region=region,animated=borderless)
                    if expanded['id']!='?':result=expanded;break
            if result['id']=='?':
                # Both rounded portrait cells and borderless boards display
                # transparent source art on a light surface. Retry that rendering
                # for uncertain cells, keeping body fit and center constraints.
                for pad in (0,-.15,-.30):
                    px,py,pr,pb=grid.tile(index,pad)
                    px,py=max(0,px),max(0,py);pr,pb=min(image.shape[1],pr),min(image.shape[0],pb)
                    region=(cx-cw*.4-px,cy-ch*.4-py,cx+cw*.4-px,cy+ch*.4-py)
                    rendered=match(image[py:pb,px:pr,:3],center_region=region,animated=True,background=180)
                    if rendered['id']!='?':result=rendered;break
            if result['id']=='?' and dark_surface:
                # Small dark-board outlines need descriptors rendered against
                # that surface too. Keep the same fit, margin and identity gate.
                for pad in (0,-.15,-.30):
                    px,py,pr,pb=grid.tile(index,pad)
                    px,py=max(0,px),max(0,py);pr,pb=min(image.shape[1],pr),min(image.shape[0],pb)
                    region=(cx-cw*.4-px,cy-ch*.4-py,cx+cw*.4-px,cy+ch*.4-py)
                    rendered=match(image[py:pb,px:pr,:3],center_region=region,animated=True,background=90)
                    if rendered['id']!='?':result=rendered;break
            # Extra texture can justify checking a pale sprite, but cannot by
            # itself turn a previously empty scenery cell into an unknown unit.
            if borderless and columns==5 and low_outline and result['id']=='?':
                result={'id':None,'score':1.,'candidates':[]}
        cells.append(result['id']);details.append(result)
        if cell_ready:cell_ready(index,dict(result),grid)
    if ratio<1:grid=Grid(tuple(v/ratio for v in grid.rect),columns,rows,grid.score)
    return {'grid':grid,'cells':cells,'details':details}
