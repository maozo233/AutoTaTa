import unittest
from treasure.solver import solve,estimate,estimate_guided
class TreasureTests(unittest.TestCase):
    def test_site_baseline(self):
        result=solve(5,[(1,3,3)],[0]*25)
        self.assertTrue(result['exact']);self.assertEqual(len(result['masks']),1638)
        self.assertEqual([round(p*100) for p in result['probabilities'][:5]],[24,33,43,33,24])
    def test_constraints_and_rotations(self):
        result=solve(3,[(1,2,1)],[2,0,1,0,0,0,0,0,0])
        self.assertEqual(len(result['masks']),2)
        self.assertEqual(result['probabilities'][0],1)
        self.assertEqual(result['probabilities'][2],0)
    def test_conflict_is_not_unknown(self):
        result=solve(3,[(1,2,1)],[2,1,1,1,1,1,1,1,1])
        self.assertTrue(result['exact']);self.assertFalse(result['masks'])
    def test_sampling_keeps_constraints(self):
        result=solve(3,[(1,2,1)],[2,0,1,0,0,0,0,0,0],node_limit=1)
        self.assertFalse(result['exact']);self.assertTrue(result['masks'])
        self.assertTrue(all(m&1 and not m&4 for m in result['masks']))
    def test_estimate_and_finished_board(self):
        self.assertEqual(estimate([3],[0]*9,10)['cost'],67)
        self.assertEqual(estimate_guided([3],[0]*9,10)['cost'],20)
        self.assertEqual(estimate_guided([3],[2,2]+[0]*7,10)['cost'],0)
