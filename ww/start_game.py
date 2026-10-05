"""Start Wuthering Waves through its launcher and exit when the game is ready."""
import argparse
import importlib
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "update"))
from updater.disaster import input as inp, uia, window

log = logging.getLogger("ww")
DEFAULTS = {
    "launcher_exe": r"C:\Program Files\Wuthering Waves\launcher.exe",
    "launch_args": [],
    "launcher_names": ["launcher.exe", "launcher_main.exe"],
    "window_keywords": ["鸣潮", "Wuthering"],
    "start_texts": ["开始游戏", "进入游戏", "启动游戏"],
    "game_names": ["Client-Win64-Shipping.exe"],
    "game_dir": r"C:\Program Files\Wuthering Waves\Wuthering Waves Game",
    "timeout": 180,
    "poll_interval": 2,
    "ready_seconds": 5,
    "click_interval": 20,
    "max_clicks": 3,
    "prefer_uia": True,
}


def load_config(path):
    import yaml
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig")) or {}
    spec = document.get("ww_launcher") or {}
    if not isinstance(spec, dict):
        raise ValueError("ww_launcher 必须是配置对象")
    cfg = {**DEFAULTS, **spec}
    for key in ("launcher_exe", "game_dir"):
        if not isinstance(cfg[key], str) or not cfg[key].strip():
            raise ValueError(f"ww_launcher.{key} 必须是非空路径")
    if not Path(cfg["launcher_exe"]).is_file():
        raise ValueError("鸣潮启动器文件不存在，请检查 ww_launcher.launcher_exe")
    if not Path(cfg["game_dir"]).is_dir():
        raise ValueError("鸣潮安装目录不存在，请检查 ww_launcher.game_dir")
    for key in ("window_keywords", "start_texts", "game_names", "launcher_names", "launch_args"):
        value = cfg[key]
        if (not isinstance(value, list) or (key != "launch_args" and not value)
                or any(not isinstance(v, str) or not v.strip() for v in value)):
            raise ValueError(f"ww_launcher.{key} 必须是文字列表")
    for key in ("timeout", "poll_interval", "ready_seconds", "click_interval", "max_clicks"):
        value = cfg[key]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError(f"ww_launcher.{key} 必须大于零")
    if not isinstance(cfg["max_clicks"], int):
        raise ValueError("ww_launcher.max_clicks 必须是整数")
    if cfg["ready_seconds"] >= cfg["timeout"]:
        raise ValueError("ready_seconds 必须小于 timeout")
    if not isinstance(cfg["prefer_uia"], bool):
        raise ValueError("ww_launcher.prefer_uia 必须是 true/false")
    return cfg


def check_dependencies():
    for name in ("psutil", "pygetwindow", "win32gui", "win32process", "PIL.ImageGrab",
                 "uiautomation", "rapidocr", "numpy", "cv2", "pyautogui"):
        importlib.import_module(name)


def game_running(cfg):
    import psutil
    wanted = {name.casefold() for name in cfg["game_names"]}
    base = os.path.normcase(os.path.abspath(cfg["game_dir"])) + os.sep
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info["name"] or "").casefold() not in wanted:
                continue
            if os.path.normcase(os.path.abspath(process.exe())).startswith(base):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def find_launcher(cfg):
    """Match both installation path and owning PID; titles alone are ambiguous."""
    import psutil
    import pygetwindow as gw
    import win32process
    target = os.path.normcase(os.path.abspath(cfg["launcher_exe"]))
    base = str(Path(target).parent) + os.sep
    names = {name.casefold() for name in cfg["launcher_names"]}
    names.add(Path(target).name.casefold())
    pids = set()
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info["name"] or "").casefold() not in names:
                continue
            if os.path.normcase(os.path.abspath(process.exe())).startswith(base):
                pids.add(process.pid)
                pids.update(child.pid for child in process.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    words = [word.casefold() for word in cfg["window_keywords"]]
    for win in gw.getAllWindows():
        try:
            if (win.visible and any(word in win.title.casefold() for word in words)
                    and win32process.GetWindowThreadProcessId(win._hWnd)[1] in pids):
                return win
        except Exception:
            continue
    return None


def start_point(win, shot, cfg):
    """UIA uses screen coordinates; OCR uses the cropped screenshot coordinates."""
    # Limit all hits to the action area at bottom right, away from announcements.
    left, top = int(shot.width * .45), int(shot.height * .55)
    region_left, region_top, region_right, region_bottom = window._inset_rect(
        (win.left, win.top, win.left + win.width, win.top + win.height))
    if cfg["prefer_uia"]:
        try:
            box = uia.find_by_text(cfg["window_keywords"], cfg["start_texts"],
                                   control_types=("Button",), window_handle=win._hWnd,
                                   exact=True, enabled_only=True)
            if box:
                x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                if (region_left + left <= x < region_right
                        and region_top + top <= y < region_bottom):
                    log.info("UIA 识别到开始游戏")
                    return int(x), int(y)
        except Exception as exc:
            log.warning("UIA 暂不可用，转 OCR：%s", type(exc).__name__)
    panel = shot.crop((left, top, shot.width, shot.height))
    from updater.disaster import ocr
    hit = ocr.find_text(panel, cfg["start_texts"], sliding=True, min_score=.85,
                        max_text_len=max(map(len, cfg["start_texts"])))
    if hit and "".join(hit[1].split()) in cfg["start_texts"]:
        box = hit[0]
        x = sum(point[0] for point in box) / len(box) + left
        y = sum(point[1] for point in box) / len(box) + top
        if left <= x < shot.width and top <= y < shot.height:
            log.info("OCR 识别到开始游戏，置信度 %.2f", hit[2])
            return int(region_left + x), int(region_top + y)
    return None


def run(cfg):
    window._ensure_dpi_awareness()
    deadline = time.monotonic() + cfg["timeout"]
    ready_since = None
    last_click = float("-inf")
    clicks = 0
    launched = False
    while time.monotonic() < deadline:
        if game_running(cfg):
            if ready_since is None:
                ready_since = time.monotonic()
            if time.monotonic() - ready_since >= cfg["ready_seconds"]:
                log.info("鸣潮游戏进程已稳定出现，启动脚本自动退出")
                return 0
        else:
            ready_since = None
            if not launched:
                subprocess.Popen([cfg["launcher_exe"], *cfg["launch_args"]],
                                 cwd=str(Path(cfg["launcher_exe"]).parent))
                launched = True
                log.info("已调用鸣潮启动器")
            if clicks < cfg["max_clicks"] and time.monotonic() - last_click >= cfg["click_interval"]:
                try:
                    win = find_launcher(cfg)
                    if win is not None:
                        shot = window.screenshot(win)
                        point = start_point(win, shot, cfg)
                        if point and time.monotonic() < deadline and not game_running(cfg):
                            inp.click(*point)
                            clicks += 1
                            last_click = time.monotonic()
                            log.info("点击开始游戏 %d/%d，等待游戏进程", clicks, cfg["max_clicks"])
                except Exception as exc:
                    log.warning("本轮识别失败，将重试：%s", type(exc).__name__)
        time.sleep(min(cfg["poll_interval"], max(0, deadline - time.monotonic())))
    log.error("启动超时，游戏进程未稳定出现；辅助脚本返回失败")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="通过鸣潮启动器点击开始游戏，成功或超时后自动退出")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--check", action="store_true", help="只检查配置和依赖，不启动或点击")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    log_dir = ROOT / "ww" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(log_dir / "start_game.log", encoding="utf-8")])
    # Keep recognition screenshots local, separately from the updater's logs.
    window.SHOT_DIR = log_dir / "screenshots"
    try:
        cfg = load_config(args.config)
        check_dependencies()
        if args.check:
            log.info("鸣潮启动配置和 UIA/OCR 依赖检查通过")
            return 0
        if args.worker:
            import msvcrt
            with (log_dir / "start_game.lock").open("a+b") as lock:
                lock.write(b" ")
                lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                return run(cfg)
        # Isolate UIA/OCR calls so even an unresponsive COM call cannot hang the helper.
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                  "--config", str(args.config.resolve()), "--worker"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            return child.wait(timeout=cfg["timeout"])
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            log.error("达到启动时间上限，识别子进程已退出")
            return 1
        except BaseException:
            if child.poll() is None:
                child.kill()
                child.wait()
            raise
    except Exception as exc:
        log.error("启动失败：%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
