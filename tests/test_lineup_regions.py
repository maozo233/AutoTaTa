"""Locate the player's five rows inside larger saved screenshots."""
import threading
import unittest
import cv2
import numpy as np
from lineup.recognition import read_image
from lineup.vision import local_checker_grid, import_formation
from tests.test_lineup import FIXTURES


class ReferenceRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cv2.setNumThreads(1)
        cls.frame=read_image(FIXTURES/'reference-extra-top.png')

    def test_saved_failure_excludes_extra_checker_rows_and_finds_fifteen_units(self):
        result=import_formation(self.frame)
        x,y,w,h=result['grid'].rect
        self.assertTrue(19<=x<=26 and 74<=y<=83)
        self.assertLess(abs(w-h),4)
        self.assertEqual([i for i,k in enumerate(result['cells']) if k is not None],list(range(6,20))+[23])
        self.assertEqual(result['cells'][15:20],['clucky','ignisnap','voltfawn','waveflutter','frostnip'])
        self.assertEqual(result['cells'][23],'droppit')
        self.assertEqual(result['cells'][7],'?')

    def test_added_margins_and_offset_do_not_define_the_board(self):
        for top,bottom,left,right,color in ((110,90,250,340,(240,238,236)),(610,671,800,1038,(240,238,236)),(35,300,160,90,(0,0,0))):
            with self.subTest(margins=(top,bottom,left,right)):
                image=cv2.copyMakeBorder(self.frame,top,bottom,left,right,cv2.BORDER_CONSTANT,value=color)
                grid=local_checker_grid(image)
                self.assertIsNotNone(grid)
                x,y,w,h=grid.rect
                self.assertLess(abs(x-left-23),4)
                self.assertLess(abs(y-top-78),4)
                self.assertLess(abs(w-221),4)
                self.assertLess(abs(h-221),4)

    def test_large_desktop_capture_preserves_small_portraits_and_source_coordinates(self):
        image=cv2.copyMakeBorder(self.frame,610,671,800,1038,cv2.BORDER_CONSTANT,value=(240,238,236))
        updates=[]
        result=import_formation(image,cell_ready=lambda i,r,g:updates.append(g.rect))
        self.assertEqual(sum(k is not None for k in result['cells']),15)
        self.assertEqual(result['cells'][15:20],['clucky','ignisnap','voltfawn','waveflutter','frostnip'])
        x,y,_,_=result['grid'].rect
        self.assertTrue(819<=x<=826 and 684<=y<=693)
        self.assertEqual(len(updates),25)
        self.assertEqual(updates[-1],result['grid'].rect)

    def test_full_game_capture_excludes_enemies_controls_and_inventory(self):
        result=import_formation(read_image(FIXTURES/'live-deployed.png'))
        self.assertEqual({i:k for i,k in enumerate(result['cells']) if k is not None},
                         {6:'firecoil',8:'cheerlet',10:'manteeny',11:'ripplewing',14:'rockfu',22:'droppit'})

    def test_separate_boards_are_ambiguous_and_do_not_publish_cells(self):
        image=cv2.hconcat([self.frame,self.frame])
        self.assertIsNone(local_checker_grid(image))
        updates=[]
        with self.assertRaisesRegex(ValueError,'框选阵型区域'):
            import_formation(image,cell_ready=lambda *args:updates.append(args))
        self.assertEqual(updates,[])

    def test_uniform_gradient_and_cancelled_captures_are_rejected(self):
        gradient=np.tile(np.linspace(70,140,480,dtype=np.uint8),(640,1))
        for gray in (np.full((640,480),90,np.uint8),gradient):
            self.assertIsNone(local_checker_grid(cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)))
        cancel=threading.Event();cancel.set()
        with self.assertRaisesRegex(RuntimeError,'已停止识别'):
            local_checker_grid(self.frame,cancel)


if __name__=='__main__':unittest.main()
