"""Real failures from the October 19 remote bundle and this machine."""
import unittest
import cv2
import numpy as np
from lineup.vision import import_formation, card_lattice_grid
from lineup.recognition import read_image
from tests.test_lineup import FIXTURES


CARD_CASES={
    'cards-local-evolved.png':{1:'rockzilla',2:'rockshell',3:'rockong',4:'dozy',6:'cheerspring',7:'rattlecoil',8:'charflutter',9:'sonarbat',10:'orchitoria',11:'waveflutter',12:'humbleetle',13:'trippet',14:'solaflora',17:'rockhog',22:'tideon'},
    'cards-local-varied.png':{1:'rockong',2:'turtuff',3:'rubblet',4:'ringtail',6:'cheerspring',7:'rattlecoil',8:'charflutter',9:'synthhog',10:'orchitoria',11:'waveflutter',12:'humbleetle',13:'hyphoria',14:'solaflora',17:'rockhog',22:'tideon'},
    'cards-remote-full.png':{0:'rockshell',1:'rockzilla',2:'gemsnail',3:'zappur',4:'orchitoria',6:'cheerspring',7:'humbleetle',8:'hyphoria',10:'sonarbat',11:'rockwu',12:'bubbit',13:'rizzler',14:'silversear',17:'rockhog',22:'clangnaga'},
    'cards-remote-crop.png':{1:'rockzilla',2:'rockshell',3:'rockong',4:'dozy',6:'cheerspring',7:'rattlecoil',8:'charflutter',9:'sonarbat',10:'orchitoria',11:'waveflutter',12:'humbleetle',13:'trippet',14:'solaflora',17:'rockhog',22:'tideon'},
}


class DiagnosticReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1)

    def assert_cards(self,frame,expected):
        result=import_formation(frame)
        self.assertEqual({i:k for i,k in enumerate(result['cells']) if k is not None},expected)
        self.assertTrue(all(d['score']>=.80 for d in result['details']))
        return result

    def test_four_failing_card_sources_keep_all_identities_and_empty_cells(self):
        for name,expected in CARD_CASES.items():
            with self.subTest(name=name):self.assert_cards(read_image(FIXTURES/name),expected)

    def test_evolution_decorations_survive_compression_and_scaling(self):
        frame=read_image(FIXTURES/'cards-local-evolved.png')
        jpeg=cv2.imdecode(cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,85])[1],cv2.IMREAD_COLOR)
        for image in (jpeg,cv2.resize(frame,None,fx=1.25,fy=1.25)):
            self.assert_cards(image,CARD_CASES['cards-local-evolved.png'])

    def test_large_card_capture_keeps_original_portrait_resolution_and_coordinates(self):
        frame=read_image(FIXTURES/'cards-local-evolved.png')
        image=cv2.copyMakeBorder(frame,450,450,700,700,cv2.BORDER_CONSTANT,value=(235,235,235))
        result=self.assert_cards(image,CARD_CASES['cards-local-evolved.png'])
        x,y,w,h=result['grid'].rect
        self.assertTrue(712<x<725 and 458<y<475)
        self.assertGreater(w,400);self.assertGreater(h,500)

    def test_scenery_is_not_stretched_into_the_bottom_row(self):
        result=import_formation(read_image(FIXTURES/'reference-bottom-scenery.png'))
        self.assertEqual([i for i,k in enumerate(result['cells']) if k is not None],list(range(6,20))+[23])
        self.assertEqual(result['cells'][7],'?')
        self.assertEqual(result['cells'][23],'droppit')
        self.assertLess(result['grid'].rect[3]/result['grid'].rect[2],1.03)

    def test_yellow_remote_board_already_supported_remains_fully_identified(self):
        result=import_formation(read_image(FIXTURES/'reference-yellow-remote.png'))
        self.assertEqual(sum(k is not None for k in result['cells']),15)
        self.assertNotIn('?',result['cells'])

    def test_plain_panels_and_two_inventory_rows_cannot_supply_five_rows(self):
        self.assertIsNone(card_lattice_grid(np.full((595,458,3),90,np.uint8)))
        frame=read_image(FIXTURES/'cards-local-evolved.png')
        self.assertIsNone(card_lattice_grid(frame[:220]))


if __name__=='__main__':unittest.main()
