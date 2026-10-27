"""Decision logic: clicks are committed only after acknowledged input."""
from dataclasses import dataclass, field

MULTIPLIERS = (1, 2, 3, 5, 10, 20, 50, 100, 150)
REWARDS = (
    ('wishbox', '心愿盒'), ('stars', '弹珠'), ('capsule', '扭蛋'),
    ('raft', '船'), ('lunchbox', '饭盒'), ('coins', '糖果'),
)


@dataclass
class Settings:
    desired_multiplier: int = 50
    priority: list = field(default_factory=lambda: [r[0] for r in REWARDS])
    mode: str = 'mumu_sdk'
    adb_path: str = ''
    adb_address: str = ''
    crop_top: int = 0
    crop_bottom: int = 0
    boat_budget: int = 0
    shutdown_on_stop: bool = False
    shutdown_force: bool = False


@dataclass
class Action:
    kind: str = 'wait'
    point: tuple | None = None
    message: str = ''
    purpose: str = ''
    label: str = ''


class Engine:
    def __init__(self, settings):
        self.settings = settings
        self.last_action = -100.
        self.pending = None
        self.pending_at = 0.
        self.active_round = False
        self.progress_seen = False
        self.round_at = 0.
        self.completed = 0
        self.used = 0
        self.seen = []
        self.target = None
        self.multiplier_pending = None
        self.multiplier_at = 0.
        self.multiplier_clicks = 0
        self.unknown_at = None
        self.last_known = None
        self.choice_at = None
        self.ready_at = None
        self.zero_at = None
        self.zero_last = None
        self.zero_reads = 0
        self.stock_at = None
        self.effective_desired = settings.desired_multiplier
        self.pending_choices = None
        self.round_stock = None
        self.round_cost = 0
        self.round_free = False
        self.stock_progress_at = None
        self.spin_retries = 0
        self.startup_checks = 0
        self.startup_deadline = 0.
        self.unchanged_at = None
        self.unchanged_last = None
        self.unchanged_reads = 0
        self.ambiguous_change = False
        self.round_visual = None
        self.round_pose = None
        self.outcome_at = None
        self.settle_until = 0.
        self.capsule_transition = False
        self.capsule_label = ''
        self.after_choice = False
        self.green_at = None
        self.pending_result = None
        self.result_candidate = None
        self.result_at = None
        self.cardpack_attempts = 0
        self.cardpack_started = None
        self.reward_attempts = 0
        self.reward_started = None
        self.reward_label = ''
        self.reward_point = None
        self.reward_visible_label = None
        self.reward_visible_at = None
        self.reward_visible_point = None
        self.selected_reward = None

    def update(self, values):
        if 'boat_budget' in values:
            value = values['boat_budget']
            if not isinstance(value, int) or value < 0:
                raise ValueError('Invalid boat budget')
            self.settings.boat_budget = value
            self.target = None
            self.seen = []
        if 'desired_multiplier' in values:
            value = values['desired_multiplier']
            if value not in MULTIPLIERS:
                raise ValueError('Unsupported multiplier')
            if value != self.settings.desired_multiplier:
                self.settings.desired_multiplier = value
                self.effective_desired = value
                self.seen = [self.multiplier_pending] if self.multiplier_pending else []
                self.target = None
                self.multiplier_clicks = 0
        if 'priority' in values:
            priority = values['priority']
            if sorted(priority) != sorted(r[0] for r in REWARDS):
                raise ValueError('Invalid reward priority')
            self.settings.priority = list(priority)

    def acknowledge(self, action, now, multiplier=None, stock=None, free=False, visual_signature=None, wheel_pose=None):
        self.last_action = now
        if action.purpose in ('cardpack','confirm','choice','capsule_group','reward_button'):
            if self.pending!=action.purpose:
                self.reward_attempts=0
                self.reward_started=now
            self.reward_attempts+=1
            self.reward_label=action.label
            self.reward_point=action.point
            self.reward_visible_at=self.reward_visible_point=self.reward_visible_label=None
            if action.purpose=='cardpack':
                self.cardpack_attempts=self.reward_attempts
                self.cardpack_started=self.reward_started
        if action.purpose in ('spin', 'choice', 'dismiss', 'cardpack', 'confirm', 'panel','capsule_group','reward_button'):
            self.pending = action.purpose
            self.pending_at = now
        if action.purpose in ('capsule_group','reward_button'):
            self.capsule_transition=False
            self.result_candidate=self.result_at=None
        if action.purpose in ('choice','capsule_group'):self.after_choice=True
        if action.purpose=='reward_button':self.capsule_label=''
        if action.purpose == 'spin':
            self.active_round = True
            self.progress_seen = False
            self.ready_at = None
            self.round_at = now
            self.round_stock = stock
            self.round_cost = multiplier or 0
            self.round_free = free
            self.round_visual = visual_signature
            self.round_pose = wheel_pose
            self.outcome_at = None
            self.stock_progress_at = None
            self.used += multiplier or 0
            self.spin_retries = 0
            self.ambiguous_change = False
        if action.purpose in ('spin', 'spin_retry'):
            if action.purpose == 'spin_retry':
                self.spin_retries += 1
                self.round_at = now
                self.ready_at = None
                self.pending = 'spin'
                self.pending_at = now
            self.startup_checks = 0
            self.startup_deadline = now+10
            self.stock_progress_at = None
            self.unchanged_at = self.unchanged_last = None
            self.unchanged_reads = 0
        if action.purpose == 'multiplier':
            self.multiplier_pending = multiplier
            self.multiplier_at = now
            self.multiplier_clicks += 1

    def multiplier_action(self, obs, now):
        value = obs.multiplier
        desired = self.effective_desired
        if value is None:
            if self.unknown_at is None:
                self.unknown_at = now
            return Action('stop' if now-self.unknown_at > 8 else 'wait', message='等待读取倍率；请确认倍率按钮清晰')
        self.unknown_at = None
        if obs.maximum and value <= desired:
            self.target = value
            self.multiplier_pending = None
            return None
        if self.multiplier_pending is not None:
            if value == self.multiplier_pending:
                if now-self.multiplier_at < 2:
                    return Action(message='等待倍率切换')
                # No response is not evidence of a cap, including x1.
                return Action('stop', message='倍率点击未响应，已停止；请检查连接或操作模式')
            self.multiplier_pending = None
        if value == desired or value == self.target:
            return None
        if value in self.seen:
            self.target = max(v for v in self.seen if v <= desired) if any(v <= desired for v in self.seen) else min(self.seen)
            if value == self.target:
                return None
        elif self.target is None:
            self.seen.append(value)
        if self.multiplier_clicks >= len(MULTIPLIERS)*2:
            return Action('stop', message='倍率连续切换异常，已停止')
        return Action('click', obs.multiplier_point, f'调整倍率：x{value} → x{desired}', 'multiplier')

    def observe_progress(self, obs, now):
        """Keep evidence even when slow recognition makes a frame unclickable."""
        if not self.active_round or now-self.round_at < .8:
            return
        if obs.motion or obs.state in ('reward', 'choice', 'cardpack', 'confirm','capsule_group') or (obs.state=='reward_button' and self.after_choice):
            self.progress_seen = True
            self.ready_at = None
            self.unchanged_reads = 0
        semantic = self.round_pose is not None and obs.wheel_pose is not None
        pairs=[(a,b) for a,b in zip(self.round_pose or (),obs.wheel_pose or ()) if min(a,b)>=0]
        delta=sum(a!=b for a,b in pairs) if len(pairs)>=22 else None
        visual_read = bool(self.round_visual) and bool(obs.visual_signature)
        if obs.state == 'ready' and (semantic or visual_read or obs.numbers_fresh) and not self.progress_seen:
            # Independent reads must confirm either the exact paid cost or
            # consumption of the central button's free-turn label.
            paid = not semantic and not visual_read and self.round_cost > 0 and self.round_stock is not None and obs.stock == self.round_stock-self.round_cost
            free_used = self.round_free and not obs.free
            same_visual = (delta is not None and delta<3) if semantic else (visual_read and len(self.round_visual) == len(obs.visual_signature) and
                           sum(abs(a-b) for a,b in zip(self.round_visual, obs.visual_signature))/len(self.round_visual) < 2)
            if semantic and delta is not None and delta>=3 and not obs.motion:
                if self.outcome_at is None:self.outcome_at=now
                elif now-self.outcome_at>=.3:
                    self.progress_seen=True
                    self.ready_at=None
            else:self.outcome_at=None
            unchanged = (not obs.motion and obs.free == self.round_free and
                         (self.round_free or obs.multiplier == self.round_cost) and
                         (same_visual if semantic or visual_read else
                          self.round_stock is not None and obs.stock == self.round_stock))
            if unchanged:
                if self.unchanged_at is None:
                    self.unchanged_at = self.unchanged_last = now
                    self.unchanged_reads = 1
                elif now-self.unchanged_last >= .3:
                    self.unchanged_last = now
                    self.unchanged_reads += 1
            else:
                self.unchanged_at = self.unchanged_last = None
                self.unchanged_reads = 0
                if (obs.free != self.round_free or (not semantic and visual_read and not same_visual) or
                    (not visual_read and obs.stock is not None and self.round_stock is not None and obs.stock != self.round_stock)):
                    self.ambiguous_change = True
            if paid or free_used:
                if self.stock_progress_at is None:
                    self.stock_progress_at = now
                elif now-self.stock_progress_at >= .3:
                    self.progress_seen = True
                    self.ready_at = None
            else:
                self.stock_progress_at = None

    def step(self, obs, now):
        if obs.state=='purchase':
            return Action('stop',message='检测到活动补给或购买窗口，已停止；请手动处理后重新开始')
        self.observe_progress(obs, now)
        if obs.state!='reward_button':self.green_at=None
        if obs.state!=self.pending:
            self.reward_visible_at=self.reward_visible_point=self.reward_visible_label=None
        if self.pending in ('capsule_group','reward_button') and obs.state in ('ready','reward','choice','cardpack','confirm','panel'):
            self.capsule_transition=True
        if obs.state != 'unknown':
            self.last_known = now
        elif self.last_known is None:
            self.last_known = now
        elif now-self.last_known > 35:
            return Action('stop', message='长时间未识别漂流界面，已停止；请检查画面与边距')
        if now-self.last_action < .8:
            return Action(message='等待操作结果')
        if self.pending in ('choice', 'dismiss', 'cardpack', 'confirm', 'panel','capsule_group','reward_button'):
            expected = {'dismiss': 'reward'}.get(self.pending, self.pending)
            if expected in ('capsule_group','reward_button'):
                if obs.state in ('unknown','transition'):
                    if now-self.reward_started>12:return Action('stop',message='等待扭蛋结果切换超时，已停止')
                    return Action(message='等待扭蛋结果切换')
                if obs.state in ('capsule_group','reward_button'):
                    changed_label=bool(self.capsule_label and obs.capsule_label and obs.capsule_label!=self.capsule_label)
                    changed_label=changed_label or bool(self.reward_label and obs.dialog_label and self.reward_label!=obs.dialog_label)
                    changed_result=False
                    if self.pending_result and obs.capsule_result:
                        distance=sum(abs(a-b) for a,b in zip(self.pending_result,obs.capsule_result))/5
                        if distance>.30:
                            if self.result_candidate is None or sum(abs(a-b) for a,b in zip(self.result_candidate,obs.capsule_result))/5>.08:
                                self.result_candidate=obs.capsule_result;self.result_at=now
                            else:changed_result=now-self.result_at>=.4
                        else:self.result_candidate=self.result_at=None
                    if self.capsule_transition or changed_label or changed_result:
                        if now-self.pending_at<1.2:return Action(message='等待扭蛋结果切换')
                        self.pending=None;expected=None
                    else:expected=obs.state
            if expected == 'choice' and tuple(r for r, _ in obs.choices) != self.pending_choices:
                self.pending = None
                expected = None
            if expected in ('cardpack','confirm','choice') and obs.state in ('unknown','transition'):
                if now-self.reward_started>8:
                    return Action('stop',message='奖励点击后页面未关闭，已停止；请检查操作模式')
                return Action(message='等待奖励页面切换')
            if obs.state == expected:
                if expected in ('cardpack','confirm','choice','capsule_group','reward_button'):
                    if now-self.reward_started>8:
                        return Action('stop',message='奖励点击后页面未关闭，已停止；请检查操作模式')
                    label,point=self.confirmed_reward_button(obs,expected)
                    if label and point is not None and (not self.reward_label or label==self.reward_label):
                        if (self.reward_visible_point is None or label!=self.reward_visible_label or
                                max(abs(a-b) for a,b in zip(point,self.reward_visible_point))>8):
                            self.reward_visible_at=now
                        self.reward_visible_point,self.reward_visible_label=point,label
                        if self.reward_attempts<3 and now-self.last_action>=1.6 and now-self.reward_visible_at>=.4:
                            return Action('click',point,f'{label} {self.reward_attempts+1}/3',expected,label)
                    else:self.reward_visible_at=self.reward_visible_point=self.reward_visible_label=None
                if now-self.pending_at > 8:
                    return Action('stop', message='奖励点击后页面未关闭，已停止；请检查操作模式')
                return Action(message='等待奖励页面关闭')
            if obs.state == 'unknown':
                return Action(message='等待奖励页面切换')
            self.pending = None
        if obs.state == 'choice':
            self.takeover(now)
            self.progress_seen = True
            if self.choice_at is None:
                self.choice_at = now
            # All three must be identified before ranking; otherwise a better
            # unknown reward could be silently skipped.
            if len(obs.choices) != 3 or any(r is None for r, _ in obs.choices):
                return Action('stop' if now-self.choice_at > 15 else 'wait', message='有奖励尚未识别，请补充奖励图示后再选择')
            reward, point = min(obs.choices, key=lambda choice: self.settings.priority.index(choice[0]))
            label = dict(REWARDS)[reward]
            self.pending_choices = tuple(r for r, _ in obs.choices)
            self.selected_reward=reward
            return Action('click', point, f'按优先级选择：{label}', 'choice','选择')
        self.choice_at = None
        if obs.state == 'reward':
            self.takeover(now)
            self.progress_seen = True
            return Action('click', obs.dismiss_point, '收取奖励，点击空白关闭', 'dismiss')
        if obs.state=='capsule_group':
            self.takeover(now)
            self.capsule_label=obs.capsule_label
            self.pending_result=obs.capsule_result
            return Action('click',obs.dismiss_point,f'继续本次扭蛋奖励：{obs.capsule_label}','capsule_group',obs.capsule_label)
        if obs.state=='reward_button':
            if obs.reward_context:self.after_choice=True
            if not self.after_choice:
                if self.green_at is None:self.green_at=now
                return Action('stop' if now-self.green_at>8 else 'wait',
                              message='正在确认绿色按钮所属页面；未确认奖励流程前不点击')
            self.takeover(now)
            self.pending_result=obs.capsule_result
            return Action('click',obs.dismiss_point,'继续领取所选奖励：点击绿色按钮','reward_button',obs.dialog_label)
        if obs.state in ('cardpack', 'confirm', 'panel'):
            if obs.state!='panel':self.takeover(now)
            return Action('click', obs.dismiss_point,
                          {'cardpack': '卡包：开心收下', 'confirm': '确认领取已选择的奖励', 'panel': '返回漂流转盘'}[obs.state], obs.state,
                          {'cardpack':'开心收下','confirm':'确定','panel':''}[obs.state])
        # Changing the multiplier redraws the wheel's numbers and can show a
        # short animation. That is not a submitted or inherited rafting round.
        multiplier_redraw = not self.active_round and self.multiplier_pending is not None and obs.state == 'ready'
        if not self.active_round and ((obs.motion and not multiplier_redraw) or (obs.state == 'transition' and obs.dialog_bounds is None)):
            self.takeover(now)
        if self.active_round:
            if obs.state != 'ready' or obs.motion:
                if obs.state!='unknown' and self.round_pose is None:self.progress_seen = True
                self.ready_at = None
                if now-self.round_at > 90:
                    return Action('stop', message='漂流或结算等待超时，已停止')
                return Action(message='等待转盘、漂流与奖励结算')
            if not self.progress_seen:
                if now-self.round_at > 30:
                    return Action('stop', message='启动转盘未确认，已停止；请检查游戏画面')
                if self.stock_progress_at is not None and now-self.stock_progress_at < 3:
                    return Action(message='正在确认本轮转盘已启动')
                if now-self.round_at > 10:
                    fresh_evidence = obs.visual_signature is not None if self.round_visual is not None else obs.numbers_fresh
                    confirmed_unchanged = (fresh_evidence and not self.ambiguous_change and
                                           self.unchanged_reads >= 2 and self.unchanged_at is not None and
                                           now-self.unchanged_at >= .9)
                    if self.spin_retries >= 2:
                        return Action('stop', message='启动转盘未确认，已停止；请检查游戏画面')
                    if confirmed_unchanged:
                        return Action('click',obs.button,f'转盘未响应，重新尝试 {self.spin_retries+2}/3','spin_retry')
                    if now >= self.startup_deadline:
                        if self.startup_checks >= 2:
                            return Action('stop', message='启动转盘未确认，已停止；请检查游戏画面')
                        self.startup_checks += 1
                        self.startup_deadline = now+5
                        return Action(message=f'等待转盘开始，重新检查 {self.startup_checks+1}/3')
                return Action(message='等待转盘开始')
            if self.ready_at is None:
                self.ready_at = now
            if now-self.ready_at < .9 or now-self.round_at < 6:
                return Action(message='等待漂流结算稳定')
            self.active_round = False
            self.pending = None
            self.completed += 1
            self.seen = []
            self.target = None
            self.multiplier_pending = None
            self.multiplier_clicks = 0
            self.round_stock = None
            self.stock_progress_at = None
            self.settle_until = now+.35 if obs.wheel_pose is not None else now
            self.after_choice = False
            # This same ready screen already passed the settlement check.
            # Reuse it for the next multiplier/budget decision instead of
            # starting an additional readiness timer on the following frame.
            return Action(message='本轮完成，重新检查倍率')
        if obs.state != 'ready' or obs.motion:
            self.ready_at = None
            self.zero_at = self.zero_last = None
            self.zero_reads = 0
            if multiplier_redraw:
                return Action('stop' if now-self.multiplier_at > 8 else 'wait', message='等待倍率画面稳定')
            return Action(message='等待漂流转盘界面')
        if now<self.settle_until:
            return Action(message='等待下一轮按钮就绪')
        if self.ready_at is None:
            self.ready_at = now
        if now-self.ready_at < .3:
            return Action(message='确认转盘已就绪')
        self.zero_at = self.zero_last = None
        self.zero_reads = 0
        remaining = self.settings.boat_budget-self.used if self.settings.boat_budget else None
        if remaining is not None and remaining <= 0 and not obs.free:
            return Action('stop', message=f'漂流预算已完成：已提交用船 {self.used} / {self.settings.boat_budget}', purpose='auto_stop')
        if obs.free:
            # The free turn can lock the multiplier. Apply the desired tier
            # again once the next paid turn becomes available.
            return Action('click', obs.button, '免费转盘，等待漂流', 'spin')
        desired = self.settings.desired_multiplier
        if remaining is not None and not obs.free:
            desired = max(v for v in MULTIPLIERS if v <= min(desired, remaining))
        if desired != self.effective_desired:
            self.effective_desired = desired
            self.target = None
            self.seen = []
        change = self.multiplier_action(obs, now)
        if change:
            return change
        if remaining is not None and obs.multiplier > remaining:
            return Action('stop', message='剩余预算不足当前实际倍率，已停止', purpose='auto_stop')
        return Action('click', obs.button, '启动转盘，等待漂流', 'spin')

    def confirmed_reward_button(self,obs,purpose):
        """Recheck current text and target; never reuse an old click position."""
        if purpose=='choice':
            if obs.dialog_label=='选择' and len(obs.choices)==3 and all(k for k,_ in obs.choices):
                return '选择',next((p for k,p in obs.choices if k==self.selected_reward),None)
            return '',None
        if purpose=='cardpack':
            return ('开心收下',obs.dismiss_point) if obs.dialog_label in ('','开心收下') else ('',None)
        if purpose=='capsule_group':
            return (obs.capsule_label,obs.dismiss_point) if obs.capsule_label in ('再开一组','开启全部','全部开启') else ('',None)
        allowed=('确定',) if purpose=='confirm' else ('领取','领取奖励','开心收下','继续','继续领取')
        if obs.dialog_checked and obs.dialog_label in allowed:
            return obs.dialog_label,obs.dismiss_point
        return '',None

    def takeover(self, now):
        self.ready_at = None
        if not self.active_round:
            self.active_round = True
            self.round_at = now
        self.progress_seen = True
