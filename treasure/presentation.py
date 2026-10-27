"""Visual inference does not turn unopened cells into observed evidence."""
OVERLAY_OPACITY = .85


def probability_fill(ratio, recommended=False):
    """A continuous yellow ramp: very transparent white at low priority."""
    strength=1.0 if recommended else max(0.0,min(1.0,ratio))**2
    return (255,round(255-43*strength),round(255-215*strength),round(28+174*strength))


def markers_and_recommendations(cells,probabilities,certain=(),predicted=(),tentative=(),identities_found=False):
    marked=set(certain)|set(predicted)|{i for i,v in enumerate(cells) if v==2}
    candidates=[(i,p) for i,p in enumerate(probabilities) if i<len(cells) and cells[i]==0 and i not in marked and p is not None]
    if identities_found:return sorted(marked),[]
    if not any(p>0 for _,p in candidates):
        candidates=[(i,p) for i,p in enumerate(probabilities) if i in tentative and i not in certain and i<len(cells) and cells[i]==0 and p is not None]
    maximum=max((p for _,p in candidates),default=0)
    recommended=[i for i,p in candidates if maximum>0 and abs(p-maximum)<1e-7]
    return sorted(marked),recommended


def recognition_status(live, ready, warning=''):
    detail=live.get('status','进入寻宝棋盘后开始识别')
    if not live.get('running'):
        return {'label':'已停止','color':'#8895a7','detail':detail}
    if any(word in detail for word in ('失败','中断','识别停止')):
        return {'label':'连接异常','color':'#cf5147','detail':detail}
    if warning:
        return {'label':'待校正','color':'#b77a20','detail':warning}
    if not ready:
        return {'label':'等待识别','color':'#b77a20','detail':detail}
    return {'label':'识别正常','color':'#36931b','detail':detail}


def located_progress(size,shapes,cells,marked):
    """Count complete, disjoint configured rectangles covered by displayed marks.

    Do not turn inferred marks into observed hits. Excess/inconsistent marks cannot
    complete a board. Search is bounded and conservative if it cannot finish.
    """
    from .solver import placements
    marked={i for i in marked if 0<=i<len(cells) and cells[i]!=1}
    marked_mask=sum(1<<i for i in marked)
    groups=[(w,h,count) for w,h,count in shapes]
    items=[(k,w*h,[m for m in placements(size,w,h) if m&marked_mask==m]) for k,(w,h,count) in enumerate(groups) for _ in range(count)]
    items.sort(key=lambda item:-item[1]);best_area=0;best_counts=[0]*len(groups);nodes=0
    def visit(depth,used,counts):
        nonlocal best_area,best_counts,nodes
        nodes+=1
        area=used.bit_count()
        if area>best_area:best_area=area;best_counts=counts[:]
        if depth==len(items) or nodes>20000:return
        k,_,options=items[depth]
        for mask in options:
            if not mask&used:
                counts[k]+=1;visit(depth+1,used|mask,counts);counts[k]-=1
        visit(depth+1,used,counts)
    visit(0,0,[0]*len(groups))
    total=sum(w*h*c for w,h,c in groups)
    complete=bool(total) and len(marked)==total and best_area==total
    pending=[[w,h,c-best_counts[k]] for k,(w,h,c) in enumerate(groups) if c>best_counts[k]]
    remaining=sum(cells[i]==0 for i in marked) if complete else None
    return {'complete':complete,'pendingShapes':pending,'locatedCells':sorted(marked),'remainingDigCells':remaining,'locatedArea':best_area}


def trusted_ghosts(ghosts,dismissed=(),size=0):
    """Only strong footprint hypotheses may be shown as located treasure."""
    dismissed=set(dismissed)
    return [g for g in ghosts if (g.get('certain') or g.get('pinned') or g.get('support',0)>=.9)
        and not any((g['y']+dy)*size+g['x']+dx in dismissed for dy in range(g['h']) for dx in range(g['w']))]


def candidate_ghosts(ghosts,dismissed=(),size=0):
    dismissed=set(dismissed)
    return [g for g in ghosts if not (g.get('certain') or g.get('pinned') or g.get('support',0)>=.9)
        and not any((g['y']+dy)*size+g['x']+dx in dismissed for dy in range(g['h']) for dx in range(g['w']))]


def pending_identified(shapes,identified):
    """Remaining identities, independent of the certainty of their footprints."""
    from collections import Counter
    found=Counter()
    for w,h,count in identified:found[tuple(sorted((w,h)))]+=count
    pending=[]
    for w,h,count in shapes:
        key=tuple(sorted((w,h)));deduct=min(count,found[key]);found[key]-=deduct
        if count>deduct:pending.append([w,h,count-deduct])
    return pending
