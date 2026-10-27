"""Unknown identities are withdrawn once, then the live plan is rebuilt."""
import threading,unittest
from unittest.mock import Mock,patch
from lineup.engine import execute,execute_stream,FormationStream,UnrecognizedBoardUnits
from tests import test_lineup as helpers
from tests.test_lineup_batch import BatchFake


class UnknownRecoveryTests(unittest.TestCase):
    def test_move_recheck_failure_withdraws_source_and_reacquires_inventory(self):
        ops=helpers.FakeOperations({4:'dozy'},[])
        ops.move=Mock(side_effect=UnrecognizedBoardUnits([4],1))
        result=execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertEqual(ops.units,{0:'dozy'});self.assertEqual(result['issues'],[])
        self.assertEqual(ops.calls,[('withdraw',4),('find','dozy'),('drag','dozy',0)])
        ops.move.assert_called_once()

    def test_recovery_discards_a_stale_supplied_board(self):
        ops=helpers.FakeOperations({0:'rockwu',4:'dozy'},[])
        plan=execute(ops,['dozy']+[None]*24,5,lambda e:None,
                     known_board=[{'index':0,'id':'?'},{'index':4,'id':'dozy'}])
        self.assertEqual(ops.units,{0:'dozy'});self.assertEqual(plan['issues'],[])

    def test_replanning_keeps_moves_that_already_completed(self):
        ops=helpers.FakeOperations({4:'dozy',5:'serrabloom'},[]);move=ops.move
        def recheck(source,target,count):
            if source==5:raise UnrecognizedBoardUnits([5],count)
            return move(source,target,count)
        ops.move=recheck
        plan=execute(ops,['dozy','manteeny']+[None]*23,5,lambda e:None)
        self.assertEqual(ops.units,{0:'dozy',1:'serrabloom'})
        self.assertEqual(ops.calls[:2],[('move',4,0),('withdraw',5)])
        self.assertEqual(len(plan['placements']),2)

    def test_multiple_unknowns_update_the_count_after_each_withdrawal(self):
        ops=helpers.FakeOperations({0:'?',1:'?',4:'dozy'},[])
        plan=execute(ops,['dozy']+[None]*24,5,lambda e:None)
        self.assertEqual(ops.calls,[('withdraw',0),('withdraw',1),('move',4,0)])
        self.assertEqual(plan['issues'],[])

    def test_failed_withdraw_is_not_clicked_again_or_followed_by_a_deploy(self):
        ops=helpers.FakeOperations({0:'?'},[{'id':'dozy'}])
        ops.withdraw_unrecognized=Mock()
        with self.assertRaises(AssertionError):execute(ops,['dozy']+[None]*24,5,lambda e:None)
        ops.withdraw_unrecognized.assert_called_once_with(0,1)
        self.assertEqual(ops.calls,[])

    def test_stream_can_remove_an_unknown_and_finish_the_same_formation(self):
        stream=FormationStream(25);stream.finish({'cells':['dozy']+[None]*24})
        ops=BatchFake({0:'?'},[{'id':'dozy'}])
        result=execute_stream(ops,stream,5,lambda e:None,threading.Event())
        self.assertEqual(ops.units,{0:'dozy'});self.assertEqual(result['issues'],[])
        self.assertEqual(ops.calls[0],('withdraw',0))

    def test_failed_import_never_triggers_unknown_cleanup(self):
        stream=FormationStream(25);stream.fail('识别失败')
        ops=BatchFake({0:'?'},[])
        with self.assertRaisesRegex(RuntimeError,'识别失败'):
            execute_stream(ops,stream,5,lambda e:None,threading.Event())
        self.assertEqual(ops.calls,[])

    def test_import_failure_during_move_recheck_prevents_cleanup(self):
        stream=FormationStream(25);stream.put(0,{'id':'dozy'})
        ops=BatchFake({4:'dozy'},[])
        def failed(*args):
            stream.fail('识别失败')
            raise UnrecognizedBoardUnits([4],1)
        ops.move=failed
        with self.assertRaisesRegex(RuntimeError,'识别失败'):
            execute_stream(ops,stream,5,lambda e:None,threading.Event())
        self.assertEqual(ops.calls,[])


class UnknownClickTests(unittest.TestCase):
    operations=helpers.ObservationGuardTests.operations

    def test_two_occupied_frames_allow_one_click_without_identity(self):
        ops=self.operations();obs=ops.observation;obs.count=1
        ops.board_identities={0:'?'};ops.guard=Mock(return_value=obs)
        with patch('lineup.runner.occupied_cell',return_value=True):ops.withdraw_unrecognized(0,1)
        self.assertEqual(ops.guard.call_count,2)
        ops.mouse.click.assert_called_once_with(tuple(map(round,obs.grid.center(0))))
        ops.vision.unit.assert_not_called();self.assertEqual(ops.pending_kind,'withdraw')

    def test_disappearing_occupant_prevents_the_click(self):
        ops=self.operations();ops.observation.count=1;ops.guard=Mock(return_value=ops.observation)
        with patch('lineup.runner.occupied_cell',side_effect=[True,False]):
            with self.assertRaisesRegex(RuntimeError,'位置已变化'):ops.withdraw_unrecognized(0,1)
        ops.mouse.click.assert_not_called()

    def test_changed_count_prevents_the_click(self):
        ops=self.operations();ops.guard=Mock(return_value=ops.observation)
        with self.assertRaisesRegex(RuntimeError,'数量已变化'):ops.withdraw_unrecognized(0,1)
        ops.mouse.click.assert_not_called()


if __name__=='__main__':unittest.main()
