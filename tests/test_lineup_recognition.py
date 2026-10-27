"""Real portrait tolerances and bounded, immediate inventory search."""
import threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import cv2
from lineup.runner import Operations
from lineup.vision import Vision,Observation,import_formation,grayscale_grid
from lineup.recognition import identify,read_image,PortraitCache,query_features,reference_features,template_pyramid
from autotata.paths import ASSETS

FIXTURES=Path(__file__).parent/'fixtures/lineup'


class RecognitionSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1)

    def operations(self):
        frame=read_image(FIXTURES/'formation-fifteen.png');obs=Vision().observe(frame)
        ops=Operations(Mock(),Mock(),Mock(),threading.Event(),Mock())
        ops.frame=frame;ops.snapshot=Mock(return_value=obs);ops.check=Mock()
        return ops,obs

    def test_same_family_visible_stage_returns_without_reading_remaining_cards(self):
        ops,obs=self.operations();ops.select_element=Mock();ops.rewind=Mock()
        with patch('lineup.recognition.identify',wraps=identify) as recognizer:
            card=ops.find_available('serrabloom')
        self.assertEqual(card['id'],'manteeny')
        self.assertEqual(card['point'],obs.cards[0]['point'])
        self.assertEqual(recognizer.call_count,1)
        self.assertIn('manteeny',ops.portraits.templates)
        ops.rewind.assert_not_called()

    def test_unknown_earlier_cards_do_not_block_later_target_or_reuse_old_position(self):
        ops,obs=self.operations()
        cards=ops.page(accelerated=True,allowed_ids={'firecoil','flarevix','firefox'},first_match=True)
        self.assertEqual([c['id'] for c in cards],['?','?','firecoil'])
        self.assertEqual(cards[-1]['point'],obs.cards[2]['point'])
        self.assertEqual(cards[-1]['patch'].shape[:2],tuple(map(round,obs.cards[2]['bounds'][2:]))[::-1])

    def test_filter_keeps_seven_matching_badges_when_three_are_shaded(self):
        ops,obs=self.operations()
        obs.filters={'lightning':(200,240),'all':(30,240)}
        obs.cards=[{'element':'rock'} for _ in range(3)]+[{'element':'lightning'} for _ in range(7)]
        ops.guard=Mock(return_value=obs)
        self.assertTrue(ops.select_element('lightning'))
        self.assertTrue(ops.select_element('lightning'))
        ops.mouse.click.assert_called_once_with((200,240))

    def test_portrait_cache_compares_only_current_requested_identities(self):
        cache=PortraitCache();image=read_image(ASSETS/'lineup/tatari/serrabloom.png')
        cache.add('serrabloom',image);cache.add('other',image)
        self.assertIsNone(cache.match(image))
        self.assertEqual(cache.match(image,{'serrabloom'})['id'],'serrabloom')
        self.assertIsNone(cache.match(image,{'dozy'}))

    def test_shared_query_descriptors_do_not_leak_identity_between_target_families(self):
        image=read_image(ASSETS/'lineup/tatari/serrabloom.png')
        query_features.cache_clear()
        self.assertEqual(identify(image,allowed_ids={'serrabloom'})['id'],'serrabloom')
        self.assertEqual(identify(image,allowed_ids={'dozy'})['id'],'?')
        self.assertEqual(query_features.cache_info().misses,1)
        self.assertEqual(query_features.cache_info().hits,1)

    def test_neutral_retry_and_template_scales_do_not_reload_the_catalog(self):
        reference_features(None);reference_features(180)
        template_pyramid.cache_clear()
        with patch('lineup.recognition.read_image',wraps=read_image) as loader:
            template_pyramid('manteeny',80,60)
            reference_features(None);reference_features(180)
        loader.assert_not_called()

    def test_animated_gibber_body_is_recognized_without_accepting_neighbor(self):
        image=read_image(FIXTURES/'live-stacked-controls.png');v=Vision();obs=v.observe(image)
        self.assertEqual(v.unit(image,obs,9)['id'],'gibber')
        self.assertEqual(v.unit(image,obs,14)['id'],'?')

    def test_light_rounded_portraits_identify_cobbledon_and_capypapa_with_all_positions(self):
        image=read_image(FIXTURES/'formation-light-portraits.png')
        expected=[None]*10+['blitzmane','cobbledon','zapooch','serrabloom','capypapa',
                  'rockshell','rattlecoil','cheerlet','solaflora','frostique',
                  'sparkdoe','aquariel','waveflutter','azurion','bubbit']
        compressed=cv2.imdecode(cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,85])[1],cv2.IMREAD_COLOR)
        for label,frame in [('original',image),('jpeg',compressed),('scaled',cv2.resize(image,None,fx=1.35,fy=1.35))]:
            with self.subTest(label=label):
                result=import_formation(frame)
                self.assertEqual(result['cells'],expected)
                for index in (11,14):
                    self.assertGreaterEqual(result['details'][index]['score'],.90 if label=='original' else .82)

    def test_neutral_portrait_retry_does_not_accept_role_badge_or_adjacent_empty_cell(self):
        image=read_image(FIXTURES/'formation-light-portraits.png');grid=grayscale_grid(image)
        x,y,right,bottom=grid.tile(11,0)
        badge=image[y:y+23,right-24:right,:3]
        self.assertEqual(identify(badge,animated=True,background=180)['id'],'?')
        self.assertEqual(identify(image[y:bottom,x:right,:3],animated=True,background=180,center_region=(0,0,10,10))['id'],'?')
        self.assertEqual(import_formation(image)['cells'][:10],[None]*10)


if __name__=='__main__':unittest.main()
