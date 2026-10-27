from dataclasses import dataclass
import re
import cv2
import numpy as np
from .paths import ASSETS
from autotata.activity_shop import supply_layout, SupplyShopReader

MULTIPLIERS = (1, 2, 3, 5, 10, 20, 50, 100)

def inside_yellow(float_x, yellow):
    # Coordinates are normalized to a 540px-wide game image. React near either
    # edge; one pixel inside the detected fill avoids uncertain border pixels.
    return yellow[0] + 1 <= float_x <= yellow[1] - 1

@dataclass
class Observation:
    state: str
    button: tuple
    multiplier_point: tuple
    bait_point: tuple
    dismiss_point: tuple
    multiplier: int | None = None
    bait_available: bool = False
    timer: str = 'unknown'
    in_yellow: bool = False
    yellow: tuple | None = None
    float_x: float | None = None
    bait_confirm_point: tuple | None = None
    track_bounds: tuple | None = None
    multiplier_max: bool = False
    rod_upgrade_hint: bool = False
    remaining_rods: int | None = None
    rod_level: int | None = None
    luck: int | None = None
    bait_stock: int | None = None
    bait_capped: bool = False
    bait_motion: bool = False
    bait_sample_at: float | None = None

def track_bounds(bar, zone):
    # Locate the pale inner rim near both ends, rather than extending into the
    # black frame or scenery. These search windows use normalized game pixels.
    cy=int(zone[1]+zone[3]/2)
    rows=bar[max(0,cy-2):min(bar.shape[0],cy+3)]
    if rows.size==0:return None
    rim=(rows[:,:,1]<80)&(rows[:,:,2]>160)
    left=[];right=[]
    for row in rim:
        ls=np.flatnonzero(row[25:65])+25
        rs=np.flatnonzero(row[280:318])+280
        if len(ls):left.append(int(ls.max())+106)
        if len(rs):right.append(int(rs.min())+104)
    if len(left)<3 or len(right)<3:return None
    lo,hi=int(np.median(left)),int(np.median(right))
    return (lo,hi) if 130<=lo<=175 and 390<=hi<=422 and hi-lo>=200 else None

class Vision:
    def __init__(self, crop_top=0, crop_bottom=0):
        self.rect = None
        self.crop_top, self.crop_bottom = crop_top, crop_bottom
        self.ocr = None
        self.supply_reader = SupplyShopReader()
        self.templates = {}
        for name in ('bait', 'title', 'hook_prompt', 'record', 'reward', 'accept', 'bait-confirm', 'bait-clock', 'multiplier-max', 'bait-flight'):
            path = ASSETS / f'{name}.png'
            if path.exists():
                self.templates[name] = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)

    def set_rect(self, frame):
        h, w = frame.shape[:2]
        if w >= h:
            raise RuntimeError('请使用竖屏游戏窗口。')
        if self.crop_top or self.crop_bottom:
            top, bottom = self.crop_top, h-self.crop_bottom
        else:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            # MuMu toolbar is pale gray; the game starts with saturated scenery.
            row_color = ((hsv[:, :, 1] > 35) & (hsv[:, :, 2] > 100)).mean(axis=1)
            candidates = np.flatnonzero(row_color[:int(h*.25)] > .30)
            if not len(candidates):
                raise RuntimeError('未找到游戏区域，请回到绿色鱼竿界面，或设置裁剪边距。')
            top = int(candidates[0])
            # A pale sky can put the first saturated row inside the game title.
            # Use the known title to recover the toolbar boundary before cropping.
            title_template = self.templates.get('title')
            if title_template is not None:
                full = cv2.resize(frame, (540, round(h*540/w)))
                header = full[:round(full.shape[0]*.25), 150:435]
                scores = cv2.matchTemplate(header, title_template, cv2.TM_CCOEFF_NORMED)
                _, confidence, _, position = cv2.minMaxLoc(scores)
                if confidence > .68:
                    top = max(0, round((position[1]-14)*w/540))
            dark = (hsv[:, :, 2] < 65).mean(axis=1)
            candidates = np.flatnonzero(dark[int(h*.80):] > .88) + int(h*.80)
            bottom = int(candidates[0]) if len(candidates) else h
        if bottom-top < w*1.35:
            raise RuntimeError('游戏区域识别不完整，请手动设置裁剪边距。')
        self.rect = (0, top, w, bottom)

    def normalize(self, frame):
        if self.rect is None:
            self.set_rect(frame)
        x, y, right, bottom = self.rect
        game = frame[y:bottom, x:right]
        return cv2.resize(game, (540, round(game.shape[0]*540/game.shape[1])))

    def point(self, x, y):
        left, top, right, _ = self.rect
        scale = (right-left)/540
        return left+x*scale, top+y*scale

    def match(self, name, roi):
        template = self.templates.get(name)
        if template is None or roi.shape[0] < template.shape[0] or roi.shape[1] < template.shape[1]:
            return 0.
        return float(cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED).max())

    def read_text(self, roi):
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        enlarged = cv2.resize(roi, None, fx=3, fy=3)
        results, _ = self.ocr(enlarged)
        return ' '.join(item[1] for item in (results or []) if item[2] >= .65)

    def read_multiplier(self, game):
        h = game.shape[0]
        text = self.read_text(game[h-180:h-110, 330:410]).lower().replace('×', 'x').replace(' ', '')
        match = re.fullmatch(r'[xх]?([0-9]{1,3})', text)
        value = int(match[1]) if match else None
        return value if value in MULTIPLIERS else None

    def read_rod_upgrade_hint(self, game):
        h=game.shape[0]
        text=self.read_text(game[h-230:h-120,210:530]).replace(' ','')
        return '可以领取' in text and '鱼竿' in text and '高级' in text

    def read_remaining_rods(self, game):
        h=game.shape[0]
        # Exclude the decorative rod icon, which OCR can mistake for a digit.
        text=self.read_text(game[h-45:h-3,255:330]).replace(' ','')
        if not re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:[,，][0-9]{3})+)',text):
            return None
        return int(text.replace(',','').replace('，',''))

    def button_colors(self, game, hsv=None):
        """Only the large action button, never the small remaining-rod icon."""
        if hsv is None:hsv=cv2.cvtColor(game,cv2.COLOR_BGR2HSV)
        h=game.shape[0]
        roi=hsv[h-168:h-40,206:334]
        if roi.shape[:2]!=(128,128):return 0.,0.,0.
        ys,xs=np.ogrid[:128,:128]
        radius=(xs-64)**2+(ys-64)**2
        ring=(radius>48**2)&(radius<64**2)
        green=(roi[:,:,0]>=35)&(roi[:,:,0]<=85)&(roi[:,:,1]>100)&(roi[:,:,2]>130)
        purple=(roi[:,:,0]>=125)&(roi[:,:,0]<=165)&(roi[:,:,1]>100)&(roi[:,:,2]>130)
        gray=(roi[:,:,1]<60)&(roi[:,:,2]>95)
        return tuple(float(mask[ring].mean()) for mask in (green,purple,gray))

    def read_rod_level(self, game):
        # Grade is read from the shaft inside the GREEN cast button only.
        # Brown / purple / gold / red correspond to base luck 1 / 2 / 3 / 4.
        if self.button_colors(game)[0] <= .50:return None
        h = game.shape[0]
        roi = cv2.cvtColor(game[h-145:h-65, 225:300], cv2.COLOR_BGR2HSV)
        yy, xx = np.indices(roi.shape[:2])
        # Thin diagonal strip over the shaft; excludes reel, bobber and green ring.
        mask = (abs(xx-(61-yy*.6)) < 12) & (yy > 14) & (yy < 58)
        mask &= (roi[:, :, 1] > 105) & (roi[:, :, 2] > 85)
        hues = roi[:, :, 0][mask]
        if len(hues) < 55:
            return None
        counts = [int(((hues >= 7) & (hues <= 15)).sum()),
                  int(((hues >= 125) & (hues <= 155)).sum()),
                  int(((hues >= 16) & (hues <= 34)).sum()),
                  int(((hues <= 6) | (hues >= 170)).sum())]
        best = int(np.argmax(counts))
        ranked = sorted(counts, reverse=True)
        if ranked[0] < 55 or sum(counts) < len(hues)*.25 or ranked[0] < sum(counts)*.55 or ranked[0] < ranked[1]*(1.45 if best == 2 else 1.6):
            return None
        return best + 1

    def read_luck_crop(self, roi):
        """Extract the yellow glyph, then recognize one upright digit, not a text line.

        Hue/geometry are calibrated from real 1, 2, 4, 6 crops. Other digits use
        the recognizer's learned shape inference, not invented game templates.
        """
        if roi.size == 0:
            return None
        h, w = roi.shape[:2]
        mask = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), (20, 80, 165), (35, 255, 255))
        _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        candidates = []
        for i, (x, y, dw, dh, area) in enumerate(stats[1:], 1):
            if (max(7, h*.22) <= dh <= h*.65 and .18 <= dw/dh <= 1.1
                    and dw <= w*.5 and .25*w <= x+dw/2 <= .78*w
                    and .18*h <= y+dh/2 <= .8*h and area >= 15):
                candidates.append((i, x, y, dw, dh))
        if len(candidates) != 1:
            return None
        i, x, y, dw, dh = candidates[0]
        glyph = (labels[y:y+dh, x:x+dw] == i).astype(np.uint8)*255
        glyph = 255-cv2.resize(glyph, (max(1, round(dw*40/dh)), 40))
        if self.ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        readings = []
        for pad in (2, 6):
            image = cv2.copyMakeBorder(glyph, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
            result, _ = self.ocr(cv2.cvtColor(image, cv2.COLOR_GRAY2BGR), use_det=False, use_cls=False)
            if not result or len(result) != 1:
                return None
            text, confidence = result[0]
            if confidence < .95 or not re.fullmatch(r'[1-8]', text):
                return None
            readings.append(int(text))
        return readings[0] if readings[0] == readings[1] else None

    def read_luck(self, game):
        h = game.shape[0]
        # Current luck comes only from the bottom-left clover's inner digit.
        # Its timer, rod colour and multiplier are separate measurements.
        roi=game[h-188:h-132,22:86]
        if roi.size==0:return None
        hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
        clover=(hsv[:,:,0]>=35)&(hsv[:,:,0]<=85)&(hsv[:,:,1]>90)&(hsv[:,:,2]>90)
        if int(clover.sum())<50:return None
        value = self.read_luck_crop(roi)
        if value is not None:
            return value
        # Preserve the original contextual OCR for partially washed-out glyphs.
        # The bait state machine still excludes animation frames and debounces.
        text = self.read_text(game[h-188:h-132, 22:86]).replace(' ', '')
        if not re.fullmatch(r'[1-8]', text):
            text = self.read_text(game[h-184:h-140, 30:77]).replace(' ', '')
        return int(text) if re.fullmatch(r'[1-8]', text) else None

    def read_bait_stock(self, game, available):
        if not available:
            return 0
        h = game.shape[0]
        value = self.read_text(game[h-145:h-100, 450:525]).replace(' ', '')
        return int(value) if re.fullmatch(r'[0-9]{1,5}', value) else None

    def read_bait_cap(self, game):
        text = self.read_text(game[135:225, 170:375]).replace(' ', '')
        return '已达使用上限' in text or '已達使用上限' in text

    def bait_animation(self, game):
        h = game.shape[0]
        flying = self.match('bait-flight', game[max(0,h-440):h-190, 100:330]) > .73
        roi = cv2.cvtColor(game[h-215:h-125, :120], cv2.COLOR_BGR2HSV)
        mask = ((roi[:, :, 0] >= 20) & (roi[:, :, 0] <= 37) &
                (roi[:, :, 1] > 55) & (roi[:, :, 2] > 190)).astype(np.uint8)
        # Exclude fixed clover and its internal number; look for surrounding stars.
        mask[25:85, 26:94] = 0
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        stars = [r for r in stats[1:] if 3 <= r[2] <= 22 and 3 <= r[3] <= 22 and 7 <= r[4] <= 250]
        return flying or len(stars) >= 2

    def read_timer(self, game):
        h = game.shape[0]
        # Timer is diagnostic only; full-stack maintenance reads the clover's luck.
        roi = game[h-145:h-101, 8:115]
        clock = self.match('bait-clock', roi) > .76
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        white = ((hsv[:, :, 1] < 65) & (hsv[:, :, 2] > 180)).astype(np.uint8)
        count, _, stats, _ = cv2.connectedComponentsWithStats(white)
        glyphs = [s for s in stats[1:] if 5 <= s[3] <= 24 and 2 <= s[2] <= 22 and s[4] >= 8]
        if not glyphs and not clock:
            return 'absent'
        text = self.read_text(roi).replace(' ', '')
        if clock or re.search(r'\d{1,2}[:：][0-5]\d', text):
            return 'active'
        return 'unknown'

    def observe(self, frame, read_multiplier=False, read_timer=False):
        game = self.normalize(frame)
        h = game.shape[0]
        hsv = cv2.cvtColor(game, cv2.COLOR_BGR2HSV)
        button = self.point(270, h-104)
        obs = Observation('unknown', button, self.point(367, h-150), self.point(482, h-155), button)
        green, purple, gray = self.button_colors(game,hsv)
        # Reject unrelated screens: title plus fishing-button ring must both be visible.
        title = self.match('title', game[:140, 150:435]) > .68
        # The offer grid covers the fishing controls. Keep active-fight frames
        # on the existing fast path; run OCR only on a matching shop layout.
        if not title:
            shop = supply_layout(game, hsv)
            if shop:
                if self.supply_reader.recognize(game, shop, self.read_text):
                    obs.state = 'purchase'
                obs.button = obs.dismiss_point = None
                return obs
        confirm = self.templates.get('bait-confirm')
        menu_roi = game[max(0,h-475):h-195, 310:535]
        if title and purple <= .45 and confirm is not None and self.match('bait-confirm', menu_roi) > .83:
            scores = cv2.matchTemplate(menu_roi, confirm, cv2.TM_CCOEFF_NORMED)
            _, _, _, pos = cv2.minMaxLoc(scores)
            obs.state = 'bait_menu'
            obs.bait_confirm_point = self.point(310+pos[0]+confirm.shape[1]/2,
                                               max(0,h-475)+pos[1]+confirm.shape[0]/2)
            obs.dismiss_point = self.point(270, h-370)
        elif title and green > .50:
            obs.state = 'ready'
        elif title and purple > .45:
            bar = hsv[h-280:h-210, 105:425]
            red = (((bar[:,:,0] < 14) | (bar[:,:,0] > 170)) & (bar[:,:,1] > 115) & (bar[:,:,2] > 95)).astype(np.uint8)
            yellow = ((bar[:,:,0] >= 20) & (bar[:,:,0] <= 38) & (bar[:,:,1] > 110) & (bar[:,:,2] > 145)).astype(np.uint8)
            n, _, stats, centers = cv2.connectedComponentsWithStats(red)
            markers = [(s, c) for s, c in zip(stats[1:], centers[1:]) if 10 <= s[3] <= 65 and 5 <= s[2] <= 35 and s[4] > 45]
            n, _, stats, _ = cv2.connectedComponentsWithStats(yellow)
            zones = [s for s in stats[1:] if s[2] > 8 and 5 <= s[3] <= 32 and s[4] > 55]
            if markers and zones:
                marker = max(markers, key=lambda pair:pair[0][4])[1]
                zone = max(zones, key=lambda s:s[4])
                obs.float_x = float(marker[0]+105)
                # The float occludes the yellow fill and can split it in two.
                # Merge only fragments at the same vertical position in this bar.
                aligned = [s for s in zones if abs(int(s[1])-int(zone[1])) <= 4]
                obs.yellow = (int(min(s[0] for s in aligned)+105),
                              int(max(s[0]+s[2] for s in aligned)+105))
                obs.in_yellow = inside_yellow(obs.float_x, obs.yellow)
                obs.track_bounds = track_bounds(bar,zone)
                obs.state = 'fight'
            elif self.match('hook_prompt', game[h-340:h-200, 95:435]) > .75:
                obs.state = 'hook'
            else:
                obs.state = 'purple_wait'
        elif title and gray > .42 and green < .12 and purple < .12:
            obs.state = 'waiting'
        else:
            # Only dismiss supplied, recognizable fishing reward overlays.
            if max(self.match('record', game), self.match('reward', game)) > .70:
                obs.state = 'result'
                green_full = (hsv[:,:,0] >= 35) & (hsv[:,:,0] <= 85) & (hsv[:,:,1] > 100) & (hsv[:,:,2] > 130)
                n, _, stats, centers = cv2.connectedComponentsWithStats(green_full.astype(np.uint8))
                accepts = [(s, c) for s, c in zip(stats[1:], centers[1:]) if s[1] > h*.72 and s[2] > 85 and s[3] > 22 and s[4] > 1500]
                if accepts:
                    obs.dismiss_point = self.point(*max(accepts, key=lambda pair:pair[0][4])[1])
                template = self.templates.get('accept')
                if template is not None:
                    scores = cv2.matchTemplate(game, template, cv2.TM_CCOEFF_NORMED)
                    _, confidence, _, pos = cv2.minMaxLoc(scores)
                    if confidence > .72:
                        obs.dismiss_point = self.point(pos[0]+template.shape[1]/2, pos[1]+template.shape[0]/2)
        if obs.state in ('ready', 'bait_menu'):
            obs.bait_motion = self.bait_animation(game)
            if obs.state == 'ready':
                obs.multiplier_max = self.match('multiplier-max',game[max(0,h-370):h-230,100:425]) > .85
            obs.bait_available = self.match('bait', game[h-210:h-100, 430:530]) > .72
            if read_multiplier:
                obs.multiplier = self.read_multiplier(game)
            if read_timer:
                obs.timer = self.read_timer(game)
        return obs
