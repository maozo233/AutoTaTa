"""Full-stack bait maintenance. No input handles; every attempt has an outcome gate."""
import random


class StableReading:
    def __init__(self):
        self.candidate = self.value = None
        self.since = self.updated = -100.
        self.count = 0

    def push(self, value, now):
        if value is None:
            self.candidate = self.value = None
            self.count = 0
            return
        if value != self.candidate:
            self.candidate, self.since, self.count = value, now, 1
            self.value = None
        else:
            self.count += 1
        if self.count >= 3 and now - self.since >= .6:
            self.value, self.updated = value, now

    def get(self, now):
        return self.value if now - self.updated <= 1.8 else None


class BaitMaintenance:
    # Conservative observation window, not a claim about measured animation length.
    TEAM_GRACE = 15.
    ANIMATION_MIN = 12.
    TIMEOUT = 35.

    def __init__(self, settings, delay=None):
        self.settings = settings
        self.delay = delay or (lambda: random.SystemRandom().uniform(1., 7.))
        self.grade = StableReading()
        self.luck = StableReading()
        self.stock = StableReading()
        self.sample_at = None
        self.level = self.current = self.target = None
        self.used = 0
        self.phase = None
        self.deadline = None
        self.started = 0.
        self.before_stock = None
        self.consumed = False
        self.cap_seen = False
        self.activity_at = -100.
        self.clear_since = None
        self.unknown_since = None
        self.inventory_unknown_since = None
        self.previous_luck = None
        self.status = '等待识别鱼竿与幸运值'
        self.failure = None
        self.fresh = False

    def at_limit(self):
        return self.settings.bait_limit > 0 and self.used >= self.settings.bait_limit

    def refill_capacity(self, obs, now):
        if not self.settings.auto_bait or self.settings.stop_when_buffs_end or not obs.bait_available or self.at_limit():
            return 0
        stock=self.stock.get(now)
        if stock is None:return None
        remaining=max(0,self.settings.bait_limit-self.used) if self.settings.bait_limit>0 else stock
        return min(stock,remaining)

    def wait_for_expiry(self, A):
        self.deadline=None
        self.inventory_unknown_since=None
        if self.settings.stop_on_bait_end and self.current==self.level:
            return A('stop',message='无法补满且鱼饵增益已结束；当前一竿已完成，停止钓鱼。',purpose='auto_stop')
        self.status=('不足以补满 · 保留鱼饵，继续钓鱼至增益结束' if self.settings.stop_on_bait_end
                     else '满幸运值保护 · 保留鱼饵，继续钓鱼攒饵')
        return None

    def observe(self, obs, now):
        if obs.bait_motion:
            self.activity_at = now
            self.clear_since = None
        if obs.bait_sample_at is not None and obs.bait_sample_at != self.sample_at:
            self.sample_at = obs.bait_sample_at
            self.grade.push(obs.rod_level, now)
            self.luck.push(None if obs.bait_motion else obs.luck, now)
            self.stock.push(obs.bait_stock, now)
        grade, luck = self.grade.get(now), self.luck.get(now)
        if grade is not None and grade != self.level:
            self.level, self.target = grade, grade + 4
            self.deadline = None
        self.fresh = grade is not None and luck is not None and grade <= luck <= grade + 4
        # Display the confirmed clover reading independently of rod recognition.
        # Only fresh, mutually consistent readings can drive bait decisions.
        self.current = luck if luck is not None and 1 <= luck <= 8 else None
        if self.fresh:
            self.unknown_since = None
            if self.phase is None:
                if luck >= self.target:
                    self.deadline = None
                    self.status = '满饵维持中 · 幸运值下降时自动补饵'
                elif self.previous_luck is not None and luck > self.previous_luck:
                    # Only a confirmed increase rearms the window, never each frame.
                    self.deadline = now + self.TEAM_GRACE + self.delay()
            self.previous_luck = luck
        if self.phase in ('verifying', 'closing'):
            if obs.bait_capped:
                self.cap_seen = True
            stock = self.stock.get(now)
            if stock is not None and self.before_stock is not None and stock < self.before_stock and not self.consumed:
                delta = self.before_stock - stock
                self.used += delta
                self.consumed = True
                if delta != 1:
                    self.failure = '鱼饵库存减少数量异常，已暂停以核对本机用饵预算。'
            if obs.state == 'ready' and not obs.bait_motion and self.fresh:
                if self.clear_since is None:
                    self.clear_since = now
            else:
                self.clear_since = None

    def submitted(self, now):
        self.phase, self.started = 'verifying', now
        self.clear_since = None
        self.status = '打窝中 · 等待动画结束'

    def _clear_attempt(self):
        self.phase = None
        self.deadline = None
        self.before_stock = None
        self.consumed = self.cap_seen = False
        self.clear_since = None

    def action(self, obs, now, make_action, ready=False):
        A = make_action
        if self.failure:
            return A('stop', message=self.failure)
        if self.phase:
            if now - self.started > self.TIMEOUT:
                return A('stop', message='打窝结果未确认，已暂停；不会重复用饵。请检查停止截图。')
            if self.phase == 'opening':
                self.status = '正在打开鱼饵弹窗'
                if obs.state == 'bait_menu':
                    if not self.settings.auto_bait or self.settings.stop_when_buffs_end or self.at_limit() or (self.fresh and self.current >= self.target):
                        self.phase = 'closing'
                        return A('click', obs.dismiss_point, '补饵已取消、预算已用完或队友已补满，关闭打窝弹窗', 'bait_cancel')
                    if not self.fresh:
                        return A('wait', message='等待幸运值稳定后确认打窝')
                    if self.settings.stop_on_bait_end or self.settings.full_bait_protection:
                        capacity=self.refill_capacity(obs,now)
                        if capacity is None:
                            return A('wait',message='确认剩余鱼饵是否足够补满')
                        if capacity < self.target-self.current:
                            self.phase='closing'
                            return A('click',obs.dismiss_point,'剩余鱼饵不足以补满，关闭弹窗并继续钓鱼','bait_cancel')
                    if obs.bait_confirm_point is not None:
                        self.phase = 'confirming'
                        return A('click', obs.bait_confirm_point, '确认打窝', 'bait_confirm')
                return A('wait', message=self.status)
            if self.phase == 'confirming':
                return A('wait', message='等待打窝操作提交')
            if self.cap_seen and obs.state == 'bait_menu' and self.phase != 'closing':
                self.phase = 'closing'
                self.status = '已达使用上限 · 等待幸运值同步'
                return A('click', obs.dismiss_point, '已达使用上限，关闭打窝弹窗', 'bait_dismiss')
            stable = self.clear_since is not None and now - self.clear_since >= 1.5
            if self.cap_seen and stable and self.current == self.target and self.stock.get(now) == self.before_stock:
                self._clear_attempt()
                return A('wait', message='已确认游戏满饵上限，本次未消耗鱼饵')
            if self.phase == 'closing' and stable:
                if self.cap_seen:
                    return A('wait', message='游戏已达上限，等待幸运值同步；不重复打窝')
                self._clear_attempt()
                return A('wait', message='打窝弹窗已关闭，重新检查幸运值')
            if self.consumed and stable and now - self.started >= self.ANIMATION_MIN and now - self.activity_at >= 1.5:
                self._clear_attempt()
                self.status = '打窝完成 · 重新检查幸运值'
                return A('wait', message=self.status)
            self.status = ('已达使用上限 · 等待画面恢复' if self.cap_seen else '打窝中 · 等待动画及库存确认')
            return A('wait', message=self.status)
        if not ready:
            return None
        if not (self.settings.auto_bait or self.settings.stop_on_bait_end or self.settings.stop_when_buffs_end):
            self.status = '自动补饵未开启'
            return None
        if not obs.bait_available and not (self.settings.stop_on_bait_end or self.settings.stop_when_buffs_end):
            self.deadline=None
            self.inventory_unknown_since=None
            self.unknown_since=None
            self.status='无可用鱼饵 · 继续钓鱼'
            return None
        if not self.fresh:
            self.status = '等待识别鱼竿与幸运值'
            if self.unknown_since is None:
                self.unknown_since = now
            if now - self.unknown_since > 10:
                return A('stop', message='鱼竿或幸运值识别不确定，已暂停；请放大游戏画面后重试。')
            return A('wait', message=self.status)
        if self.settings.stop_when_buffs_end and self.current == self.level:
            return A('stop', message='鱼饵增益已结束，幸运值回到基础值；当前一竿已完成，停止钓鱼。', purpose='auto_stop')
        if self.current >= self.target:
            self.deadline = None
            self.status = '满饵维持中 · 幸运值下降时自动补饵' if self.settings.auto_bait else '当前已满饵 · 自动补饵未开启'
            return None
        if self.settings.stop_when_buffs_end:
            self.status = '等待鱼饵增益结束 · 继续钓鱼'
            return None
        if self.settings.stop_on_bait_end or self.settings.full_bait_protection:
            capacity=self.refill_capacity(obs,now)
            if capacity is not None and capacity < self.target-self.current:
                return self.wait_for_expiry(A)
        if not obs.bait_available:
            self.deadline=None
            self.inventory_unknown_since=None
            self.status='无可用鱼饵 · 继续钓鱼'
            return None
        if self.deadline is None:
            self.deadline = now + self.TEAM_GRACE + self.delay()
        if now < self.deadline:
            self.status = '等待补饵 · 恢复满额则取消'
            return A('wait', message=self.status)
        stock = self.stock.get(now)
        unavailable = not self.settings.auto_bait or self.at_limit() or stock == 0
        if unavailable:
            reason = '预算已用完' if self.at_limit() else '无可用鱼饵' if stock == 0 else '自动补饵未开启'
            self.status = reason + ' · 等待队友补饵'
            return None
        if stock is None or not obs.bait_available:
            self.status = '鱼饵库存待确认 · 暂不提交打窝'
            if self.inventory_unknown_since is None:
                self.inventory_unknown_since = now
            if now - self.inventory_unknown_since > 10:
                return A('stop', message='无法确认鱼饵库存，已暂停以避免用饵预算失真。')
            return A('wait', message=self.status)
        self.inventory_unknown_since = None
        self.phase, self.started, self.before_stock = 'opening', now, stock
        self.consumed = self.cap_seen = False
        self.clear_since = None
        self.status = '正在打开鱼饵弹窗'
        return A('click', obs.bait_point, self.status, 'bait_open')

    def snapshot(self):
        return dict(baitDeadline=self.deadline, baitPhase=self.phase, baitAtLimit=self.at_limit(),
                    baitUsed=self.used, rodLevel=self.level, luckCurrent=self.current,
                    luckTarget=self.target, baitStatus=self.status)
