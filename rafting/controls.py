"""OCR is advisory to a continuously observed, fresh-frame control loop."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import cv2
from autotata.activity_shop import supply_layout, supply_signature
from .vision import Vision


class ControlReader:
    def __init__(self, crop_top=0, crop_bottom=0):
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='rafting-controls')
        self.reader=None
        self.crop=(crop_top,crop_bottom)
        self.future=None
        self.request_at=-100.
        self.request_key=None
        self.result_key=None
        self.result=None
        self.kind=None
        self.kind_at=0.
        self.request_frame=None
        self.capsule_key=None
        self.dialog_key=None
        self.shop_key=None

    def read(self, frame):
        if self.reader is None:self.reader=Vision(*self.crop)
        return self.reader.observe(frame,read_inventory=False)

    def sample(self, vision, frame, obs, now):
        if obs.state not in ('ready','unknown','transition','reward_button','confirm'):return obs
        game=vision.normalize(frame)
        kind='ready' if obs.state=='ready' else 'overlay'
        if kind!=self.kind:self.kind,self.kind_at=kind,now
        if kind=='ready':
            if obs.button is None:return obs
            left,top,right,_=vision.rect
            my=(obs.button[1]-top)*540/(right-left)-177
            roi=game[max(0,int(my-28)):int(my+35),420:515]
            image=cv2.resize(roi,(64,40))
        else:
            image=cv2.resize(game,(64,96),interpolation=cv2.INTER_AREA)
        key=(kind,image)
        if self.future is not None and self.future.done():
            try:self.result=self.future.result()
            except Exception:self.result=None
            self.result_key=self.request_key
            self.capsule_key=(vision.capsule_button_signature(self.request_frame,self.result.dismiss_point)
                              if self.result is not None and self.result.dismiss_point is not None and
                              self.result.state in ('capsule_group','cardpack','confirm','reward_button') else None)
            self.dialog_key=(vision.dialog_signature(self.request_frame,self.result.dialog_bounds)
                             if self.result is not None and self.result.dialog_bounds else None)
            self.shop_key=None
            if self.result is not None and self.result.state=='purchase' and self.result.dialog_label=='活动补给礼包':
                requested=vision.normalize(self.request_frame)
                layout=supply_layout(requested)
                if layout:self.shop_key=(layout,supply_signature(requested,layout))
            self.future=None
        matches=(self.result_key is not None and self.result_key[0]==kind and
                 cv2.absdiff(image,self.result_key[1]).mean()<(.35 if kind=='ready' else 1.2))
        if kind=='overlay' and self.capsule_key is not None:
            current=vision.capsule_button_signature(frame,self.result.dismiss_point)
            button_matches=current is not None and cv2.absdiff(current,self.capsule_key).mean()<1.2
            matches=button_matches if self.result.state=='capsule_group' else matches and button_matches
        if kind=='overlay' and self.dialog_key is not None:
            current=vision.dialog_signature(frame,self.result.dialog_bounds)
            matches=current is not None and cv2.absdiff(current,self.dialog_key).mean()<1.2
            if matches and self.result.state=='panel':
                close=vision.visible_close(game,self.result.dialog_bounds)
                left,top,right,_=vision.rect;scale=540/(right-left)
                expected=((self.result.dismiss_point[0]-left)*scale,(self.result.dismiss_point[1]-top)*scale)
                matches=close is not None and sum(abs(a-b) for a,b in zip(close,expected))<8
        if kind=='overlay' and self.shop_key is not None:
            layout=supply_layout(game)
            matches=(layout==self.shop_key[0] and layout is not None and
                     cv2.absdiff(supply_signature(game,layout),self.shop_key[1]).mean()<1.2)
        if self.future is None and now-self.request_at>=1.2 and (kind=='ready' or now-self.kind_at>=.4):
            self.request_at=now;self.request_key=key
            self.request_frame=frame.copy()
            self.future=self.pool.submit(self.read,frame.copy())
        if matches and self.result is not None:
            if kind=='ready' and self.result.state=='ready':
                return replace(obs,multiplier=self.result.multiplier)
            if kind=='overlay' and (self.result.state in ('reward','cardpack','confirm','panel','capsule_group','purchase') or
                                   (self.result.state=='reward_button' and self.result.dialog_checked)):
                return self.result
        # A bare green/Confirm glyph could also belong to a purchase dialog.
        # Keep the engine waiting until the fresh page classification finishes.
        if obs.state in ('reward_button','confirm') and not obs.dialog_checked:
            return replace(obs,state='unknown',dismiss_point=None)
        return obs

    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True)
