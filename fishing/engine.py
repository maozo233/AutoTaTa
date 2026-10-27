"""Pure decision logic; no native handles or input in this module."""
from dataclasses import dataclass
from .vision import MULTIPLIERS
from .bait import BaitMaintenance

FIGHT_LEAD_PIXELS = 14

@dataclass
class Settings:
    desired_multiplier: int = 50
    auto_bait: bool = False
    full_bait_protection: bool = False
    stop_on_bait_end: bool = False
    stop_when_buffs_end: bool = False
    mode: str = 'mumu_sdk'
    ui_scale: float = 1.0
    adb_path: str = ""
    adb_address: str = ""
    crop_top: int = 0
    crop_bottom: int = 0
    bait_limit: int = 1
    rod_budget: int = 0
    shutdown_on_stop: bool = False
    shutdown_force: bool = False

@dataclass
class Action:
    kind: str
    point: tuple | None = None
    message: str = ''
    purpose: str = ''
    rods: int = 0

class Engine:
    def __init__(self, settings):
        self.settings = settings
        self.last_action = -100.
        self.last_fight_action = -100.
        self.fight_round = 0
        self.fight_clicks = 0
        self.fight_active = False
        self.fight_sample = None
        self.fight_early = False
        self.ready_since = None
        self.absent_since = None
        self.bait = BaitMaintenance(settings)
        self.bait_pending = None
        self.bait_verified = False
        self.bait_phase = None
        self.bait_used = 0
        self.next_bait_at = None
        self.multiplier_done = False
        self.seen = []
        self.pending_multiplier = None
        self.pending_time = 0.
        self.target = None
        self.multiplier_clicks = 0
        self.multiplier_unknown_since = None
        self.last_state = 'unknown'
        self.last_known = None
        self.catch_count = 0
        self.rods_used = 0
        self.rods_zero_since = None
        self.pending_rods = 0
        self.initial_reading_since = None
        self.cast_submitted_at = None
        self.cast_fallback_sent = False
        self.result_counted = False

    def update_desired_multiplier(self, value):
        if value not in MULTIPLIERS:
            raise ValueError('Unsupported multiplier')
        if value == self.settings.desired_multiplier:
            return False
        self.settings.desired_multiplier = value
        self.multiplier_done = False
        self.target = None
        # A previously submitted click may still be animating; keep awaiting it.
        self.seen = [] if self.pending_multiplier is None else [self.pending_multiplier]
        self.multiplier_clicks = 0
        self.multiplier_unknown_since = None
        return True

    def needs_multiplier(self):
        return not self.multiplier_done

    def acknowledge(self, action, now):
        if action.purpose == 'cast':
            self.pending_rods = action.rods
            self.cast_submitted_at = now
            self.cast_fallback_sent = False
        if action.purpose == 'bait_confirm':
            self.bait.submitted(now)

    @property
    def bait_used(self):
        return self.bait.used

    @bait_used.setter
    def bait_used(self, value):
        self.bait.used = value

    @property
    def bait_phase(self):
        return self.bait.phase

    @bait_phase.setter
    def bait_phase(self, value):
        self.bait.phase = value

    def bait_limit_reached(self):
        return self.bait.at_limit()

    def anticipate_fight(self, obs, now):
        previous=self.fight_sample
        self.fight_sample=(now,obs.float_x,obs.yellow) if obs.float_x is not None and obs.yellow else None
        if obs.in_yellow or previous is None or self.fight_sample is None:
            return False
        before,x0,zone0=previous
        if not 0 < now-before <= .2 or max(abs(a-b) for a,b in zip(zone0,obs.yellow)) > 8:
            return False
        x=obs.float_x;left,right=obs.yellow
        if obs.track_bounds is None:return False
        track_left,track_right=obs.track_bounds
        if not 0<=track_left<track_right<=540 or not track_left<=left<right<=track_right:
            return False
        if not track_left<=x<=track_right:return False
        delta=x-x0
        # Bound the lead to fourteen normalized pixels and require real movement
        # toward a stable target. Never expand the trailing/exit edge blindly.
        if abs(delta)>40:
            return False
        if max(track_left,left-FIGHT_LEAD_PIXELS) <= x < left+1:
            return delta>.25 and x0 < left+1
        if right-1 < x <= min(track_right,right+FIGHT_LEAD_PIXELS):
            return delta<-.25 and x0 > right-1
        return False

    def step(self, obs, now):
        if obs.state == 'purchase':
            return Action('stop',message='检测到活动补给礼包页面，已停止钓鱼；请手动处理后重新开始。')
        self.bait.observe(obs, now)
        pending_bait = self.bait.action(obs, now, Action)
        if pending_bait:
            return pending_bait
        if self.pending_rods and obs.state in ('waiting', 'hook', 'fight', 'purple_wait', 'result'):
            self.rods_used += self.pending_rods
            self.pending_rods = 0
        if obs.state in ('waiting','hook','fight','purple_wait','result'):
            self.cast_submitted_at=None
            self.cast_fallback_sent=False
        if obs.state=='ready' and self.cast_submitted_at is not None:
            elapsed=now-self.cast_submitted_at
            if elapsed<2:return Action('wait',message='等待抛竿进入咬饵阶段')
            if self.settings.mode=='mumu_sdk' and not self.cast_fallback_sent:
                self.cast_fallback_sent=True
                return Action('click',obs.button,'MuMuSDK抛竿未响应，尝试一次ADB触摸','cast_fallback')
            if elapsed<5:return Action('wait',message='等待抛竿操作确认')
            return Action('stop',message='抛竿点击后未进入等待咬饵；可能模拟器被遮挡后暂停渲染或不接受触摸。请检查MuMu后台运行设置或使用通用ADB模式。')
        if obs.state=='ready' and obs.rod_upgrade_hint:
            self.multiplier_unknown_since=None
            if now-self.last_action<1:return Action('wait',message='等待鱼竿升级提示消失')
            self.last_action=now
            return Action('click',obs.dismiss_point,'收起鱼竿升级提示，重新读取倍率','dismiss_upgrade_hint')
        if self.last_known is None or obs.state != 'unknown':
            self.last_known = now
        elif now-self.last_known > 12:
            return Action('stop', message='长时间未识别到钓鱼界面，请检查画面或裁剪边距。')
        self.fight_early = False
        if obs.state in ('ready', 'waiting', 'result'):
            self.fight_active = False
            self.fight_sample = None
        if obs.state == 'fight' and not self.fight_active:
            self.fight_round += 1
            self.fight_clicks = 0
            self.fight_active = True
        self.last_state = obs.state
        if obs.state != 'ready':
            self.rods_zero_since = None
            self.ready_since = None
            self.absent_since = None
        if obs.state == 'bait_menu':
            return Action('stop', message='检测到手动打开的鱼饵弹窗，请关闭后重新开始。')
        if obs.state == 'result':
            if not self.result_counted:
                self.catch_count += 1
                self.result_counted = True
            if now-self.last_action >= .85:
                self.last_action = now
                return Action('click', obs.dismiss_point, '关闭钓鱼结果')
        elif obs.state == 'hook':
            if now-self.last_action >= .40:
                self.last_action = now
                return Action('click', obs.button, '咬杆：拉钩')
        elif obs.state == 'fight':
            self.fight_early = self.anticipate_fight(obs,now)
            if (obs.in_yellow or self.fight_early) and now-self.last_fight_action+1e-9 >= .001:
                self.last_action = now
                self.last_fight_action = now
                self.fight_clicks += 1
                return Action('click', obs.button, f'控鱼第{self.fight_round}轮，第{self.fight_clicks}次点击：'+(f'预判入条（最多提前{FIGHT_LEAD_PIXELS}px）' if self.fight_early else '浮漂进入黄条'), 'fight')
        elif obs.state == 'ready':
            self.result_counted = False
            if obs.bait_sample_at is not None and (self.bait.level is None or self.bait.current is None):
                if self.initial_reading_since is None:self.initial_reading_since=now
                if now-self.initial_reading_since<3:
                    return Action('wait',message='首次抛竿前确认鱼竿等级与幸运值')
            if obs.remaining_rods == 0:
                if self.rods_zero_since is None:self.rods_zero_since=now
                if now-self.rods_zero_since >= .4:
                    return Action('stop',message='剩余鱼竿已为0，自动停止钓鱼。',purpose='auto_stop')
                return Action('wait',message='确认剩余鱼竿为0；暂停抛竿和用饵')
            self.rods_zero_since = None
            if self.ready_since is None:
                self.ready_since = now
            if now-self.ready_since < .35 or now-self.last_action < .4:
                return Action('wait')
            if self.settings.rod_budget > 0:
                remaining = self.settings.rod_budget-self.rods_used-self.pending_rods
                if remaining <= 0:
                    return Action('stop', message=f'本次用竿预算已用完：预算 {self.settings.rod_budget} 根，已用 {self.rods_used} 根，待确认 {self.pending_rods} 根。', purpose='auto_stop')
                # Resolve the actual multiplier before opening bait or casting.
                if not self.multiplier_done:
                    multiplier = self.check_multiplier(obs, now)
                    if multiplier:
                        return multiplier
                if obs.multiplier is None:
                    return Action('stop', message='无法确认实际倍率，已停止以避免超出用竿预算。')
                if obs.multiplier > remaining:
                    return Action('stop', message=f'剩余用竿预算 {remaining} 根，不足下一竿实际倍率 x{obs.multiplier}，已停止；不会超预算抛竿。', purpose='auto_stop')
            bait = self.check_bait(obs, now)
            if bait:
                return bait
            if not self.multiplier_done:
                multiplier = self.check_multiplier(obs, now)
                if multiplier:
                    return multiplier
            self.last_action = now
            self.multiplier_done = False
            self.pending_multiplier = None
            self.seen = []
            self.target = None
            self.multiplier_clicks = 0
            self.multiplier_unknown_since = None
            return Action('click', obs.button, '抛竿', 'cast', rods=obs.multiplier or 0)
        return Action('wait')

    def check_bait(self, obs, now):
        return self.bait.action(obs, now, Action, ready=True)

    def check_multiplier(self, obs, now):
        value = obs.multiplier
        if value is None:
            if self.multiplier_unknown_since is None:
                self.multiplier_unknown_since = now
            if now-self.multiplier_unknown_since < 2:
                return Action('wait', message='等待倍率动画结束及数字清晰')
            return Action('stop', message='持续无法读取倍率，已停止。请放大到建议客户区 315×599 或更大（最低 250×484），确保倍率数字清晰后重新开始。')
        self.multiplier_unknown_since = None
        desired = self.settings.desired_multiplier
        if obs.multiplier_max and value <= desired:
            # Positive game feedback: unchanged value is the actual ceiling,
            # not a transport failure. Never infer a ceiling from silence alone.
            self.target = value
            self.pending_multiplier = None
            self.multiplier_done = True
            return None
        if self.pending_multiplier is not None:
            if value == self.pending_multiplier:
                if now-self.pending_time < 2:
                    return Action('wait', message='等待倍率切换')
                # A single available x1 does not change on a click.
                if value == 1 and self.seen == [1]:
                    self.target = 1
                else:
                    return Action('stop', message='倍率点击后未变化，已停止。可尝试切换操作模式；仍无响应请检查停止截图与日志。')
            self.pending_multiplier = None
        if value == desired or value == self.target:
            self.multiplier_done = True
            return None
        if value in self.seen:
            maximum = max(self.seen)
            self.target = max(v for v in self.seen if v <= min(maximum, desired))
            if value == self.target:
                self.multiplier_done = True
                return None
        elif self.target is None:
            self.seen.append(value)
        if len(self.seen) > len(MULTIPLIERS):
            return Action('stop', message='倍率切换异常，已停止。')
        self.pending_multiplier = value
        self.multiplier_clicks += 1
        if self.multiplier_clicks > 24:
            return Action('stop', message='倍率连续切换仍未达到目标，已停止。')
        self.pending_time = self.last_action = now
        return Action('click', obs.multiplier_point, f'调整倍率：当前 x{value}，期望 x{desired}' )
