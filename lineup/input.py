"""Drag only through the already bound MAA input channel."""
import logging,math,time


def drag(session,start,end,cancel,duration=360,hold=.04,waypoint=None,ease_out=False):
    if cancel.is_set():raise RuntimeError('已停止上阵')
    replacement=getattr(session,'fallback_session',None)
    if replacement is not None:return drag(replacement,start,end,cancel,duration,hold,waypoint,ease_out)
    width,height=session.size
    for x,y in (start,end) if waypoint is None else (start,waypoint,end):
        if not 0<=x<width or not 0<=y<height:raise RuntimeError('拖拽坐标超出已绑定画面')
    backend=getattr(session,'backend',None)
    if backend is not None:
        if not session.validate(start) or not session.validate(end):raise RuntimeError('输入已停止')
        controller=backend.controller
    else:
        if not session.validate():raise RuntimeError('输入已停止')
        controller=session.controller
    from fishing.maa_input import wait_job
    pressed=False
    failed=False
    started=time.monotonic()
    try:
        if backend is not None:backend.down(*map(round,start))
        else:wait_job(controller.post_touch_down(*map(round,start),contact=0))
        pressed=True
        if cancel.wait(hold):raise RuntimeError('已停止上阵')
        # Small initial moves keep the pointer in its original inventory card
        # while the game starts dragging; coarse jumps can enter another row.
        steps=max(12,math.ceil(duration/24))
        lift_steps=max(8,round(steps*.45))
        pickup_fraction=min(.60,54*width/540/max(1,math.dist(start,waypoint))) if waypoint is not None else 0
        motion_started=time.monotonic()
        for step in range(1,steps+1):
            if cancel.is_set():raise RuntimeError('已停止上阵')
            valid=session.validate(end) if backend is not None else session.validate()
            if not valid:raise RuntimeError('输入已停止')
            if waypoint is not None and step<=lift_steps:
                a,b=start,waypoint
                # Stay inside the source card until drag pickup has engaged;
                # crossing the upper row too early can grab that row's unit.
                fraction=pickup_fraction*step/5 if step<=5 else pickup_fraction+(1-pickup_fraction)*(step-5)/(lift_steps-5)
            elif waypoint is not None:a,b,fraction=waypoint,end,(step-lift_steps)/(steps-lift_steps)
            else:
                a,b,fraction=start,end,step/steps
                if ease_out:fraction=6*fraction**5-15*fraction**4+10*fraction**3
            point=tuple(round(x+(y-x)*fraction) for x,y in zip(a,b))
            wait_job(controller.post_touch_move(*point,contact=0))
            remaining=motion_started+duration/1000*step/steps-time.monotonic()
            if remaining>0 and cancel.wait(remaining):raise RuntimeError('已停止上阵')
        # Let the ScrollRect's release velocity decay while contact is still
        # stationary; a short touch-up tail otherwise causes seconds of inertia.
        if (hold or ease_out) and cancel.wait(.14 if ease_out else .04):raise RuntimeError('已停止上阵')
    except BaseException:
        failed=True
        raise
    finally:
        try:
            if pressed:
                if backend is not None:
                    from fishing.windows import user32
                    if session.mode=='foreground' and user32.GetForegroundWindow()!=session.hwnd:
                        session.emergency_release(end);backend.deactivate()
                    else:backend.up()
                else:wait_job(controller.post_touch_up(contact=0))
            elif backend is not None:backend.deactivate()
            else:wait_job(controller.post_inactive())
        except Exception:
            if not failed:raise
            logging.getLogger('lineup').exception('松开拖拽操作失败')
    logging.getLogger('lineup').info('drag completed requested_ms=%s moves=%s lifted=%s elapsed=%.3fs',duration,steps,waypoint is not None,time.monotonic()-started)
