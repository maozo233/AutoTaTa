"""Replay the 2026-10-16/17 local failures without sending game input."""
import itertools
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
from lineup.vision import Grid, Observation, Vision, occupied_cell, import_formation, checker_reference_grid
from lineup.recognition import read_image
from tests import test_lineup as helpers


class LocalOccupancyTests(unittest.TestCase):
    operations = helpers.ObservationGuardTests.operations

    @classmethod
    def setUpClass(cls):
        cv2.setNumThreads(1)

    def test_neighbor_tail_does_not_add_a_sixteenth_unit(self):
        frame = read_image(helpers.FIXTURES/'live-neighbor-spill.png')
        grid = Grid((203.33333333333334, 373.33333333333337, 488.33333333333337, 488.33333333333337), 5, 5)
        occupied = [i for i in range(25) if occupied_cell(frame, grid, i)]
        self.assertEqual(occupied, [5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21])

    def test_successful_withdrawal_confirms_despite_neighbor_outline(self):
        before = read_image(helpers.FIXTURES/'withdraw-spill-before.png')
        after = read_image(helpers.FIXTURES/'withdraw-spill-after.png')
        grid = Grid((203.33333333333334, 383.33333333333337, 488.33333333333337, 488.33333333333337), 5, 5)
        self.assertTrue(occupied_cell(before, grid, 5))
        self.assertFalse(occupied_cell(after, grid, 5))
        ops = self.operations()
        x,y,right,bottom = grid.tile(5, .12)
        ops.pending = (5, before[y:bottom,x:right].copy())
        ops.pending_kind = 'withdraw'
        ops.pending_identity = 'clawzor'
        ops.board_identities = {5:'clawzor'}
        ops.frame = after
        obs = Observation(state='ready', count=11, limit=15, grid=grid)
        ops.snapshot = Mock(return_value=obs)
        self.assertIs(ops.wait_count(11), obs)
        self.assertEqual(ops.snapshot.call_count, 2)
        self.assertNotIn(5, ops.board_identities)
        ops.mouse.click.assert_not_called()

    def test_matching_count_cannot_confirm_an_occupied_withdrawal_cell(self):
        ops = self.operations()
        grid = ops.observation.grid
        x,y,right,bottom = grid.tile(0, .12)
        ops.pending = (0, np.zeros_like(ops.frame[y:bottom,x:right]))
        ops.pending_kind = 'withdraw'
        ops.snapshot = Mock(return_value=Observation(state='ready', count=0, grid=grid))
        with patch('lineup.runner.occupied_cell', return_value=True), patch('lineup.runner.time.monotonic', side_effect=itertools.count()):
            with self.assertRaisesRegex(RuntimeError, '未确认上阵数量更新'):
                ops.wait_count(0)
        ops.mouse.click.assert_not_called()


class CroppedBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cv2.setNumThreads(1)

    def test_both_failed_imports_locate_all_five_rows(self):
        for name in ('cropped-light-board.png', 'cropped-dark-board.png'):
            with self.subTest(name=name):
                frame = read_image(helpers.FIXTURES/name)
                grid = checker_reference_grid(frame)
                self.assertIsNotNone(grid)
                x,y,w,h = grid.rect
                self.assertGreater(w, frame.shape[1]*.88)
                self.assertLess(y, 15)
                self.assertLess(abs(w-h), 8)
                result = import_formation(frame)
                self.assertEqual(len(result['cells']), 25)
                self.assertEqual(result['cells'][:5], [None]*5)
                self.assertEqual(sum(k is not None for k in result['cells']), 16 if 'dark' in name else 15)
                if 'dark' in name:
                    self.assertEqual(result['cells'][6], 'clawzor')
                    self.assertEqual(result['cells'][7], None)
                    self.assertIsNotNone(result['cells'][14])
                    # The badge above waveflutter crosses into this otherwise
                    # empty tile; the old 17-cell expectation included it.
                    self.assertIsNone(result['cells'][16])
                    self.assertIn('?', result['cells'])

    def test_plain_or_random_panels_do_not_supply_a_checker_grid(self):
        for frame in (np.full((218,211,3), 90, np.uint8), np.random.default_rng(42).integers(0,256,(218,211,3),dtype=np.uint8)):
            self.assertIsNone(checker_reference_grid(frame))


if __name__ == '__main__':
    unittest.main()
