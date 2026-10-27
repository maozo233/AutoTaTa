"""October 24 multi-machine failures, replayed without device input."""
import threading
import unittest
from unittest.mock import Mock
import cv2

from lineup.engine import execute, execute_stream, FormationStream
from lineup.recognition import read_image
from lineup.vision import import_formation, incomplete_reference
from tests.test_lineup import FIXTURES, FakeOperations


class SavedReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1)

    def test_neighbor_badge_does_not_add_a_sixteenth_unit(self):
        for name,empty in [('oct24-dark-tail.png',2),('oct24-dark-empty.png',7)]:
            with self.subTest(name=name):
                result=import_formation(read_image(FIXTURES/name))
                self.assertEqual(sum(k is not None for k in result['cells']),15)
                self.assertIsNone(result['cells'][empty])
                self.assertNotIn('?',result['cells'])

    def test_pale_yellow_sprite_is_not_an_empty_cell_or_scenery_a_unit(self):
        result=import_formation(read_image(FIXTURES/'oct24-yellow-pale.png'))
        self.assertEqual(result['cells'][6],'stalkerix')
        self.assertIsNone(result['cells'][16])
        self.assertEqual(sum(k is not None for k in result['cells']),15)
        self.assertEqual(result['cells'][19],'?')

    def test_dark_background_retry_recovers_pale_bodies_without_forcing_all_identities(self):
        result=import_formation(read_image(FIXTURES/'oct24-dark-pale.png'))
        self.assertEqual(result['cells'][7],'pearpair')
        self.assertEqual(result['cells'][12],'cheerlet')
        self.assertEqual(result['cells'][8],'?')
        self.assertEqual(sum(k is not None for k in result['cells']),15)

    def test_incomplete_three_or_four_rows_never_publish_stretched_five_rows(self):
        for name in ('oct24-cropped-four-yellow.png','oct24-cropped-four-green.png',
                     'oct24-cropped-four-badges.png','oct24-cropped-three-green.png'):
            frame=read_image(FIXTURES/name)
            for manual in (None,(0,0,frame.shape[1],frame.shape[0])):
                with self.subTest(name=name,manual=manual):
                    updates=[]
                    with self.assertRaisesRegex(ValueError,'完整五行'):
                        import_formation(frame,manual_rect=manual,cell_ready=lambda *args:updates.append(args))
                    self.assertEqual(updates,[])

    def test_complete_and_compressed_five_rows_are_not_missing_rows(self):
        for name in ('oct24-yellow-pale.png','oct24-green-portraits.png','formation-small-checker.png'):
            image=read_image(FIXTURES/name)
            self.assertFalse(incomplete_reference(image))
            self.assertFalse(incomplete_reference(cv2.resize(image,None,fx=1.1,fy=.90)))

    def test_yellow_animation_and_rocks_cannot_add_a_sixteenth_unit(self):
        result=import_formation(read_image(FIXTURES/'oct24-yellow-animation.png'))
        self.assertIsNone(result['cells'][16])
        self.assertEqual(sum(k is not None for k in result['cells']),15)

    def test_offset_manual_crop_still_cannot_stretch_missing_rows(self):
        image=read_image(FIXTURES/'oct24-cropped-three-green.png')
        padded=cv2.copyMakeBorder(image,100,100,150,150,cv2.BORDER_CONSTANT,value=(230,230,230))
        with self.assertRaisesRegex(ValueError,'完整五行'):
            import_formation(padded,manual_rect=(150,100,image.shape[1],image.shape[0]))


class BoardObservationTests(unittest.TestCase):
    def changed_board(self):
        ops=FakeOperations({0:'dozy'},[])
        original=ops.board
        def scan():
            ops.units[1]='rockwu'
            return original()
        ops.board=scan
        return ops

    def test_completed_import_uses_the_count_of_the_verified_board_scan(self):
        ops=self.changed_board()
        plan=execute(ops,['dozy','rockwu']+[None]*23,5,lambda value:None)
        self.assertEqual(len(plan['placements']),2)
        self.assertEqual(ops.calls,[])

    def test_streaming_import_also_uses_the_latest_verified_count(self):
        ops=self.changed_board();stream=FormationStream(25)
        stream.finish({'cells':['dozy','rockwu']+[None]*23})
        plan=execute_stream(ops,stream,5,lambda value:None,threading.Event())
        self.assertEqual(len(plan['placements']),2)
        self.assertEqual(ops.calls,[])

    def test_count_disagreement_still_stops_before_any_input(self):
        ops=FakeOperations({0:'dozy'},[]);ops.board=Mock(return_value=[])
        with self.assertRaisesRegex(RuntimeError,'数量不一致'):
            execute(ops,['dozy']+[None]*24,5,lambda value:None)
        self.assertEqual(ops.calls,[])

    def test_mode_change_during_scan_still_stops_before_input(self):
        ops=FakeOperations({0:'dozy'},[]);original=ops.board
        def scan():
            ops.limit=5
            return original()
        ops.board=scan
        with self.assertRaisesRegex(RuntimeError,'场地已变化'):
            execute(ops,['dozy']+[None]*24,5,lambda value:None)
        self.assertEqual(ops.calls,[])


if __name__=='__main__':unittest.main()
