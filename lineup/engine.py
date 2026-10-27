"""Incremental reconciliation of deployed units and targeted inventory search."""
from dataclasses import dataclass
import threading
from .catalog import choose_available, load_catalog


class UnrecognizedBoardUnits(RuntimeError):
    def __init__(self,indices,count):
        super().__init__('多帧仍未确认场上塔塔身份，准备点击下阵')
        self.indices=tuple(sorted(set(indices)));self.count=count


def recover_unrecognized(ops,work,check=None):
    """A confirmed withdrawal invalidates every previously planned move."""
    removed=0
    while True:
        try:return work(removed>0)
        except UnrecognizedBoardUnits as exc:
            if not exc.indices or removed+len(exc.indices)>25:
                raise RuntimeError('未确认塔塔过多，请检查场地后重试') from exc
            count=exc.count
            for index in exc.indices:
                if check is not None:check()
                ops.withdraw_unrecognized(index,count)
                after=ops.wait_count(count-1)
                if after.count!=count-1:raise RuntimeError('未确认塔塔下阵，已停止')
                count-=1;removed+=1


@dataclass
class Settings:
    mode: str = 'mumu_sdk'
    crop_top: int = 0
    crop_bottom: int = 0
    adb_path: str = ''
    adb_address: str = ''


def project_cells(cells, source_columns, target_columns, rows=5):
    """Center narrower boards; do not silently discard requested edge units."""
    target=[None]*(target_columns*rows); issues=[]
    offset=(target_columns-source_columns)//2
    for index,wanted in enumerate(cells):
        row,col=divmod(index,source_columns); col+=offset
        if row>=rows or not 0<=col<target_columns:
            if wanted is not None:issues.append({'sourceIndex':index,'reason':'超出当前场地'})
        else:target[row*target_columns+col]=wanted
    return target,issues


def board_observation(ops, initial):
    """Use the count from the board scan, which reacquires its own frames."""
    current=ops.action_state() if callable(getattr(ops,'action_state',None)) else ops.snapshot()
    if (current.state!='ready' or current.limit!=initial.limit or
            (current.grid.columns,current.grid.rows)!=(initial.grid.columns,initial.grid.rows) or
            max(abs(a-b) for a,b in zip(current.grid.rect,initial.grid.rect))>5):
        raise RuntimeError('识别期间场地已变化，请重新开始')
    return current


class FormationStream:
    """One immutable image import, progressively confirmed by its own worker."""
    def __init__(self,size):
        self.condition=threading.Condition();self.cells=['?']*size
        self.version=0;self.done=False;self.error=None
    def put(self,index,result):
        with self.condition:
            if self.done:return
            self.cells[index]=result['id'];self.version+=1;self.condition.notify_all()
    def finish(self,result):
        with self.condition:
            if self.done:return
            self.cells=list(result['cells']);self.done=True;self.version+=1;self.condition.notify_all()
    def fail(self,error):
        with self.condition:
            if self.done:return
            self.error=str(error);self.done=True;self.version+=1;self.condition.notify_all()
    def read(self):
        with self.condition:
            if self.error:raise RuntimeError(self.error)
            return list(self.cells),self.done,self.version
    def wait(self,version):
        with self.condition:
            if version==self.version:self.condition.wait(.08)


def execute_stream(ops,stream,columns,publish,cancel):
    def check():
        if cancel.is_set():raise RuntimeError('已停止上阵')
        stream.read()
    return recover_unrecognized(ops,lambda recovered:_execute_stream(ops,stream,columns,publish,cancel),check)


def _execute_stream(ops,stream,columns,publish,cancel):
    """Act on confirmed cells while image recognition continues independently.

    Before the whole image is known, retain all unrequested field units. Only
    move into empty destinations or add an identified inventory unit below the
    limit. Final reconciliation reuses this verified board and handles blockers.
    """
    if cancel.is_set():raise RuntimeError('已停止上阵')
    stream.read()
    initial=ops.snapshot()
    if initial.state!='ready':raise RuntimeError('请先进入塔塔上阵界面')
    catalog={r['id']:r for r in load_catalog()}
    board={u['index']:dict(u) for u in ops.board()}
    initial=board_observation(ops,initial)
    if len(board)!=initial.count:raise RuntimeError('场上塔塔位置与数量不一致，请确认场地后重试')
    unknown=[i for i,u in board.items() if u['id'] not in catalog]
    if unknown:raise UnrecognizedBoardUnits(unknown,initial.count)
    expected=initial.count;missing=set();completed=set()
    badges=[c.get('element') for c in getattr(initial,'cards',()) if c.get('element')]
    element=max(set(badges),key=badges.count) if badges and max(badges.count(k) for k in set(badges))>=len(badges)*.65 else None
    def verify():
        obs=ops.action_state() if callable(getattr(ops,'action_state',None)) else ops.snapshot()
        if obs.state!='ready' or obs.count!=expected or obs.limit!=initial.limit or (obs.grid.columns,obs.grid.rows)!=(initial.grid.columns,initial.grid.rows):
            raise RuntimeError('当前上阵数量发生变化，已停止')
        return obs
    while True:
        if cancel.is_set():raise RuntimeError('已停止上阵')
        cells,done,version=stream.read()
        if done:
            return execute(ops,cells,columns,publish,known_board=list(board.values()))
        targets,_=project_cells(cells,columns,initial.grid.columns,initial.grid.rows)
        wanted={i:k for i,k in enumerate(targets) if k in catalog}
        if initial.grid.columns==3 and initial.limit==5:
            if element is None and wanted:element=catalog[next(iter(wanted.values()))]['elementKey']
            wanted={i:k for i,k in wanted.items() if catalog[k]['elementKey']==element}
        acted=False;requests={}
        for index,identity in wanted.items():
            if index in completed:continue
            matching=choose_available(identity,[u for u in board.values() if u['id'] in catalog])
            if matching:
                source=matching['index']
                if source==index:completed.add(index);continue
                if index in board or source in completed:continue
                stream.read()
                verify();ops.move(source,index,expected);ops.wait_move(expected)
                board.pop(source);matching['index']=index;board[index]=matching
                completed.add(index);acted=True;break
            if index not in board and expected<initial.limit and (index,identity) not in missing:requests[index]=identity
        if not acted and requests:
            first=catalog[next(iter(requests.values()))]['elementKey']
            requests={i:k for i,k in requests.items() if catalog[k]['elementKey']==first}
            publish({'status':'边识别边上阵：正在查找已确认的塔塔'})
            used={u['id'] for u in board.values() if u['id'] in catalog}
            # Real operations inspect each inventory page and return at the
            # first confirmed match. Image recognition never waits for paging.
            match=ops.find_next(requests,used)
            if match:
                index,card=match
                if index not in requests or card['id'] not in catalog or catalog[card['id']]['family']!=catalog[requests[index]]['family']:
                    raise RuntimeError('库存匹配结果与待上阵目标不一致')
                if cancel.is_set():raise RuntimeError('已停止上阵')
                stream.read()  # Recognition failure invalidates queued actions.
                before=verify();ops.deploy(card,before.grid.center(index),expected,index)
                after=ops.wait_count(expected+1)
                if after.limit!=initial.limit or (after.grid.columns,after.grid.rows)!=(initial.grid.columns,initial.grid.rows):
                    raise RuntimeError('场地格子或数量上限已变化，已停止')
                expected+=1;board[index]={'index':index,'id':card['id']};completed.add(index);acted=True
            else:missing.update(requests.items())
        if acted:publish({'completed':len(completed),'count':expected,'limit':initial.limit,'status':f'边识别边上阵 · 已完成 {len(completed)} 只'})
        else:stream.wait(version)


def execute(ops,cells,columns,publish,known_board=None):
    return recover_unrecognized(ops,lambda recovered:_execute(ops,cells,columns,publish,None if recovered else known_board))


def _execute(ops,cells,columns,publish,known_board=None):
    """All device actions are injected, so every transition can be replay-tested."""
    initial=ops.snapshot()
    if initial.state!='ready':raise RuntimeError('请先进入塔塔上阵界面')
    targets,outside=project_cells(cells,columns,initial.grid.columns,initial.grid.rows)
    catalog={r['id']:r for r in load_catalog()}
    plan={'placements':[],'issues':[],'outside':outside}
    wanted={i:k for i,k in enumerate(targets) if k in catalog}
    plan['issues']=[{'index':i,'reason':'识别不确定'} for i,k in enumerate(targets) if k is not None and k not in catalog]
    if initial.grid.columns==3 and initial.limit==5 and wanted:
        badges=[c.get('element') for c in initial.cards if c.get('element')]
        element=max(set(badges),key=badges.count) if badges else catalog[next(iter(wanted.values()))]['elementKey']
        if badges and badges.count(element)<len(badges)*.65:
            element=catalog[next(iter(wanted.values()))]['elementKey']
        for index,identity in list(wanted.items()):
            if catalog[identity]['elementKey']!=element:
                plan['issues'].append({'index':index,'reason':'3×4 仅支持当前活动属性'});wanted.pop(index)
    publish({'issues':list(plan['issues']),'outside':outside,'plan':[]})
    if not wanted:
        publish({'status':'没有可以确认上阵的塔塔，请修正阵容或补充库存识别','completed':0})
        return plan
    publish({'status':'正在检查已上场塔塔，保留匹配阵容'})
    board={u['index']:dict(u) for u in (known_board if known_board is not None else ops.board())}
    if known_board is None:initial=board_observation(ops,initial)
    if len(board)!=initial.count:raise RuntimeError('场上塔塔位置与数量不一致，请确认场地后重试')
    unknown=[i for i,u in board.items() if u['id'] not in catalog]
    if unknown:raise UnrecognizedBoardUnits(unknown,initial.count)
    # Reserve exact identities globally before permitting evolution substitutions.
    assigned={};available=list(board.values())
    for exact in (True,False):
        for index,identity in wanted.items():
            if index in assigned:continue
            candidates=[u for u in available if u['id'] in catalog and (not exact or u['id']==identity)]
            candidates.sort(key=lambda u:u['index']!=index)
            unit=choose_available(identity,candidates)
            if unit:
                assigned[index]=unit;available.remove(unit)
    expected=initial.count

    def verify():
        before=ops.action_state() if callable(getattr(ops,'action_state',None)) else ops.snapshot()
        if before.state!='ready' or before.count!=expected or before.limit!=initial.limit or (before.grid.columns,before.grid.rows)!=(initial.grid.columns,initial.grid.rows):
            raise RuntimeError('当前上阵数量发生变化，已停止')
        return before

    def withdraw(index):
        nonlocal expected
        verify();ops.withdraw(index,expected);ops.wait_count(expected-1)
        expected-=1;board.pop(index)

    # Remove mismatching blockers before moving retained units into their cells.
    discard={u['index'] for u in available if u['id'] in catalog}
    for index in sorted(discard & set(assigned)):withdraw(index);discard.remove(index)
    moving={index:u for index,u in assigned.items() if u['index']!=index}
    while moving:
        movable=next((i for i in moving if i not in board),None)
        if movable is None:
            # Break a position cycle using a verified empty cell, never stack units.
            blocked=[i for i in moving if i in board and board[i] not in moving.values()]
            if blocked:
                for i in blocked:
                    plan['issues'].append({'index':i,'reason':'目标格子已有未确认塔塔'})
                    moving.pop(i);assigned.pop(i)
                continue
            empty=next((i for i in range(len(targets)) if i not in board),None)
            if empty is None:
                if discard:
                    index=min(discard);withdraw(index);discard.remove(index);continue
                raise RuntimeError('没有空格可调整阵容，请先收回一只塔塔')
            movable=next(iter(moving));unit=moving[movable];destination=empty
        else:unit=moving[movable];destination=movable
        verify();source=unit['index'];ops.move(source,destination,expected);ops.wait_move(expected)
        board.pop(source);unit['index']=destination;board[destination]=unit
        if destination==movable:moving.pop(movable)
    for index in sorted(discard):withdraw(index)
    for index,unit in assigned.items():
        if unit['index']==index:
            plan['placements'].append({'index':index,'wanted':wanted[index],'actual':unit['id'],'substituted':wanted[index]!=unit['id']})
    completed=len(plan['placements']);used={u['id'] for u in board.values() if u['id'] in catalog}
    publish({'completed':completed,'plan':list(plan['placements']),'issues':list(plan['issues'])})
    # Search every pending family of the current element on each page. A fresh
    # search after each deployment prevents reuse of shifted inventory positions.
    pending={}
    for index,identity in wanted.items():
        if index in assigned:continue
        if index in board:
            if not any(i['index']==index for i in plan['issues']):
                plan['issues'].append({'index':index,'reason':'目标格子未空出'})
            continue
        pending[index]=identity
    groups={}
    for index,identity in pending.items():groups.setdefault(catalog[identity]['elementKey'],{})[index]=identity
    for requests in groups.values():
        while requests:
            if expected>=initial.limit:
                plan['issues'].extend({'index':i,'reason':'超过上阵上限'} for i in requests);break
            publish({'status':f'正在查找下一只塔塔 · 已完成 {completed} 只'})
            if callable(getattr(ops,'find_next',None)):
                match=ops.find_next(requests,used)
                index,card=match if match else (None,None)
            else:
                index=next(iter(requests));card=ops.find_available(requests[index],used)
            if card is None:
                missing=list(requests) if index is None else [index]
                for i in missing:plan['issues'].append({'index':i,'reason':'库存未找到'});requests.pop(i)
                publish({'issues':list(plan['issues'])})
                continue
            if index not in requests or card['id'] not in catalog or catalog[card['id']]['family']!=catalog[requests[index]]['family']:
                raise RuntimeError('库存匹配结果与待上阵目标不一致')
            identity=requests.pop(index)
            before=verify()
            publish({'status':f'找到塔塔，正在拖拽上阵 · 已完成 {completed} 只'})
            ops.deploy(card,before.grid.center(index),before.count,index)
            after=ops.wait_count(expected+1)
            if after.limit!=initial.limit or (after.grid.columns,after.grid.rows)!=(initial.grid.columns,initial.grid.rows):
                raise RuntimeError('场地格子或数量上限已变化，已停止')
            expected+=1;completed+=1;used.add(card['id'])
            plan['placements'].append({'index':index,'wanted':identity,'actual':card['id'],'substituted':identity!=card['id']})
            publish({'completed':completed,'count':after.count,'limit':after.limit,'plan':list(plan['placements'])})
    plan['issues']=list({i['index']:i for i in plan['issues']}.values())
    publish({'completed':completed,'issues':list(plan['issues']),'status':f'已上阵 {completed} 只 · {len(plan["issues"])+len(outside)} 个位置待处理'})
    return plan
