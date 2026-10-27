"""Bounded failure history; captures only the already bound game frames."""
from collections import deque
import json
import cv2
from autotata.paths import ROOT


class Trace:
    def __init__(self):
        self.events=deque(maxlen=400)
        self.frames=deque(maxlen=40)
        self.last_frame=-100.

    def add(self,frame,obs,engine,action,captured_at,now):
        self.events.append({'time':now,'frameAge':now-captured_at,'state':obs.state,
                            'motion':obs.motion,'pose':obs.wheel_pose,'free':obs.free,
                            'multiplier':obs.multiplier,'action':action.purpose or action.kind,
                            'message':action.message,'progress':engine.progress_seen,
                            'ambiguous':engine.ambiguous_change,'unchangedReads':engine.unchanged_reads,
                            'attempt':engine.spin_retries+1,'rounds':engine.completed,
                            'capsuleLabel':obs.capsule_label,'rewardContext':engine.after_choice,
                            'dialogLabel':obs.dialog_label,'dialogBounds':obs.dialog_bounds})
        self.events[-1]['cardpackAttempts']=engine.cardpack_attempts
        self.events[-1]['rewardButtonAttempts']=engine.reward_attempts
        self.events[-1]['rewardButtonLabel']=engine.reward_label
        if now-self.last_frame>=.5:
            small=cv2.resize(frame,(540,round(len(frame)*540/frame.shape[1])))
            ok,pixels=cv2.imencode('.jpg',small,[cv2.IMWRITE_JPEG_QUALITY,70])
            if ok:self.frames.append((now,pixels.tobytes()))
            self.last_frame=now

    def save(self,message):
        folder=ROOT/'logs/rafting-last-trace';folder.mkdir(parents=True,exist_ok=True)
        files=[]
        for index,(moment,pixels) in enumerate(self.frames):
            name=f'{index:02}.jpg';(folder/name).write_bytes(pixels)
            files.append({'time':moment,'file':name})
        (folder/'trace.json').write_text(json.dumps({'message':message,'frames':files,
                'events':list(self.events)},ensure_ascii=False,indent=2),encoding='utf-8')
