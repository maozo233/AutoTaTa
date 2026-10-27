"""Small animated reference bodies and transient identity rechecks."""
import unittest
from unittest.mock import Mock,patch
import cv2
from tests import test_lineup as helpers
from lineup.vision import Vision,Observation,import_formation,read_image
from lineup.recognition import identify


class AnimatedBodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1)
    def test_supplied_small_pose_is_identified_without_losing_four_other_units(self):
        image=read_image(helpers.FIXTURES/'three-four-overlap-reference.png');result=import_formation(image,3)
        self.assertEqual(result['cells'],[None,None,'rockzilla','rockong',None,None,'rockshell',None,None,'clangnaga','bastogard',None])
        self.assertEqual(Vision().unit(image,Observation(grid=result['grid']),3)['id'],'rockong')
    def test_pose_recovery_retains_center_and_requested_identity_constraints(self):
        image=read_image(helpers.FIXTURES/'three-four-overlap-reference.png');grid=import_formation(image,3)['grid']
        x,y,right,bottom=grid.tile(3,-.30);crop=image[max(0,y):bottom,max(0,x):right]
        self.assertEqual(identify(crop,allowed_ids={'rockong'},animated=True,background=180)['id'],'rockong')
        self.assertEqual(identify(crop,allowed_ids={'dozy'},animated=True,background=180)['id'],'?')
        self.assertEqual(identify(crop,animated=True,background=180,center_region=(0,0,10,10))['id'],'?')
    def test_supplied_fifteen_limit_frame_rechecks_taptail_on_neutral_surface(self):
        image=read_image(helpers.FIXTURES/'live-identity-recheck.png');vision=Vision();obs=vision.observe(image)
        self.assertEqual((obs.count,obs.limit),(14,15))
        self.assertEqual(vision.unit(image,obs,24,'taptail')['id'],'taptail')


class IdentityRecheckTests(unittest.TestCase):
    operations=helpers.ObservationGuardTests.operations
    def setup_guard(self,results):
        ops=self.operations();ops.board_identities={0:'dozy'}
        ops.observation.count=1;ops.guard=Mock(return_value=ops.observation)
        ops.vision.unit=Mock(side_effect=[{'id':r,'score':.9 if r!='?' else .4} for r in results])
        return ops
    def test_unknown_animation_recovers_only_after_two_fresh_positive_checks(self):
        ops=self.setup_guard(['?','dozy','dozy'])
        with patch('lineup.runner.occupied_cell',return_value=True):self.assertIs(ops.board_guard([0],1),ops.observation)
        self.assertEqual(ops.guard.call_count,3);ops.mouse.click.assert_not_called()
    def test_recovery_confirmation_resets_on_another_unknown_pose(self):
        ops=self.setup_guard(['?','dozy','?','dozy','dozy'])
        with patch('lineup.runner.occupied_cell',return_value=True):ops.board_guard([0],1)
        self.assertEqual(ops.guard.call_count,5)
    def test_unknown_stays_bounded_and_never_sends_input(self):
        ops=self.setup_guard(['?']*5)
        with patch('lineup.runner.occupied_cell',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'多帧仍未确认'):ops.board_guard([0],1)
        self.assertEqual(ops.guard.call_count,5);ops.mouse.click.assert_not_called()
    def test_known_conflicting_identity_stops_without_retry(self):
        ops=self.setup_guard(['rockwu'])
        with patch('lineup.runner.occupied_cell',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'身份已变化'):ops.board_guard([0],1)
        self.assertEqual(ops.guard.call_count,1)
    def test_quantity_change_during_recheck_stops_before_input(self):
        ops=self.setup_guard(['?','dozy','dozy']);changed=helpers.Observation(state='ready',count=2)
        ops.guard.side_effect=[ops.observation,changed]
        with patch('lineup.runner.occupied_cell',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'数量已变化'):ops.board_guard([0],1)
        self.assertEqual(ops.vision.unit.call_count,1);ops.mouse.click.assert_not_called()


if __name__=='__main__':unittest.main()
