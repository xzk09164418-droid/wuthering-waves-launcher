import sys
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ww import start_game as ww


class Clock:
    def __init__(self):
        self.now = 0

    def sleep(self, seconds):
        self.now += seconds

class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(ww.DEFAULTS)
        self.win = SimpleNamespace(_hWnd=123, left=100, top=200, width=1040, height=840)
        self.shot = Mock(width=1000, height=800)

    def test_uia_scoped_enabled_button_keeps_screen_coordinates(self):
        with patch.object(ww.uia, "find_by_text", return_value=(800, 800, 1000, 900)) as find:
            self.assertEqual(ww.start_point(self.win, self.shot, self.cfg), (900, 850))
        self.assertEqual(find.call_args.kwargs["window_handle"], 123)
        self.assertTrue(find.call_args.kwargs["exact"])
        self.assertTrue(find.call_args.kwargs["enabled_only"])

    def test_ocr_crop_offsets_and_window_inset_are_added_once(self):
        fake = SimpleNamespace(find_text=Mock(return_value=(
            [[100, 100], [200, 100], [200, 140], [100, 140]], "开始游戏", .95)))
        with patch.object(ww.uia, "find_by_text", return_value=None), \
                patch.dict(sys.modules, {"updater.disaster.ocr": fake}):
            self.assertEqual(ww.start_point(self.win, self.shot, self.cfg), (720, 780))
        self.shot.crop.assert_called_once_with((450, 440, 1000, 800))

    def test_announcement_with_start_prefix_is_rejected(self):
        fake = SimpleNamespace(find_text=Mock(return_value=(
            [[100, 100], [200, 100], [200, 140], [100, 140]], "开始游戏攻略", .99)))
        with patch.object(ww.uia, "find_by_text", return_value=None), \
                patch.dict(sys.modules, {"updater.disaster.ocr": fake}):
            self.assertIsNone(ww.start_point(self.win, self.shot, self.cfg))

    def test_disabled_or_partial_uia_button_is_rejected(self):
        rect = SimpleNamespace(left=0, top=0, right=10, bottom=10, width=lambda:10, height=lambda:10)
        ctrl = SimpleNamespace(Name="开始游戏", ControlTypeName="ButtonControl",
                               IsEnabled=False, BoundingRectangle=rect, GetChildren=lambda:[])
        self.assertIsNone(ww.uia._walk(ctrl, ["开始游戏"], ["Button"], 0, True, True))
        ctrl.IsEnabled = True
        ctrl.Name = "开始游戏攻略"
        self.assertIsNone(ww.uia._walk(ctrl, ["开始游戏"], ["Button"], 0, True, True))

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(ww.DEFAULTS, timeout=10, poll_interval=1, ready_seconds=2, click_interval=3)
        self.clock = Clock()

    def test_existing_game_exits_without_launch_or_click(self):
        with patch.object(ww.window, "_ensure_dpi_awareness"), \
                patch.object(ww, "game_running", return_value=True), \
                patch.object(ww.time, "monotonic", side_effect=lambda:self.clock.now), \
                patch.object(ww.time, "sleep", side_effect=self.clock.sleep), \
                patch.object(ww.subprocess, "Popen") as launch, patch.object(ww.inp, "click") as click:
            self.assertEqual(ww.run(self.cfg), 0)
        launch.assert_not_called()
        click.assert_not_called()

    def test_process_flicker_resets_stability_and_missing_button_times_out(self):
        with patch.object(ww.window, "_ensure_dpi_awareness"), \
                patch.object(ww, "game_running", side_effect=lambda _:self.clock.now in (0, 1, 3)), \
                patch.object(ww, "find_launcher", return_value=None), \
                patch.object(ww.time, "monotonic", side_effect=lambda:self.clock.now), \
                patch.object(ww.time, "sleep", side_effect=self.clock.sleep), \
                patch.object(ww.subprocess, "Popen") as launch:
            self.assertEqual(ww.run(self.cfg), 1)
        self.assertEqual(self.clock.now, 10)
        launch.assert_called_once()

    def test_click_then_wait_for_game_and_exit(self):
        with patch.object(ww.window, "_ensure_dpi_awareness"), \
                patch.object(ww.window, "screenshot"), patch.object(ww, "find_launcher", return_value="win"), \
                patch.object(ww, "start_point", return_value=(100, 200)), \
                patch.object(ww, "game_running", side_effect=lambda _:self.clock.now>=1), \
                patch.object(ww.time, "monotonic", side_effect=lambda:self.clock.now), \
                patch.object(ww.time, "sleep", side_effect=self.clock.sleep), \
                patch.object(ww.subprocess, "Popen"), patch.object(ww.inp, "click") as click:
            self.assertEqual(ww.run(self.cfg), 0)
        click.assert_called_once_with(100, 200)

    def test_parent_watchdog_kills_a_hung_worker(self):
        child = Mock()
        child.wait.side_effect = [ww.subprocess.TimeoutExpired("worker", 10), 1]
        with patch.object(ww, "load_config", return_value=self.cfg), \
                patch.object(ww, "check_dependencies"), \
                patch.object(ww.logging, "basicConfig"), \
                patch.object(ww.logging, "FileHandler", return_value=logging.NullHandler()), \
                patch.object(ww.subprocess, "Popen", return_value=child):
            self.assertEqual(ww.main([]), 1)
        child.kill.assert_called_once()
