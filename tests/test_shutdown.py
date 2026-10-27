import unittest
from unittest.mock import patch
from fishing.shutdown import request_shutdown

class ShutdownTests(unittest.TestCase):
    def test_no_implicit_forcing_or_os_countdown(self):
        with patch('fishing.shutdown.subprocess.run') as run:
            request_shutdown(False)
            self.assertEqual(run.call_args.args[0][1:], ['/s','/t','0'])
            request_shutdown(True)
            self.assertEqual(run.call_args.args[0][1:], ['/s','/t','0','/f'])
