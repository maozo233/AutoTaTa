import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fishing.maatouch_display import prepare_maatouch_display

class DisplayBindingTests(unittest.TestCase):
    def test_virtual_display_uses_visible_coordinates_and_explicit_display(self):
        device=SimpleNamespace(adb_path='adb.exe',address='127.0.0.1:16384',config={'extras':{'mumu':{'enable':True}}})
        with patch('fishing.display_probe.inspect_fishing_displays',return_value=(device.config,(2,900,1600))),patch('fishing.maatouch_display.subprocess.run',return_value=SimpleNamespace(returncode=0)):
            config,target=prepare_maatouch_display(device)
        self.assertEqual(target,(2,900,1600))
        self.assertEqual(config['command']['Orientation'][-1],'echo 0')
        self.assertEqual(config['command']['Resolution'][-1],'echo 900 1600 0')
        command=config['command']['InvokeApp'][-1]
        self.assertTrue(command.endswith('{PACKAGE_NAME} 2'))
        self.assertIn('.dex:/data/local/tmp/{APP_WORKING_FILE}',command)
        self.assertNotIn('command',device.config)

    def test_failed_patch_push_prevents_agent_start(self):
        device=SimpleNamespace(adb_path='adb.exe',address='127.0.0.1:16384',config={})
        with patch('fishing.display_probe.inspect_fishing_displays',return_value=(device.config,(2,900,1600))),patch('fishing.maatouch_display.subprocess.run',return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(RuntimeError,'传输失败'):prepare_maatouch_display(device)
