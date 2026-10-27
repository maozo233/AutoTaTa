"""Recognize the wheel and center reward cards; ignore header text."""
from dataclasses import dataclass, field
import re
import cv2
import numpy as np
from autotata.paths import ASSETS
from autotata.activity_shop import supply_layout, supply_shop
from fishing.vision import Vision as BaseVision
from .engine import MULTIPLIERS, REWARDS


@dataclass
class Observation:
    state: str = 'unknown'
    button: tuple | None = None
    multiplier_point: tuple | None = None
    dismiss_point: tuple | None = None
    multiplier: int | None = None
    maximum: bool = False
    stock: int | None = None
    choices: list = field(default_factory=list)
    motion: bool = False
    free: bool = False
    numbers_fresh: bool = False
    visual_signature: bytes | None = None
    wheel_pose: tuple | None = None
    capsule_label: str = ''
    capsule_result: tuple | None = None
    dialog_bounds: tuple | None = None
    dialog_label: str = ''
    reward_context: bool = False
    dialog_checked: bool = False


class Vision(BaseVision):
    def __init__(self, crop_top=0, crop_bottom=0):
        super().__init__(crop_top, crop_bottom)
        self.templates = {}
        self.rewards = {}
        for name in ('spin', 'maximum', 'select', 'reward-title', 'accept', 'confirm', 'close', 'free', 'capsule-next', 'capsule-all'):
            self.templates[name] = self.read_image(ASSETS/'rafting'/f'{name}.png')
        for key, _ in REWARDS:
            self.rewards[key] = self.read_image(ASSETS/'rafting/rewards'/f'{key}.png')
        self.lunchbox_card = self.read_image(ASSETS/'rafting/rewards/lunchbox-card.png')
        self.wishbox_card = self.read_image(ASSETS/'rafting/rewards/wishbox-card.png')
        self.wishbox_card_sdk = self.read_image(ASSETS/'rafting/rewards/wishbox-card-sdk.png')
        self.previous = None
        self.boat_anchor = None
        self.last_motion = False
        self.previous_pose = None

    @staticmethod
    def wheel_pose(game, bx, by):
        hsv=cv2.cvtColor(game,cv2.COLOR_BGR2HSV)
        result=[]
        for angle in np.linspace(205,335,28):
            samples=[]
            for radius in (135,160,185):
                rad=np.deg2rad(angle)
                x,y=round(bx+radius*np.cos(rad)),round(by+16+radius*np.sin(rad))
                samples.append(hsv[max(0,y-3):y+4,max(0,x-3):x+4].reshape(-1,3))
            colors=np.concatenate(samples)
            colors=colors[(colors[:,1]>90)&(colors[:,2]>120)]
            votes=[np.sum((colors[:,0]>=lo)&(colors[:,0]<=hi))
                   for lo,hi in ((88,119),(120,165),(18,45))]
            result.append(int(np.argmax(votes)) if max(votes)>=12 else -1)
        return tuple(result)

    @staticmethod
    def read_image(path):
        return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR) if path.exists() else None

    def read_text(self, roi, minimum=.65):
        if roi.size==0:return ''
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
        results,_=self.ocr(cv2.resize(roi,None,fx=3,fy=3))
        return ' '.join(item[1] for item in (results or []) if item[2]>=minimum)

    def recognize_digits(self, roi):
        if roi.size==0:return ''
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
        # The digit bounds are already known. DB text detection can miss
        # outlined numbers (979) or change their crop; recognize them directly.
        results,_=self.ocr(cv2.resize(roi,None,fx=3,fy=3),use_det=False,use_cls=False)
        if not results or len(results)!=1 or results[0][1]<.95:
            return ''
        return results[0][0].replace(' ','')

    def boat_motion(self, game):
        """Track hull horizontal displacement, ignoring avatar/vertical bobbing.

        Return None when the hull is obscured, so the caller can use the
        averaged scenery fallback rather than assume a moving boat is idle.
        """
        h=game.shape[0]
        roi=game[int(h*.40):int(h*.60),100:450]
        mask=cv2.inRange(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV),(28,90,90),(75,255,255))
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
        _,_,stats,centers=cv2.connectedComponentsWithStats(mask)
        candidates=[(area,float(centers[i][0])) for i,(_,_,bw,bh,area) in enumerate(stats[1:],1)
                    if bw>100 and bw/bh>1.2 and area>900]
        if not candidates:
            self.boat_anchor=None
            return None
        _,center=max(candidates)
        if self.boat_anchor is None:
            self.boat_anchor=center
            return False
        # Accumulate from the last confirmed position so slow, sustained drift
        # still registers; tolerate up to 9 normalized pixels of idle sway.
        moving=abs(center-self.boat_anchor)>=10
        if moving:self.boat_anchor=center
        return moving

    def set_rect(self, frame):
        h, w = frame.shape[:2]
        if w >= h:
            raise RuntimeError('请使用竖屏漂流大赛窗口')
        if self.crop_top or self.crop_bottom:
            top, bottom = self.crop_top, h-self.crop_bottom
        else:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            # Dark reward overlays must not be mistaken for letterboxing.
            # A native toolbar remains pale even when the game is dimmed.
            pale = ((hsv[:, :, 1] < 25) & (hsv[:, :, 2] > 170)).mean(axis=1)
            toolbar = np.flatnonzero(pale[:round(h*.12)] > .65)
            top = int(toolbar[-1]+1) if len(toolbar) > h*.015 else 0
            bottom = h
        if not 0 <= top < bottom <= h or bottom-top < w*1.3:
            raise RuntimeError('漂流画面裁剪不完整，请调整顶部和底部边距')
        self.rect = (0, top, w, bottom)

    def button_free(self, game, bx, by):
        roi=game[max(0,int(by+8)):min(game.shape[0],int(by+52)),max(0,int(bx-52)):min(540,int(bx+52))]
        return self.locate(self.templates['free'],roi,(.85,.95,1.,1.1))[0]>.78

    @staticmethod
    def stock_region(game, by):
        # The icon and number are centered together. More digits move the
        # leading digit left; a fixed narrow numeric crop truncates 1000.
        return game[max(0,int(by+65)):min(len(game),int(by+101)),195:370]

    def read_stock(self, roi):
        if roi.size == 0:
            return None
        # Use white bodies only to locate the number. Feeding their binary
        # mask to OCR changes the glyph context and reads 999 as 666.
        mask=cv2.inRange(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV),(0,0,180),(180,60,255))
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        digits=[i for i,(x,y,w,h,area) in enumerate(stats[1:],1)
                if 8<=h<=25 and 2<=w<=22 and area>=15]
        if not digits:
            return None
        boxes=stats[digits]
        boxes=boxes[np.argsort(boxes[:,0])]
        x0,y0=boxes[:,:2].min(axis=0)
        x1,y1=(boxes[:,:2]+boxes[:,2:4]).max(axis=0)
        numeric=roi[max(0,y0-1):min(len(roi),y1+1),max(0,x0-1):min(roi.shape[1],x1+1)]
        # Preserve original colors and outline; no artificial black canvas
        # and no second text-detector crop of the already located numerals.
        text=self.recognize_digits(numeric)
        def valid(value):
            return (re.fullmatch(r'\d+',value) and len(value)==len(digits) and
                    (len(value)==1 or not value.startswith('0')))
        if valid(text):
            return int(text)
        # Adjacent narrow 1s can collapse into one character in line OCR.
        # Recheck the already separated glyphs individually; each must still
        # be a high-confidence single digit. Never manufacture missing digits.
        parts=[]
        for x,y,w,h,_ in boxes:
            crop=roi[max(0,y-1):min(len(roi),y+h+1),max(0,x-1):min(roi.shape[1],x+w+1)]
            part=self.recognize_digits(crop)
            if not re.fullmatch(r'\d',part):return None
            parts.append(part)
        text=''.join(parts)
        return int(text) if valid(text) else None

    @staticmethod
    def locate(template, roi, scales=(.75, 1., 1.25)):
        best = (0., None, None)
        if template is None or roi.size == 0:
            return best
        for scale in scales:
            t = cv2.resize(template, None, fx=scale, fy=scale)
            if min(t.shape[:2]) < 5 or any(a > b for a, b in zip(t.shape[:2], roi.shape[:2])):
                continue
            score = cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED)
            _, confidence, _, pos = cv2.minMaxLoc(score)
            if confidence > best[0]:
                best = (confidence, pos, (t.shape[1], t.shape[0]))
        return best

    def classify_reward(self, roi):
        scores = []
        for key, template in self.rewards.items():
            confidence, _, _ = self.locate(template, roi, (.55, .65, .75, .85, 1., 1.15, 1.3, 1.5))
            if key == 'lunchbox':
                confidence = max(confidence, self.locate(self.lunchbox_card, roi, (.7, .85, 1., 1.15, 1.3))[0])
            if key == 'wishbox':
                for card in (self.wishbox_card, self.wishbox_card_sdk):
                    confidence = max(confidence, self.locate(card, roi, (.65, .75, .85, 1., 1.15, 1.3))[0])
            scores.append((confidence, key))
        scores.sort(reverse=True)
        return scores[0][1] if scores[0][0] >= .66 and scores[0][0]-scores[1][0] >= .06 else None

    @staticmethod
    def bottom_buttons(game, include_yellow=False):
        h,w=game.shape[:2]
        hsv=cv2.cvtColor(game,cv2.COLOR_BGR2HSV)
        mask=cv2.inRange(hsv,(35,90,65),(85,255,255))
        if include_yellow:
            mask=cv2.bitwise_or(mask,cv2.inRange(hsv,(15,90,65),(34,255,255)))
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        return [(int(x),int(y),int(bw),int(bh)) for x,y,bw,bh,area in stats[1:]
                if bw>w*.24 and h*.7<y<h*.94 and 20<bh<h*.12 and area>bw*bh*.4]

    def capsule_button_signature(self, frame, point):
        game=self.normalize(frame)
        left,top,right,_=self.rect;scale=540/(right-left)
        px,py=(point[0]-left)*scale,(point[1]-top)*scale
        for x,y,bw,bh in self.bottom_buttons(game,include_yellow=True):
            if x<=px<=x+bw and y<=py<=y+bh:
                # Only the button lettering; group counters and characters
                # are excluded, so their animation cannot invalidate OCR.
                roi=game[y+int(bh*.15):y+int(bh*.85),x+int(bw*.2):x+int(bw*.8)]
                mask=cv2.inRange(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV),(0,0,185),(180,70,255))
                return cv2.resize(mask,(64,24),interpolation=cv2.INTER_AREA)
        return None

    @staticmethod
    def capsule_result(game):
        # Five result positions; no inventory, batch count, or bottom button.
        # Hue distributions tolerate the recorded character glow animation.
        h=len(game);features=[]
        for cx,cy in ((270,.13),(120,.35),(410,.35),(180,.6),(410,.6)):
            roi=game[round(h*cy)-55:round(h*cy)+55,cx-55:cx+55]
            hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
            mask=(hsv[:,:,1]>100)&(hsv[:,:,2]>100)
            hist=np.histogram(hsv[:,:,0][mask],bins=12,range=(0,180))[0]/(roi.shape[0]*roi.shape[1])
            features.extend(hist.tolist())
        return tuple(features)

    @staticmethod
    def modal_rect(game):
        """A bright central dialog, separated from the dimmed activity."""
        h,w=game.shape[:2]
        hsv=cv2.cvtColor(game,cv2.COLOR_BGR2HSV)
        # Bright scenery/clouds are not dialogs. The actual overlay dims
        # the outer activity, while leaving its central panel readable.
        edge=round(w*.045)
        if np.median(np.concatenate((hsv[:,:edge,2].ravel(),hsv[:,-edge:,2].ravel())))>150:
            return None
        mask=cv2.inRange(hsv,(0,0,165),(180,55,255))
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(7,7)))
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        candidates=[(int(area),(int(x),int(y),int(bw),int(bh))) for x,y,bw,bh,area in stats[1:]
                    if bw>w*.5 and bh>h*.14 and area>bw*bh*.5 and
                    h*.07<y and y+bh<h*.95 and 8<x and x+bw<w-8]
        return max(candidates)[1] if candidates else None

    def dialog_signature(self, frame, bounds):
        game=self.normalize(frame)
        current=self.modal_rect(game)
        if current is None or any(abs(a-b)>8 for a,b in zip(current,bounds)):return None
        x,y,bw,bh=bounds
        return cv2.resize(game[y:y+bh,x:x+bw],(96,96),interpolation=cv2.INTER_AREA)

    def activity_anchor(self, game):
        h=len(game)
        return self.locate(self.templates['spin'],game[round(h*.55):,135:405],(.65,.8,1.,1.2))[0]>.72

    def visible_close(self, game, bounds=None):
        h,w=game.shape[:2]
        # Actual modal corner or its bottom return control. Do not search
        # arbitrary illustrations for an X, or click the dimmed game exit.
        regions=[(180,round(h*.78),360,h)]
        if bounds:
            x,y,bw,bh=bounds
            regions.extend([(max(0,x+bw-85),max(0,y-40),min(w,x+bw+35),min(h,y+85)),
                            (max(0,x+bw//2-80),max(0,y+bh-45),min(w,x+bw//2+80),min(h,y+bh+90))])
        else:regions.append((w-110,0,w,round(h*.22)))
        matches=[]
        for x,y,right,bottom in regions:
            score,p,size=self.locate(self.templates['close'],game[y:bottom,x:right],(.6,.8,1.,1.2,1.5))
            if score<=.82:continue
            px,py=x+p[0],y+p[1];sw,sh=size
            visible=(game[py:py+sh,px:px+sw].max(axis=2)>200).mean()>.08
            if visible:matches.append((score,(px+sw/2,py+sh/2)))
        return max(matches)[1] if matches else None

    def activity_dialog(self, game, bounds=None):
        h,w=game.shape[:2]
        if bounds:
            x,y,bw,bh=bounds;roi=game[y:y+bh,x:x+bw]
        else:roi=game[round(h*.08):round(h*.86),30:w-30]
        text=self.read_text(roi,minimum=.8).replace(' ','')
        boat_words=('漂流艇','漂流船','船不足','船数量','船用完','购买船','买船','船礼包')
        purchase_words=('购买','购入','去商店','前往商店','补充漂流艇','补充漂流船','兑换漂流艇','兑换漂流船')
        buying=any(word in text for word in purchase_words)
        explicit_boat=any(word in text for word in boat_words)
        activity=any(word in text for word in ('漂流大赛','漂流艇','冲刺距离','转盘','基础距离','漂流距离')) or self.activity_anchor(game)
        panel=next((word for word in ('比赛规则','活动规则','基础距离','距离概率','排行榜','排名奖励','奖励预览','累计奖励','大赛规则') if word in text),None)
        purchase_title=bool(re.match(r'(?:漂流大赛)?(?:购买|补充|兑换|漂流艇不足|漂流船不足|船不足|漂流艇已用完)',text))
        # Rules can explain how to purchase boats. Their heading and real
        # close control distinguish that prose from the purchase dialog.
        if activity and panel and panel in text[:32] and not purchase_title:
            point=self.visible_close(game,bounds)
            if point:
                return Observation('panel',dismiss_point=self.point(*point),dialog_bounds=bounds,dialog_label=panel)
            return None
        # A plain purchase title can also be identified by the actual boat
        # artwork within the modal, rather than bottom inventory digits.
        modal_boat=bool(buying and self.classify_reward(roi)=='raft')
        if buying and (explicit_boat or modal_boat):
            return Observation('purchase',dialog_bounds=bounds,dialog_label='漂流艇购买')
        if activity and panel and not buying:
            point=self.visible_close(game,bounds)
            if point:
                return Observation('panel',dismiss_point=self.point(*point),dialog_bounds=bounds,dialog_label=panel)
        # Direct takeover on a result page needs reward evidence AND a
        # recognized continuation label; a green purchase button is not enough.
        reward=any(word in text for word in ('奖励','恭喜获得','扭蛋结果'))
        buttons=self.bottom_buttons(game)
        if reward and not buying and len(buttons)==1:
            x,y,bw,bh=buttons[0]
            label=self.read_text(game[y+round(bh*.2):y+bh,x:x+bw],minimum=.85).replace(' ','')
            if label in ('确定','领取','领取奖励','开心收下','继续','继续领取'):
                return Observation('confirm' if label=='确定' else 'reward_button',dismiss_point=self.point(x+bw/2,y+bh/2),
                                   dialog_bounds=bounds,dialog_label=label,reward_context=True,dialog_checked=True,
                                   capsule_result=self.capsule_result(game))
        return None

    def reward_choices(self, game, partial=False):
        h, w = game.shape[:2]
        top, bottom = (0, h) if partial else (round(h*.2), round(h*.87))
        hsv = cv2.cvtColor(game[top:bottom], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 90, 65), (85, 255, 255))
        count, _, stats, _ = cv2.connectedComponentsWithStats(green)
        buttons = []
        for x, y, bw, bh, area in stats[1:]:
            if not w*.15 <= bw <= w*.32 or not 12 <= bh <= (h*.20 if partial else h*.08) or area < bw*bh*.35:
                continue
            y += top
            confidence, _, _ = self.locate(self.templates['select'], game[y:y+bh, x:x+bw], (.6, .8, 1., 1.2, 1.4, 1.6, 1.8, 2.))
            if confidence >= .64:
                buttons.append((x, y, bw, bh))
        buttons.sort()
        if len(buttons) != 3 or max(b[1] for b in buttons)-min(b[1] for b in buttons) > 12:
            return []
        choices = []
        for x, y, bw, bh in buttons:
            # Icon area immediately above each Select button; exclude quantity
            # strip and all title text floating above the three cards.
            left, right = max(0, x-8), min(w, x+bw+8)
            icon = game[max(0, y-round(bw*1.35)):max(0, y-round(bw*.43)), left:right]
            reward = self.classify_reward(icon)
            point = (x+bw/2, y+bh/2)
            choices.append((reward, point if partial else self.point(*point)))
        return choices

    def accept_button(self, game, read_text=False):
        """Only the green button and its lettering identify this result page."""
        matches=[]
        for x,y,bw,bh in self.bottom_buttons(game):
            roi=game[y:y+bh,x:x+bw]
            score=self.locate(self.templates['accept'],roi,(.75,.9,1.,1.15,1.3))[0]
            label=(self.read_text(roi[round(bh*.2):round(bh*.95)],minimum=.85).replace(' ','')
                   if read_text and score<=.76 else '')
            if score>.76 or label=='开心收下':
                matches.append(self.point(x+bw/2,y+bh/2))
        if len(matches)==1:
            return Observation('cardpack',dismiss_point=matches[0],dialog_label='开心收下',dialog_checked=read_text)
        return None

    def observe(self, frame, read_numbers=True, read_inventory=True):
        game = self.normalize(frame)
        h, w = game.shape[:2]
        shop = supply_layout(game)
        if shop:
            if read_numbers and supply_shop(game, shop, lambda roi: self.read_text(roi, minimum=.8)):
                return Observation('purchase',dialog_label='活动补给礼包')
            # Block green reward fallbacks while this multi-offer grid is checked.
            return Observation()
        accept=self.accept_button(game,read_text=read_numbers)
        if accept:return accept
        bounds=self.modal_rect(game)
        if bounds:
            dialog=self.activity_dialog(game,bounds) if read_numbers else None
            return dialog or Observation('unknown',dialog_bounds=bounds)
        bottom_buttons=self.bottom_buttons(game)
        continuation=(Observation('reward_button',dismiss_point=self.point(
            bottom_buttons[0][0]+bottom_buttons[0][2]/2,
            bottom_buttons[0][1]+bottom_buttons[0][3]/2),capsule_result=self.capsule_result(game),dialog_checked=read_numbers) if len(bottom_buttons)==1 else None)
        choices = self.reward_choices(game)
        if choices:
            return Observation('choice', choices=choices,dialog_label='选择')
        groups=[]
        # Yellow is eligible only with an explicit capsule label. The generic
        # reward continuation above remains limited to the green button.
        for x,y,bw,bh in self.bottom_buttons(game,include_yellow=True):
            roi=game[y:y+bh,x:x+bw]
            label=''
            if self.locate(self.templates['capsule-next'],roi,(.55,.7,.85,.95,1.,1.15,1.3))[0]>.82:
                label='再开一组'
            if self.locate(self.templates['capsule-all'],roi,(.55,.7,.85,.95,1.,1.15,1.3))[0]>.82:
                label='开启全部'
            aligned_green=any(abs(gy-y)<=12 for _,gy,_,_ in bottom_buttons)
            if read_numbers and (label or (x,y,bw,bh) in bottom_buttons or aligned_green):
                # The batch badge can overlap the top of the button.
                # Read only its label, never include the 5/10-style counter.
                label_roi=roi[round(bh*.2):round(bh*.95)]
                text=self.read_text(label_roi,minimum=.85).replace(' ','')
                if text in ('开启全部','全部开启','再开一组'):label=text
                elif continuation is not None and (x,y,bw,bh) in bottom_buttons and text in ('确定','领取','领取奖励','开心收下','继续','继续领取'):
                    continuation.dialog_label=text
            if label:groups.append((label,self.point(x+bw/2,y+bh/2)))
        if groups:
            label,point=min(groups,key=lambda item:0 if item[0] in ('开启全部','全部开启') else 1)
            return Observation('capsule_group',dismiss_point=point,capsule_label=label,capsule_result=self.capsule_result(game))
        if read_numbers and bottom_buttons:
            dialog=self.activity_dialog(game)
            if dialog:return dialog
        # Explicit buttons outrank blank-dismiss rewards. Match their labels
        # inside a wide green bottom button, never across unrelated page text.
        hsv = cv2.cvtColor(game, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 90, 65), (85, 255, 255))
        _, _, stats, _ = cv2.connectedComponentsWithStats(green)
        for x, y, bw, bh, area in stats[1:]:
            if not (bw > w*.65 and h*.7 < y < h*.94 and 20 < bh < h*.12 and area > bw*bh*.4):
                continue
            roi = game[y:y+bh, x:x+bw]
            for name, state in (('confirm', 'confirm'),):
                score = self.locate(self.templates[name], roi, (.75, .9, 1., 1.15, 1.3))[0]
                if score > .76:
                    return Observation(state, dismiss_point=self.point(x+bw/2, y+bh/2),dialog_label='确定',dialog_checked=read_numbers)
        title_roi = game[round(h*.08):round(h*.3), 60:480]
        if self.locate(self.templates['reward-title'], title_roi, (.75, .9, 1., 1.1, 1.25))[0] > .78:
            return Observation('reward', dismiss_point=self.point(270, h*.80))
        # Confirm the raft glyph and colored wheel, rather than clicking an
        # assumed coordinate on unrelated event screens.
        y0 = round(h*.72)
        confidence, pos, size = self.locate(self.templates['spin'], game[y0:round(h*.98), 155:385], (.85, .95, 1., 1.1))
        if confidence > .70:
            bx, by = 155+pos[0]+size[0]/2, y0+pos[1]+size[1]/2
            wheel = game[max(0, int(by-190)):int(by-85), 40:500]
            hsv = cv2.cvtColor(wheel, cv2.COLOR_BGR2HSV)
            colored = ((hsv[:, :, 0] > 88) & (hsv[:, :, 0] < 160) & (hsv[:, :, 1] > 100)).mean() if wheel.size else 0
            if colored > .3:
                if (hsv[:, :, 2] > 125).mean() < .4:
                    if read_numbers:
                        dialog=self.activity_dialog(game)
                        if dialog:return dialog
                    return continuation or Observation('transition')
                # Relative to the recognized main button; works with toolbar
                # crop, resized captures and simulator internal resolution.
                mx, my = 464, by-177
                obs = Observation('ready', self.point(bx, by), self.point(mx, my), self.point(270, h*.76))
                # The raft idles/bobs continuously. Measure wheel rotation and
                # coarse scenery scrolling separately; idle animation must not
                # keep settlement waiting forever (calibrated against video).
                wheel_sample = cv2.resize(game[round(h*.67):round(h*.85), 50:490], (64,32))
                # Average the whole scenery cells. Linear shrinking samples a
                # few individual pixels; at SDK resolution and slower capture
                # cadence, bobbing avatars can then look like map scrolling.
                scene_sample = cv2.resize(game[round(h*.25):round(h*.45), 180:440], (12,12), interpolation=cv2.INTER_AREA)
                boat_moving=self.boat_motion(game)
                obs.wheel_pose = self.wheel_pose(game,bx,by)
                pairs=[(a,b) for a,b in zip(self.previous_pose or (),obs.wheel_pose) if min(a,b)>=0]
                rotating = len(pairs)>=22 and sum(a!=b for a,b in pairs)>=3
                obs.motion = bool(self.previous is not None and (
                    (rotating if len(pairs)>=22 else cv2.absdiff(wheel_sample,self.previous[0]).mean() > 12) or
                    (boat_moving if boat_moving is not None else
                     cv2.absdiff(scene_sample,self.previous[1]).mean() > 10)))
                self.previous = (wheel_sample,scene_sample)
                self.previous_pose = obs.wheel_pose
                # Exclude stock, multiplier toast, and avatars from retry
                # evidence. These freshly captured pixels are independent of OCR.
                route_sample = cv2.resize(game[round(h*.18):round(h*.35),300:420],
                                          (12,12), interpolation=cv2.INTER_AREA)
                obs.visual_signature = (cv2.resize(wheel_sample, (32,16)).tobytes()
                                        + route_sample.tobytes())
                obs.free = self.button_free(game,bx,by)
                if read_numbers:
                    obs.numbers_fresh = True
                    # Gray/hovered x1 in the reference video has lower OCR
                    # confidence. Only accept an exact supported number here.
                    text = self.read_text(game[max(0, int(my-28)):int(my+27), 420:515],minimum=.52).lower().replace(' ', '').replace('×', 'x')
                    match = re.fullmatch(r'[xх]?([0-9]{1,3})', text)
                    obs.multiplier = int(match[1]) if match and int(match[1]) in MULTIPLIERS else None
                    if obs.multiplier is None:
                        # Hover highlights/cursor edges can change OCR layout
                        # with a one-pixel shift. Retry within the same circle.
                        text=self.read_text(game[max(0,int(my-20)):int(my+35),420:515],minimum=.52).lower().replace(' ','').replace('×','x')
                        match=re.fullmatch(r'[xх]?([0-9]{1,3})',text)
                        obs.multiplier=int(match[1]) if match and int(match[1]) in MULTIPLIERS else None
                    if read_inventory:
                        obs.stock = self.read_stock(self.stock_region(game,by))
                    # A free turn is labelled on the central yellow button;
                    # the stock underneath still shows the normal boat count.
                    # Never read the wheel's separate free-distance outcome.
                maximum_roi = game[max(0, int(my-55)):int(my+15), 155:390]
                obs.maximum = self.locate(self.templates['maximum'], maximum_roi, (.85, .95, 1.))[0] > .74
                return obs
        self.previous = None
        self.previous_pose = None
        self.boat_anchor = None
        if read_numbers:
            dialog=self.activity_dialog(game)
            if dialog:return dialog
            text = self.read_text(game[round(h*.22):round(h*.72), 60:480]).replace(' ', '')
            if ('点击空白' in text or '点击任意' in text) and any(word in text for word in ('奖励', '获得', '领取', '关闭', '继续')):
                return Observation('reward', dismiss_point=self.point(270, h*.8))
        return continuation or Observation()
