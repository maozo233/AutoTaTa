"""Real supply page plus explicitly transformed layout and negative controls."""
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from autotata.activity_shop import supply_layout, supply_shop, SupplyShopReader
from fishing.vision import Vision as FishingVision, Observation as FishingObservation
from fishing.engine import Engine as FishingEngine, Settings as FishingSettings
from rafting.vision import Vision as RaftingVision
from rafting.engine import Engine as RaftingEngine, Settings as RaftingSettings, Action

ROOT = Path(__file__).resolve().parents[1]


class ActivityShopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = RaftingVision.read_image(ROOT/'assets/fixtures/rafting/activity-supply-shop-real.png')
        cls.vision = RaftingVision()
        cls.game = cls.vision.normalize(cls.frame)

    def test_real_page_and_scaled_captures_use_button_labels(self):
        self.assertEqual(len(supply_layout(self.game).buttons), 6)
        for scale in (.7, 1., 1.4):
            with self.subTest(scale=scale):
                frame = cv2.resize(self.frame, None, fx=scale, fy=scale)
                vision = RaftingVision(); vision.ocr = self.vision.ocr
                obs = vision.observe(frame, True, False)
                self.vision.ocr = vision.ocr
                self.assertEqual(obs.state, 'purchase')
                self.assertIsNone(obs.button); self.assertIsNone(obs.dismiss_point)
                self.assertIsNone(obs.stock)

    def test_shifted_reordered_four_card_layout_remains_a_shop(self):
        # Reorder four real card crops, with new padding and row spacing.
        canvas = np.full((1000, 540, 3), (28, 23, 30), np.uint8)
        cards = [self.game[260:450, 8:266], self.game[260:450, 277:530],
                 self.game[470:660, 8:266], self.game[470:660, 277:530]]
        for card, (x, y) in zip((cards[1], cards[0], cards[2], cards[3]),
                                ((18, 325), (283, 325), (18, 615), (283, 615))):
            card = cv2.resize(card, (238, 177))
            canvas[y:y+177, x:x+238] = card
        layout = supply_layout(canvas)
        self.assertIsNotNone(layout); self.assertEqual(len(layout.buttons), 4)
        self.assertTrue(supply_shop(canvas, layout, lambda roi: self.vision.read_text(roi, minimum=.8)))

    def test_all_free_grid_requires_bundle_title(self):
        layout = supply_layout(self.game)
        all_green = replace(layout, buttons=tuple(replace(b, color='green') for b in layout.buttons))
        read = MagicMock(side_effect=['免费']*6+['活动大礼包'])
        self.assertTrue(supply_shop(self.game, all_green, read))
        self.assertFalse(supply_shop(self.game, all_green, MagicMock(side_effect=['免费']*6+['奖励选择'])))
        changed = self.game.copy()
        source = next(b for b in layout.buttons if b.color == 'green')
        sx, sy, sw, sh = source.bounds
        for button in layout.buttons:
            if button.color == 'yellow':
                x, y, w, h = button.bounds
                changed[y:y+h, x:x+w] = cv2.resize(self.game[sy:sy+sh, sx:sx+sw], (w, h))
        transformed = supply_layout(changed)
        self.assertIsNotNone(transformed)
        self.assertTrue(supply_shop(changed, transformed, lambda roi: self.vision.read_text(roi, minimum=.8)))

    def test_prices_need_currency_and_green_needs_exact_free_label(self):
        layout = supply_layout(self.game)
        self.assertFalse(supply_shop(self.game, layout, MagicMock(side_effect=['12', '免费', '18', '免费', '免费', '免费', '礼包'])))
        self.assertFalse(supply_shop(self.game, layout, MagicMock(side_effect=['¥12', '选择', '¥18', '领取', '确定', '开心收下'])))

    def test_reward_pages_and_ready_boards_do_not_trigger_grid_gate(self):
        names = ['choice-full', 'cardpack-three', 'confirm-full', 'capsule-batch-next-and-all-phone',
                 'reward-button-synthetic', 'rules-synthetic']
        for name in names:
            path = ROOT/'assets/fixtures/rafting'/f'{name}.png'
            if not path.exists():
                self.fail(f'Missing negative fixture: {name}')
            vision = RaftingVision(); game = vision.normalize(vision.read_image(path))
            self.assertIsNone(supply_layout(game), name)
        for name in ('ready', 'waiting', 'fight-inside', 'result', 'bait-menu'):
            frame = RaftingVision.read_image(ROOT/'assets/fixtures'/f'{name}.png')
            game = cv2.resize(frame, (540, round(frame.shape[0]*540/frame.shape[1])))
            self.assertIsNone(supply_layout(game), name)

    def test_grid_text_change_invalidates_cached_shop(self):
        layout = supply_layout(self.game); reader = SupplyShopReader()
        read = MagicMock(return_value='')
        read.side_effect = ['¥12', '免费', '¥18', '免费', '免费', '免费']
        self.assertTrue(reader.recognize(self.game, layout, read))
        read.reset_mock(side_effect=True)
        self.assertTrue(reader.recognize(self.game.copy(), layout, read))
        read.assert_not_called()
        changed = self.game.copy()
        for b in layout.buttons:
            x, y, w, h = b.bounds; changed[y:y+h, x:x+w] = (0, 0, 0)
        read.return_value = ''
        self.assertFalse(reader.recognize(changed, layout, read))
        self.assertTrue(read.called)

    def test_rafting_async_verification_blocks_reward_fallback(self):
        from rafting.controls import ControlReader
        vision = RaftingVision(); fast = vision.observe(self.frame, False, False)
        self.assertEqual(fast.state, 'unknown'); self.assertIsNone(fast.dismiss_point)
        verified = self.vision.observe(self.frame, True, False)
        reader = ControlReader(); future = Future()
        engine = RaftingEngine(RaftingSettings()); engine.after_choice = True
        try:
            with patch.object(reader.pool, 'submit', return_value=future):
                self.assertNotEqual(engine.step(reader.sample(vision, self.frame, fast, 0), 0).kind, 'click')
                reader.sample(vision, self.frame, fast, .5); future.set_result(verified)
                checked = reader.sample(vision, self.frame, fast, .7)
                self.assertEqual(checked.state, 'purchase')
                self.assertEqual(engine.step(checked, .7).kind, 'stop')
                animated = self.frame.copy(); animated[40:280] = (30, 30, 30)
                self.assertEqual(reader.sample(vision, animated, fast, .8).state, 'purchase')
                # An old shop OCR result cannot replace a fresh changed page.
                other = self.frame.copy(); other[350:850] = 0
                self.assertNotEqual(reader.sample(vision, other, fast, .9).state, 'purchase')
        finally:
            reader.close()

    def test_uncertain_ocr_is_rechecked_on_an_unchanged_page(self):
        reader = SupplyShopReader(); layout = supply_layout(self.game)
        text = MagicMock(return_value='')
        with patch('autotata.activity_shop.time.monotonic', return_value=10):
            self.assertFalse(reader.recognize(self.game, layout, text))
        text.reset_mock(); text.side_effect = ['¥12', '免费', '¥18', '免费', '免费', '免费']
        with patch('autotata.activity_shop.time.monotonic', return_value=10.5):
            self.assertFalse(reader.recognize(self.game, layout, text)); text.assert_not_called()
        with patch('autotata.activity_shop.time.monotonic', return_value=12.1):
            self.assertTrue(reader.recognize(self.game, layout, text))

    def test_shop_stop_precedes_bait_and_rafting_reward_retry(self):
        fish = FishingEngine(FishingSettings(auto_bait=True, shutdown_on_stop=True))
        fish.bait.phase = 'confirming'; fish.pending_rods = 3
        action = fish.step(FishingObservation('purchase', None, None, None, None), 0)
        self.assertEqual(action.kind, 'stop'); self.assertNotEqual(action.purpose, 'auto_stop')
        self.assertEqual((fish.rods_used, fish.bait.used), (0, 0))
        raft = RaftingEngine(RaftingSettings(shutdown_on_stop=True)); raft.after_choice = True
        raft.acknowledge(Action(purpose='choice'), 0)
        action = raft.step(self.vision.observe(self.frame, True, False), 1)
        self.assertEqual(action.kind, 'stop'); self.assertNotEqual(action.purpose, 'auto_stop')
        self.assertIsNone(action.point); self.assertEqual(raft.used, 0)

    def test_fishing_runner_stops_on_real_shop_without_click_or_normal_completion(self):
        from fishing.runner import run
        vision = FishingVision(); vision.ocr = self.vision.ocr
        # First OCR may be stale; the fresh same-page frame must not repeat it.
        self.assertEqual(vision.observe(self.frame).state, 'purchase')
        cancel = threading.Event(); capture = MagicMock(); mouse = MagicMock()
        mouse.size = (self.frame.shape[1], self.frame.shape[0])
        sequence = iter(range(1, 100)); messages = []
        capture.read.side_effect = lambda: (self.frame, time.monotonic(), next(sequence), mouse.size)
        with patch('fishing.runner.WindowCapture', return_value=capture), patch('fishing.runner.Mouse', return_value=mouse), \
             patch('fishing.runner.Vision', return_value=vision), patch('fishing.runner.user32') as user, \
             patch('fishing.runner.cv2.imwrite'):
            user.GetAsyncKeyState.return_value = 0; user.GetForegroundWindow.return_value = 42
            run(42, FishingSettings(mode='foreground', auto_bait=True, shutdown_on_stop=True), cancel, messages.append)
        mouse.click.assert_not_called(); mouse.fallback_click.assert_not_called()
        self.assertIn({'normalStop': False, 'reconnectReady': False}, messages)
