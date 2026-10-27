"""Bound capture, horizontal inventory paging, fresh-frame guarded dragging."""
import logging,time,hashlib
import cv2,numpy as np
from .vision import Vision,Grid,occupied_cell
from .input import drag
from .engine import execute,execute_stream,FormationStream,UnrecognizedBoardUnits


def connect(hwnd,settings,cancel):
    capture=mouse=None
    try:
        factory=lambda:Vision(settings.crop_top,settings.crop_bottom)
        if settings.mode=='maatouch':
            from fishing.generic_adb import GenericAdbSession
            capture=mouse=GenericAdbSession(settings,cancel,vision_factory=factory)
            capture.start(allow_active=True)
        elif settings.mode=='mumu_sdk':
            from fishing.adb_session import AdbSession
            # Keep SDK capture, but bind native continuous touch to that exact
            # display. Repeated SDK touch-down events can grab a neighboring
            # inventory row during a drag instead of retaining its first card.
            capture=mouse=AdbSession(hwnd,cancel,mode='maatouch',vision_factory=factory,allow_active=True)
            capture.start()
        else:
            from fishing.windows import WindowCapture,Mouse
            capture=WindowCapture(hwnd);capture.start();mouse=Mouse(hwnd,settings.mode,cancel)
        return capture,mouse
    except Exception:
        for item in (mouse,capture if capture is not mouse else None):
            if item is not None:item.close()
        raise


def card_patch(frame,card):
    x,y,w,h=map(round,card['bounds'])
    return frame[y:y+h,x:x+w,:3].copy()


def similar(a,b,threshold=8):
    if a is None or b is None or a.shape!=b.shape:return False
    a=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY);b=cv2.cvtColor(b,cv2.COLOR_BGR2GRAY)
    return float(np.abs(a.astype(float)-b).mean())<threshold


def inventory_fingerprint(frame,obs):
    x,y,w,h=map(round,obs.inventory_rect)
    return cv2.resize(frame[y:y+h,x:x+w,:3],(90,40))


def inventory_landmarks(frame,obs):
    """Static badge/star bands prove scrolling stopped despite idle animation."""
    if not obs.cards:return None
    x,y,w,h=map(round,obs.inventory_rect)
    if obs.count_y is not None:
        # Anchor to the independent count bar: connected card seams can differ
        # by a few pixels while the stationary card content stays unchanged.
        a,b=round(obs.count_y+35*obs.scale),round(obs.count_y+48*obs.scale)
        return cv2.resize(frame[a:b,x:x+w,:3],(180,10))
    bands=[]
    rows=[]
    for card in sorted(obs.cards,key=lambda c:c['bounds'][1]):
        _,top,_,height=card['bounds']
        if any(abs(top-old)<=8*obs.scale for old in rows):continue
        rows.append(top)
        for lo,hi in ((.03,.18),(.90,.98)):
            a,b=round(top+height*lo),round(top+height*hi)
            band=frame[max(y,a):min(y+h,b),x:x+w,:3]
            if band.size:bands.append(cv2.resize(band,(180,5)))
    return np.concatenate(bands) if bands else None


class Operations:
    def __init__(self,capture,mouse,vision,cancel,publish,targets=None,diagnostics=None):
        self.capture,self.mouse,self.vision,self.cancel,self.publish=capture,mouse,vision,cancel,publish
        self.sequence=-1;self.frame=None;self.observation=None;self.cache={};self.pending=None
        from .recognition import PortraitCache
        self.portraits=PortraitCache()
        from .catalog import load_catalog
        self.catalog={r['id']:r for r in load_catalog()}
        self.targets=targets;self.element=None;self.board_reference=None;self.moving=None;self.pending_kind=None;self.inventory_found=set()
        self.board_identities={};self.pending_identity=None;self.moving_identity=None
        self.grid_anchor=None
        self.search_direction=1
        self.page_ready=False
        self.diagnostics=diagnostics;self.initial_recorded=False
    def record_frame(self,slot,**fields):
        if self.diagnostics is not None and self.frame is not None:self.diagnostics.capture(self.frame,slot,**fields)
    def check(self):
        if self.cancel.is_set():raise RuntimeError('已停止上阵')
        from fishing.windows import user32
        from fishing.hotkeys import STOP_KEY
        if user32.GetAsyncKeyState(STOP_KEY)&0x8000:self.cancel.set();raise RuntimeError('已停止上阵')
    def fresh_frame(self):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            self.check();sample=self.capture.read()
            if sample:
                frame,at,seq,size=sample
                if tuple(size)!=tuple(self.mouse.size):raise RuntimeError('设备画面尺寸已变化')
                if seq!=self.sequence and time.monotonic()-at<1:
                    self.sequence=seq;return frame
            self.cancel.wait(.04)
        raise RuntimeError('没有获取到新画面，未继续发送操作')
    def snapshot(self):
        frame=self.fresh_frame()
        if self.diagnostics is not None and not self.initial_recorded:
            self.diagnostics.capture(frame,'game-initial');self.initial_recorded=True
        obs=self.vision.observe(frame,grid_hint=self.grid_anchor)
        if obs.state!='ready':raise RuntimeError('上阵界面尚未识别，请恢复上阵页面后重试')
        self.stabilize_grid(obs)
        self.frame=frame;self.observation=obs
        self.page_ready=True
        self.publish({'count':obs.count,'limit':obs.limit,'grid':{'rect':list(obs.grid.rect),'columns':obs.grid.columns,'rows':obs.grid.rows},'frameSize':[frame.shape[1],frame.shape[0]]})
        return obs
    def action_state(self):
        # The next action always calls guard() on a new frame. Reuse the last
        # observation here rather than running the same full inspection twice.
        return self.observation if self.observation is not None else self.snapshot()
    def stabilize_grid(self,obs):
        # Sprites briefly cover checker corners. Keep the verified grid while
        # independent controls and dimensions prove that the layout is unchanged.
        if obs.state!='ready' or obs.clear is None:return
        if self.grid_anchor is None:
            self.grid_anchor=(obs.grid,obs.clear,obs.limit,obs.count_y);return
        grid,clear,limit,count_y=self.grid_anchor
        if obs.limit!=limit or obs.grid.columns!=grid.columns or obs.grid.rows!=grid.rows:
            raise RuntimeError('上阵界面或数量上限已变化，请重新开始')
        if np.linalg.norm(np.subtract(obs.clear,clear))>5*obs.scale or count_y is not None and obs.count_y is not None and abs(obs.count_y-count_y)>5*obs.scale:
            raise RuntimeError('场地位置已变化，请重新开始')
        if max(abs(a-b) for a,b in zip(obs.grid.rect,grid.rect))>10*obs.scale:
            raise RuntimeError('场地位置已变化，请重新开始')
        obs.grid=Grid(grid.rect,grid.columns,grid.rows,obs.grid.score)
    def guard(self):
        # Recognition may take seconds. Reacquire before input and reject any
        # intervening inventory/count/layout change instead of using stale pixels.
        before=self.frame;old=self.observation;fresh=self.fresh_frame()
        x,y,w,h=map(round,old.inventory_rect)
        if not similar(before[y:y+h,x:x+w],fresh[y:y+h,x:x+w],5):
            raise RuntimeError('识别期间库存界面已变化，请重新开始')
        new=self.vision.observe(fresh,grid_hint=self.grid_anchor)
        self.stabilize_grid(new)
        if new.state!='ready' or (new.count,new.limit,new.grid.columns)!=(old.count,old.limit,old.grid.columns):
            raise RuntimeError('识别期间上阵状态已变化，请重新开始')
        if max(abs(a-b) for a,b in zip(new.grid.rect,old.grid.rect))>5:
            raise RuntimeError('场地位置已变化，请重新开始')
        self.frame=fresh;self.observation=new;self.check()
        return new
    def page(self,accelerated=False,allowed_ids=None,first_match=False,refresh=True):
        from .recognition import identify
        obs=self.snapshot() if refresh else self.action_state();cards=[]
        for card in obs.cards:
            self.check();patch=card_patch(self.frame,card)
            # Level/star/element symbols occupy the top and bottom card bands.
            portrait=patch[round(len(patch)*.12):round(len(patch)*.85),:]
            element=card.get('element') or self.element
            allowed=allowed_ids if allowed_ids is not None else ({k for k,r in self.catalog.items() if r['elementKey']==element} if element else None)
            digest=(tuple(sorted(allowed)) if allowed is not None else None,hashlib.sha256(portrait.tobytes()).hexdigest())
            result=self.cache.get(digest)
            if result is None and accelerated:result=self.portraits.match(portrait,allowed)
            if result is not None and allowed is not None and result['id'] not in allowed:result=None
            if result is None:
                result=identify(portrait,allowed_ids=allowed,animated=True)
                if result['id']=='?' and result['score']>=.60 and allowed is not None and len(allowed)<=6:
                    rendered=identify(portrait,allowed_ids=allowed,animated=True,background=180)
                    if rendered['id']!='?' or rendered['score']>result['score']:result=rendered
                self.cache[digest]=result
            self.portraits.add(result['id'],portrait)
            cards.append({**card,**result,'patch':patch.copy()})
            logging.getLogger('lineup').debug('inventory card id=%s score=%s bounds=%s allowed=%s',result['id'],result['score'],card['bounds'],sorted(allowed) if allowed is not None else None)
            if result['id']!='?':self.inventory_found.add(result['id'])
            if first_match and result['id']!='?':break
        self.publish({'inventoryFound':len(self.inventory_found)})
        if self.diagnostics is not None:
            self.diagnostics.record('inventory',element=self.element,cards=[{k:v for k,v in c.items() if k!='patch'} for c in cards])
            self.record_frame('game-recognition',phase='inventory')
        return cards
    def scroll(self,direction):
        obs=self.guard();x,y,w,h=obs.inventory_rect
        before=inventory_fingerprint(self.frame,obs)
        # The white count/list separator does not receive ScrollRect gestures.
        # Swipe horizontally through a freshly verified full portrait row,
        # without holding or any vertical motion that would deploy a unit.
        boxes=[c['bounds'] for c in obs.cards]
        if not boxes:
            raise RuntimeError('未确认库存滑动区域，请展开塔塔列表后重试')
        rows=[]
        for box in sorted(boxes,key=lambda b:b[1]):
            row=next((r for r in rows if abs(r[0][1]-box[1])<=8*obs.scale),None)
            if row is None:rows.append([box])
            else:row.append(box)
        row=sorted(max(rows,key=len),key=lambda b:b[0])
        if len(row)<2:raise RuntimeError('未确认库存滑动区域，请展开塔塔列表后重试')
        line=float(np.median([b[1]+b[3]*.55 for b in row]))
        a=(row[-1][0]+row[-1][2]*.5,line);b=(row[0][0]+row[0][2]*.5,line)
        if not y<line<y+h or not x<a[0]<x+w or not x<b[0]<x+w:
            raise RuntimeError('未确认库存滑动区域，请展开塔塔列表后重试')
        started=time.monotonic()
        self.record_frame('game-before-action',action='scroll',direction=direction,count=obs.count)
        drag(self.mouse,a if direction>0 else b,b if direction>0 else a,self.cancel,220,hold=0,ease_out=True)
        self.cancel.wait(.10)
        deadline=time.monotonic()+6.;previous=None;previous_bounds=None
        while time.monotonic()<deadline:
            fresh=self.snapshot()
            if (fresh.count,fresh.limit)!=(obs.count,obs.limit):
                raise RuntimeError('库存滑动期间上阵数量发生变化，已停止')
            pixels=inventory_landmarks(self.frame,fresh)
            bounds=np.asarray([c['bounds'] for c in fresh.cards],float)
            aligned=(previous_bounds is not None and bounds.shape==previous_bounds.shape
                     and bounds.size and np.max(abs(bounds[:,:3]-previous_bounds[:,:3]))<=2*fresh.scale
                     and np.max(abs(bounds[:,3]-previous_bounds[:,3]))<=8*fresh.scale)
            logging.getLogger('lineup').debug('inventory settling cards=%s aligned=%s bounds=%s landmark_diff=%s',len(bounds),bool(aligned),bounds.tolist(),
                float(np.abs(previous.astype(float)-pixels).mean()) if previous is not None and pixels is not None and previous.shape==pixels.shape else None)
            if aligned and previous is not None and similar(previous,pixels,3):
                changed=not similar(before,inventory_fingerprint(self.frame,fresh),3)
                logging.getLogger('lineup').info('inventory swipe direction=%s changed=%s elapsed=%.3fs',direction,changed,time.monotonic()-started)
                self.record_frame('game-after-action',action='scroll',direction=direction,changed=changed,count=fresh.count)
                return changed
            previous=pixels;previous_bounds=bounds;self.cancel.wait(.07)
        raise RuntimeError('库存滑动尚未稳定，已停止；不会使用移动中的卡片位置')
    def rewind(self):
        if self.observation is None:self.snapshot()
        for _ in range(40):
            if self.scroll(-1) is False:return
        raise RuntimeError('库存列表未回到起点，请手动回到最左侧后重试')
    def select_element(self,element):
        obs=self.snapshot()
        if obs.grid.columns==3 and obs.limit==5:
            # This activity exposes only its own element. Never tap filters or
            # infer an inventory identity from the requested element alone.
            return False
        if not obs.filters:
            if self.element is not None:raise RuntimeError('属性筛选栏已变化，请展开后重试')
            return False
        key=element or 'all'
        if key not in obs.filters:raise RuntimeError('未确认属性筛选按钮，请展开筛选栏后重试')
        if self.element==element and element is not None:
            badges=[c.get('element') for c in obs.cards if c.get('element')]
            if badges and sum(b==element for b in badges)>=np.ceil(len(badges)*.65):return True
        point=obs.filters[key];old_count,old_limit=obs.count,obs.limit
        fresh=self.guard()
        if key not in fresh.filters or np.linalg.norm(np.subtract(fresh.filters[key],point))>4:
            raise RuntimeError('属性筛选按钮位置已变化，未继续操作')
        self.record_frame('game-before-action',action='filter',element=key,count=old_count)
        self.mouse.click(tuple(map(round,fresh.filters[key])));self.cancel.wait(.10)
        stable=0
        for _ in range(8):
            obs=self.snapshot()
            if (obs.count,obs.limit)!=(old_count,old_limit):raise RuntimeError('筛选期间上阵数量已变化')
            badges=[c.get('element') for c in obs.cards if c.get('element')]
            # Verify the inventory badges independently of the tapped filter.
            valid=element is None or (badges and sum(b==element for b in badges)>=np.ceil(len(badges)*.65))
            if not obs.cards and obs.filters:valid=True
            stable=stable+1 if valid else 0
            if stable>=2:
                self.element=element;self.search_direction=1
                self.record_frame('game-after-action',action='filter',element=key,count=obs.count)
                return True
            self.cancel.wait(.06)
        # Badge shading can make rock/lightning ambiguous. Filtering is a search
        # optimization; subsequent portrait verification is the input authority.
        self.publish({'status':'属性筛选尚未确认，退回全部库存并核对塔塔图像'})
        logging.getLogger('lineup').info('filter unconfirmed requested=%s badges=%s; fall back to all',element,badges)
        if element is not None and 'all' in obs.filters:
            self.select_element(None);return False
        raise RuntimeError('未确认属性筛选生效，未继续拖拽')

    def select_all(self):return self.select_element(None)
    def wait_count(self,expected):
        deadline=time.monotonic()+8;stable=0;obs=self.observation
        while time.monotonic()<deadline:
            self.cancel.wait(.06)
            try:obs=self.snapshot()
            except RuntimeError as exc:
                if '上阵界面尚未识别' not in str(exc):raise
                stable=0;continue
            stable=stable+1 if obs.count==expected else 0
            if stable>=2:
                if self.pending is not None:
                    index,old=self.pending;x,y,right,bottom=obs.grid.tile(index,.12)
                    if similar(old,self.frame[y:bottom,x:right],3):continue
                    if self.pending_kind is not None and occupied_cell(self.frame,obs.grid,index)!=(self.pending_kind=='deploy'):continue
                    if self.pending_kind=='deploy' and self.pending_identity:
                        if self.vision.unit(self.frame,obs,index,self.pending_identity)['id']!=self.pending_identity:continue
                        self.board_identities[index]=self.pending_identity
                    elif self.pending_kind=='withdraw':self.board_identities.pop(index,None)
                self.record_frame('game-after-action',action=self.pending_kind,count=obs.count,index=self.pending[0] if self.pending else None)
                self.pending=None
                self.pending_kind=None
                self.pending_identity=None
                self.board_reference=self.frame.copy()
                return obs
        if self.diagnostics is not None:
            index=self.pending[0] if self.pending else None
            self.diagnostics.record('confirmation-timeout',action=self.pending_kind,expected=expected,
                observed=getattr(obs,'count',None),index=index,identity=self.pending_identity,
                occupied=occupied_cell(self.frame,obs.grid,index) if index is not None and obs is not None else None)
        raise RuntimeError('未确认上阵数量更新，已停止；不会重复拖拽')
    def find_available(self,identity,used=()):
        match=self.find_next({0:identity},used)
        return match[1] if match else None
    def find_next(self,requests,used=()):
        """Find any pending family of one element, then immediately deploy it."""
        from .catalog import choose_available
        used_families={self.catalog[k]['family'] for k in used if k in self.catalog}
        requests={i:k for i,k in requests.items() if self.catalog[k]['family'] not in used_families}
        if not requests:return None
        identity=next(iter(requests.values()));element=self.catalog[identity]['elementKey']
        requests={i:k for i,k in requests.items() if self.catalog[k]['elementKey']==element}
        families={self.catalog[k]['family'] for k in requests.values()}
        allowed={k for k,r in self.catalog.items() if r['family'] in families and k not in used}
        if not allowed:return None
        self.select_element(element)
        visited=[]
        def inspect():
            cards=self.page(accelerated=True,allowed_ids=allowed,first_match=True,refresh=not self.page_ready)
            for index,wanted in requests.items():
                match=choose_available(wanted,[c for c in cards if c['id'] in allowed],used)
                if match:return index,match
            # A settled list still has animated portraits. A plausible unknown
            # gets one fresh pose before this page is declared checked; retain
            # the same identity threshold and reacquire its current bounds.
            if any(c['id']=='?' and c.get('score',0)>=.50 for c in cards):
                self.cancel.wait(.16)
                cards=self.page(accelerated=True,allowed_ids=allowed,first_match=True)
                for index,wanted in requests.items():
                    match=choose_available(wanted,[c for c in cards if c['id'] in allowed],used)
                    if match:return index,match
            visited.append(inventory_fingerprint(self.frame,self.observation))
            return None
        match=inspect()
        if match:return match
        if not self.observation.cards:return None
        # Continue from the visible page. Inspect every new page immediately;
        # only reverse after reaching an edge, skipping already checked pages.
        for direction in (self.search_direction,-self.search_direction):
            self.search_direction=direction
            for _ in range(40):
                if self.scroll(direction) is False:break
                pixels=inventory_fingerprint(self.frame,self.observation)
                if any(similar(old,pixels,2) for old in visited):continue
                if len(visited)>=40:raise RuntimeError('库存查找超过 40 页，请检查列表后重试')
                self.publish({'status':f'正在按属性查找塔塔 · 已检查 {len(visited)} 页'})
                match=inspect()
                if match:return match
            else:raise RuntimeError('库存查找未到末尾，请检查列表是否可以滑动')
        return None

    def board(self):
        started=time.monotonic()
        confirmed={};positions=None;baseline=None;last_valid=None
        families={self.catalog[k]['family'] for k in self.targets or () if k in self.catalog}
        preferred={k for k,r in self.catalog.items() if r['family'] in families}
        for attempt in range(3):
            obs=self.snapshot()
            units=self.vision.board(self.frame,obs,self.check,preferred_ids=preferred) if preferred else self.vision.board(self.frame,obs,self.check)
            if self.diagnostics is not None:
                self.diagnostics.record('board-check',attempt=attempt+1,count=obs.count,grid=obs.grid.rect,units=units)
                self.record_frame('game-recognition',phase='board',attempt=attempt+1)
            if len(units)==obs.count:
                current={u['index'] for u in units}
                if current!=positions or baseline is not None and max(abs(a-b) for a,b in zip(baseline,obs.grid.rect))>5:confirmed={}
                positions=current;baseline=obs.grid.rect
                for unit in units:
                    if unit['id']!='?':confirmed[unit['index']]=unit
                last_valid=[confirmed.get(u['index'],u) for u in units]
                if all(u['id']!='?' for u in last_valid):break
            else:
                last_valid=None;confirmed={};positions=None;baseline=None
            self.cancel.wait(.2)
        if last_valid is None:raise RuntimeError('场上塔塔位置与数量不一致，请确认场地后重试')
        logging.getLogger('lineup').info('deployed board count=%s elapsed=%.3fs units=%s',obs.count,time.monotonic()-started,last_valid)
        self.board_identities={u['index']:u['id'] for u in last_valid}
        if self.diagnostics is not None:
            self.diagnostics.record('board',count=obs.count,grid=obs.grid.rect,units=last_valid)
            self.record_frame('game-recognition',phase='board')
        self.board_reference=self.frame.copy();return last_valid

    def board_guard(self,indices,count):
        old=self.observation;reference=self.frame.copy()
        recovering=False;stable=0;uncertain=set()
        for attempt in range(5):
            obs=self.guard()
            if obs.count!=count:raise RuntimeError('场上塔塔数量已变化')
            unresolved=[]
            for index in indices:
                x,y,right,bottom=old.grid.tile(index,.12)
                baseline=self.board_reference if self.board_reference is not None else reference
                was_occupied=occupied_cell(baseline,old.grid,index)
                if was_occupied!=occupied_cell(self.frame,obs.grid,index):raise RuntimeError('场上塔塔位置已变化，未继续操作')
                if not was_occupied:
                    if not similar(baseline[y:bottom,x:right],self.frame[y:bottom,x:right],18):
                        raise RuntimeError('场上塔塔位置已变化，未继续操作')
                    continue
                expected=self.board_identities.get(index)
                if not expected or expected=='?':raise UnrecognizedBoardUnits([index],count)
                result=self.vision.unit(self.frame,obs,index,expected)
                if result['id']==expected:continue
                logging.getLogger('lineup').info('identity recheck attempt=%s index=%s expected=%s result=%s',attempt+1,index,expected,result)
                if result['id']!='?':raise RuntimeError('场上塔塔身份已变化，未继续操作')
                unresolved.append(index)
                uncertain.add(index)
            if not unresolved:
                stable+=1
                if not recovering or stable>=2:return obs
            else:
                recovering=True;stable=0
                self.publish({'status':'正在复核场上塔塔姿态…'})
            if attempt<4:self.cancel.wait(.06)
        raise UnrecognizedBoardUnits(uncertain,count)

    def withdraw_unrecognized(self,index,count):
        # Identity is deliberately unnecessary for this requested fallback.
        # Require two fresh occupied-cell, layout and count checks instead.
        for attempt in range(2):
            obs=self.guard()
            if obs.count!=count:raise RuntimeError('场上塔塔数量已变化')
            if not 0<=index<obs.grid.columns*obs.grid.rows or not occupied_cell(self.frame,obs.grid,index):
                raise RuntimeError('待下阵塔塔位置已变化，未继续操作')
            if attempt==0:self.cancel.wait(.06)
        self.publish({'status':'场上塔塔未确认，正在点击收回'})
        logging.getLogger('lineup').info('withdraw unrecognized index=%s count=%s previous_identity=%s',index,count,self.board_identities.get(index))
        self._withdraw(obs,index,count)

    def withdraw(self,index,count):
        obs=self.board_guard([index],count)
        self.publish({'status':'正在点击收回不匹配的塔塔'})
        self._withdraw(obs,index,count)

    def _withdraw(self,obs,index,count):
        x,y,right,bottom=obs.grid.tile(index,.12)
        self.pending=(index,self.frame[y:bottom,x:right].copy())
        self.pending_kind='withdraw'
        self.pending_identity=self.board_identities.get(index)
        logging.getLogger('lineup').info('withdraw index=%s count=%s',index,count)
        self.record_frame('game-before-action',action='withdraw',index=index,count=count,identity=self.pending_identity)
        self.mouse.click(tuple(map(round,obs.grid.center(index))))

    def move(self,source,target,count):
        obs=self.board_guard([source,target],count)
        self.moving=[(i,self.frame[obs.grid.tile(i,.12)[1]:obs.grid.tile(i,.12)[3],obs.grid.tile(i,.12)[0]:obs.grid.tile(i,.12)[2]].copy()) for i in (source,target)]
        self.moving_identity=self.board_identities.get(source)
        self.publish({'status':'正在移动已上场的匹配塔塔'})
        logging.getLogger('lineup').info('move source=%s target=%s count=%s',source,target,count)
        self.record_frame('game-before-action',action='move',source=source,target=target,count=count,identity=self.moving_identity)
        drag(self.mouse,obs.grid.center(source),obs.grid.center(target),self.cancel)

    def wait_move(self,count):
        started=time.monotonic();deadline=started+8;stable=0
        while time.monotonic()<deadline:
            self.cancel.wait(.06)
            try:obs=self.snapshot()
            except RuntimeError as exc:
                if '上阵界面尚未识别' not in str(exc):raise
                stable=0;continue
            changed=obs.count==count and self.moving is not None
            for index,before in self.moving or []:
                x,y,right,bottom=obs.grid.tile(index,.12)
                changed=changed and not similar(before,self.frame[y:bottom,x:right],3)
            if self.moving:
                source,target=[p[0] for p in self.moving]
                changed=changed and occupied_cell(self.frame,obs.grid,target)
                if self.moving_identity and changed:
                    # Neighboring wings/stars can occupy pixels in the vacated
                    # tile. Confirm the moved unit's location, not those pixels.
                    source_id=self.vision.unit(self.frame,obs,source,self.moving_identity)['id']
                    target_id=self.vision.unit(self.frame,obs,target,self.moving_identity)['id']
                    changed=source_id!=self.moving_identity and target_id==self.moving_identity
                else:changed=changed and not occupied_cell(self.frame,obs.grid,source)
            stable=stable+1 if changed else 0
            if stable>=2:
                if self.moving_identity:
                    self.board_identities.pop(source,None);self.board_identities[target]=self.moving_identity
                logging.getLogger('lineup').info('move confirmed source=%s target=%s identity=%s elapsed=%.3fs',source,target,self.moving_identity,time.monotonic()-started)
                self.record_frame('game-after-action',action='move',source=source,target=target,count=count,identity=self.moving_identity)
                self.moving=None;self.board_reference=self.frame.copy();return obs
        raise RuntimeError('未确认塔塔移动完成，已停止；不会重复拖拽')
    def deploy(self,card,target,count,index):
        current=self.board_guard([index],count)
        if 'patch' not in card or not similar(card['patch'],card_patch(self.frame,card),5):
            raise RuntimeError('库存塔塔位置已变化，未继续拖拽')
        if current.count!=count or current.count>=current.limit:raise RuntimeError('上阵数量已变化')
        if np.linalg.norm(np.subtract(current.grid.center(index),target))>5:raise RuntimeError('目标格子已变化')
        x,y,right,bottom=current.grid.tile(index,.12)
        self.pending=(index,self.frame[y:bottom,x:right].copy())
        self.pending_kind='deploy'
        self.pending_identity=card['id']
        logging.getLogger('lineup').info('deploy identity=%s index=%s count=%s point=%s',card['id'],index,count,card['point'])
        self.record_frame('game-before-action',action='deploy',index=index,count=count,identity=card['id'],source=card['point'])
        lift=(card['point'][0],min(card['point'][1]-80*current.scale,current.inventory_rect[1]-20*current.scale))
        drag(self.mouse,card['point'],current.grid.center(index),self.cancel,waypoint=lift)


def run(hwnd,settings,cells,columns,cancel,publish):
    capture=mouse=ops=None;diagnostic=getattr(publish,'diagnostics',None)
    try:
        cv2.setNumThreads(1)
        publish({'status':'正在连接上阵设备…'})
        capture,mouse=connect(hwnd,settings,cancel)
        streaming=isinstance(cells,FormationStream)
        ops=Operations(capture,mouse,Vision(settings.crop_top,settings.crop_bottom),cancel,publish,targets=None if streaming else cells,diagnostics=diagnostic)
        result=execute_stream(ops,cells,columns,publish,cancel) if streaming else execute(ops,cells,columns,publish)
        if diagnostic:diagnostic.stage('deployment','partial' if isinstance(result,dict) and result.get('issues') else 'completed',result=result)
    except Exception as exc:
        if cancel.is_set():logging.getLogger('lineup').info('用户停止上阵')
        else:logging.getLogger('lineup').exception('上阵操作结束')
        if diagnostic:
            import traceback
            diagnostic.stage('deployment','stopped' if cancel.is_set() else 'failed',error=str(exc),traceback=traceback.format_exc())
            try:
                sample=capture.read() if capture is not None else None
                frame=sample[0] if sample else ops.frame if ops is not None else None
                if frame is not None:diagnostic.capture(frame,'game-failure',error=str(exc))
            except Exception:logging.getLogger('lineup').warning('Failed to capture error frame',exc_info=True)
        message=str(exc).replace('转盘页面','上阵界面').replace('钓鱼画面','上阵画面')
        message=message.replace('已暂停；切回游戏后继续','已停止上阵；切回游戏后重新开始').replace('操作区域被遮挡，已暂停','操作区域被遮挡，已停止上阵')
        publish({'status':'已停止' if cancel.is_set() else message})
    finally:
        if diagnostic is not None:
            try:
                sample=capture.read() if capture is not None else None
                if sample:diagnostic.capture(sample[0],'game-final')
                elif ops is not None:ops.record_frame('game-final')
            except Exception:logging.getLogger('lineup').warning('Failed to capture final frame',exc_info=True)
        for item in (mouse,capture if capture is not mouse else None):
            if item is not None:
                try:item.close()
                except Exception:logging.getLogger('lineup').exception('连接释放失败')
