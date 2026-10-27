import unittest
import cv2
from fishing.paths import ASSETS
from fishing.vision import Vision, inside_yellow

class VisionTests(unittest.TestCase):
    def test_gold_ready_real_and_upgrade_hint(self):
        v=Vision();g=v.normalize(cv2.imread(str(ASSETS/'fixtures/gold-ready-real.png')))
        self.assertEqual(v.read_rod_level(g),3);self.assertFalse(v.read_rod_upgrade_hint(g))
        v=Vision();g=v.normalize(cv2.imread(str(ASSETS/'fixtures/rod-upgrade-hint.png')))
        self.assertTrue(v.read_rod_upgrade_hint(g));self.assertIsNone(v.read_multiplier(g))

    def test_luck_real_crops_at_multiple_scales(self):
        for number in (1, 2, 4, 6):
            crop = cv2.imread(str(ASSETS/'fixtures/luck'/f'real-{number}.png'))
            for scale in (.75, 1., 1.5, 2.):
                with self.subTest(number=number, scale=scale):
                    self.assertEqual(self.v.read_luck_crop(cv2.resize(crop,None,fx=scale,fy=scale)),number)

    def test_luck_rejects_blank_and_ambiguous_glyphs(self):
        import numpy as np
        for color in ((0,0,0),(255,255,255),(0,255,255),(0,255,0)):
            self.assertIsNone(self.v.read_luck_crop(np.full((56,64,3),color,np.uint8)))
        image = np.zeros((56,64,3),np.uint8)
        cv2.rectangle(image,(20,18),(25,40),(0,220,255),-1)
        cv2.rectangle(image,(35,18),(40,40),(0,220,255),-1)
        self.assertIsNone(self.v.read_luck_crop(image))


    def test_rod_levels_real_and_explicitly_synthetic_red(self):
        for name,expected in [('ready100',1),('multiplier-max',2),('bait-stars',3),('synthetic-red-ready',4)]:
            v=Vision();frame=cv2.imread(str(ASSETS/'fixtures'/f'{name}.png'))
            v.observe(frame);self.assertEqual(v.read_rod_level(v.normalize(frame)),expected,name)

    def test_real_luck_inventory_and_cap_toast(self):
        for name,luck,stock,cap in [('ready100',1,1,False),('multiplier-max',2,0,False),('bait-menu',4,1,False),('bait-cap',6,2,True),('bait-stars',5,4,False)]:
            v=Vision();frame=cv2.imread(str(ASSETS/'fixtures'/f'{name}.png'));o=v.observe(frame);g=v.normalize(frame)
            self.assertEqual(v.read_luck(g),luck,name)
            self.assertEqual(v.read_bait_stock(g,o.bait_available),stock,name)
            self.assertEqual(v.read_bait_cap(g),cap,name)

    def test_real_flight_and_star_effects_block_reading(self):
        for name in ('bait-flight','bait-stars'):
            v=Vision();g=v.normalize(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png')))
            self.assertTrue(v.bait_animation(g),name)
        for name in ('ready100','multiplier-max','bait-menu','bait-cap'):
            v=Vision();g=v.normalize(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png')))
            self.assertFalse(v.bait_animation(g),name)

    def test_real_maximum_toast_and_negative_screens(self):
        frame=cv2.imread(str(ASSETS/'fixtures/multiplier-max.png'))
        sample=Vision().observe(frame,read_multiplier=True)
        self.assertEqual(sample.state,'ready');self.assertEqual(sample.multiplier,20)
        self.assertTrue(sample.multiplier_max)
        for name in ('ready','ready100','bait-menu','fight-inside','result'):
            self.assertFalse(self.v.observe(cv2.imread(str(ASSETS/'fixtures'/f'{name}.png'))).multiplier_max,name)

    def test_early_entry_from_either_side_including_narrow_zone(self):
        for zone in ((100,180),(100,110)):
            with self.subTest(zone=zone):
                self.assertTrue(inside_yellow(zone[0]+1,zone))
                self.assertTrue(inside_yellow(zone[1]-1,zone))
                self.assertFalse(inside_yellow(zone[0]-.1,zone))
                self.assertFalse(inside_yellow(zone[1]+.1,zone))

    def test_live_pale_sky_does_not_crop_away_title(self):
        vision=Vision()
        sample=vision.observe(cv2.imread(str(ASSETS/'fixtures/live-ready.png')),True)
        self.assertEqual(sample.state,'ready')
        self.assertEqual(sample.multiplier,1)
        self.assertAlmostEqual(vision.rect[1],40,delta=2)

    def test_all_multiplier_values_from_real_switch_video(self):
        v = Vision()
        for value in (1,2,3,5,10,20,50,100):
            with self.subTest(value=value):
                frame = cv2.imread(str(ASSETS/'fixtures'/f'multiplier-{value}.png'))
                sample = v.observe(frame, read_multiplier=True)
                self.assertEqual(sample.state, 'ready')
                self.assertEqual(sample.multiplier, value)

    def setUp(self):
        self.v = Vision()
        self.v.observe(cv2.imread(str(ASSETS/'fixtures/ready.png')))

    def test_float_splits_yellow_zone(self):
        obs = self.v.observe(cv2.imread(str(ASSETS/'fixtures/fight-inside.png')))
        self.assertEqual(obs.state, 'fight')
        self.assertTrue(obs.in_yellow)
        self.assertIsNotNone(obs.track_bounds)
        self.assertLess(obs.track_bounds[0],obs.yellow[0])
        self.assertGreater(obs.track_bounds[1],obs.yellow[1])
        self.assertTrue(obs.yellow[0] < obs.float_x < obs.yellow[1])

    def test_float_outside_zone(self):
        obs = self.v.observe(cv2.imread(str(ASSETS/'fixtures/fight-outside.png')))
        self.assertEqual(obs.state, 'fight')
        self.assertFalse(obs.in_yellow)

    def test_result_accept_button_is_clicked(self):
        obs = self.v.observe(cv2.imread(str(ASSETS/'fixtures/result.png')))
        self.assertEqual(obs.state, 'result')
        self.assertGreater(obs.dismiss_point[0], 200)
        self.assertLess(obs.dismiss_point[0], 340)
        self.assertGreater(obs.dismiss_point[1], 840)

    def test_clover_multiplier_not_used_as_timer(self):
        obs = self.v.observe(cv2.imread(str(ASSETS/'fixtures/ready.png')), read_timer=True)
        self.assertEqual(obs.timer, 'absent')

    def test_real_bait_menu_and_timer(self):
        v = Vision()
        obs = v.observe(cv2.imread(str(ASSETS/'fixtures/bait-menu.png')), True, True)
        self.assertEqual(obs.state, 'bait_menu')
        self.assertEqual(obs.multiplier, 10)
        self.assertEqual(obs.timer, 'active')
        self.assertAlmostEqual(obs.bait_confirm_point[0], 425, delta=4)
        self.assertAlmostEqual(obs.bait_confirm_point[1], 600, delta=4)

if __name__ == '__main__':
    unittest.main()
