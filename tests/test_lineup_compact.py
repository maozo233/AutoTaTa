"""Small compressed checkerboards retain occupied cells and identity limits."""
import unittest
from pathlib import Path
import cv2,numpy as np
from lineup.vision import checker_reference_grid,import_formation
from lineup.recognition import read_image

FIXTURES=Path(__file__).parent/'fixtures/lineup'
EXPECTED=[None]*5+['sizribb','serrabloom','cobbledon','boldclaw',None,None,
          'cheerlet','rockhog','firecoil','electroar','azurion','boltskipper',
          'cluckeroo','ripplewing','sparkdoe',None,'frostique','frugagon',None,None]


class CompactReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1)

    def test_current_small_original_preserves_all_fifteen_and_empty_cells(self):
        result=import_formation(read_image(FIXTURES/'formation-small-checker.png'))
        self.assertEqual(result['cells'],EXPECTED)

    def test_compressed_board_is_not_rejected_or_pale_units_marked_empty(self):
        im=cv2.resize(read_image(FIXTURES/'formation-small-checker.png'),(263,219))
        result=import_formation(im)
        self.assertLess(max(abs(a-b) for a,b in zip(result['grid'].rect,(6.6,0,252,216))),4)
        self.assertEqual(sum(k is not None for k in result['cells']),15)
        for i,wanted in enumerate(EXPECTED):
            self.assertIn(result['cells'][i],(wanted,'?') if wanted else (None,))
            if i!=11:self.assertEqual(result['cells'][i],wanted)

    def test_short_flat_or_gradient_panel_is_not_a_checkerboard(self):
        for gray in (np.full((219,263),170,np.uint8),
                     np.tile(np.linspace(90,210,263,dtype=np.uint8),(219,1))):
            self.assertIsNone(checker_reference_grid(cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)))


if __name__=='__main__':unittest.main()
