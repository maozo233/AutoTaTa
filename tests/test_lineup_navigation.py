"""Regression coverage for dimmed badges, joined rows and animated inventory."""
import unittest
from unittest.mock import Mock,patch
import cv2
from lineup.vision import Vision,badge_element
from lineup.recognition import read_image
from tests import test_lineup as helpers
FIXTURES=helpers.FIXTURES


class InventoryGeometryTests(unittest.TestCase):
    def test_joined_card_frames_restore_two_rows_without_inner_duplicates(self):
        obs=Vision().observe(read_image(FIXTURES/'live-joined-inventory.png'))
        self.assertEqual((obs.count,obs.limit,len(obs.cards)),(11,15,10))
        self.assertEqual([c['bounds'][0] for c in obs.cards[:5]],
                         [c['bounds'][0] for c in obs.cards[5:]])
        self.assertTrue(all(c['bounds'][3]>150 for c in obs.cards))
        self.assertEqual([c['element'] for c in obs.cards],
                         ['fire','lightning','water','lightning','grass',
                          'lightning','lightning','grass','grass','fire'])

    def test_dimming_does_not_turn_a_lightning_symbol_into_rock(self):
        image=read_image(FIXTURES/'formation-fifteen.png')
        obs=Vision().observe(image)
        game=cv2.resize(image,(540,round(len(image)/obs.scale)))
        for level in (1.,.65,.45):
            dimmed=(game*level).astype('uint8')
            for card in obs.cards:
                if card['element']!='lightning':continue
                box=tuple(round(v/obs.scale) for v in card['bounds'])
                self.assertEqual(badge_element(dimmed,box),'lightning')


class InventorySettleTests(unittest.TestCase):
    operations=helpers.ObservationGuardTests.operations

    def test_plausible_inventory_pose_is_rechecked_before_leaving_the_page(self):
        ops=self.operations();ops.select_element=Mock();ops.scroll=Mock()
        card={'id':'cavyzap','score':.93,'point':(230,180)}
        ops.page=Mock(side_effect=[[{'id':'?','score':.518}],[card]])
        self.assertIs(ops.find_available('hippiehog'),card)
        self.assertEqual(ops.page.call_count,2);ops.scroll.assert_not_called()

    def test_idle_portrait_animation_does_not_block_a_stationary_page(self):
        ops=self.operations();obs=ops.observation
        obs.cards=[{'bounds':(10,160,60,70)},{'bounds':(200,160,60,70)}]
        ops.guard=Mock(return_value=obs)
        levels=iter((30,200))
        def sample():
            ops.frame[180:215]=next(levels)
            return obs
        ops.snapshot=Mock(side_effect=sample)
        with patch('lineup.runner.drag') as gesture:ops.scroll(1)
        self.assertEqual(ops.snapshot.call_count,2);gesture.assert_called_once()

    def test_single_partial_upper_row_uses_the_complete_lower_row(self):
        ops=self.operations();obs=ops.observation
        obs.cards=[{'bounds':(10,152,60,35)},
                   {'bounds':(10,195,60,45)},{'bounds':(200,195,60,45)}]
        ops.guard=Mock(return_value=obs);ops.snapshot=Mock(return_value=obs)
        with patch('lineup.runner.drag') as gesture:ops.scroll(1)
        self.assertGreater(gesture.call_args.args[1][1],195)


if __name__=='__main__':unittest.main()
