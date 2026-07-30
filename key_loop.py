# -*- coding: utf-8 -*-
"""KeyLoop 按键精灵 Lite - Windows 定时按键工具。"""

import ctypes
from ctypes import wintypes
import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

from key_loop_core import KeyBinding, KeyScheduler


if os.name != "nt":
    raise SystemExit("此工具仅支持 Windows（依赖 Win32 SendInput）")


# ---------------- Win32 SendInput 底层实现 ----------------
user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", InputUnion)]


user32.SendInput.argtypes = (
    wintypes.UINT,
    ctypes.POINTER(Input),
    ctypes.c_int,
)
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = wintypes.SHORT


def send_key_event(scan_code, extended=False, key_up=False):
    """发送一个扫描码按下或松开事件，成功时返回 True。"""

    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= KEYEVENTF_KEYUP

    union = InputUnion()
    union.ki = KeyBdInput(0, scan_code, flags, 0, 0)
    event = Input(INPUT_KEYBOARD, union)
    return user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) == 1


# ---------------- 按键与配置 ----------------
KEYS = {}
for _i in range(10):
    KEYS["F%d" % (_i + 1)] = (0x3B + _i, False)
KEYS["F11"] = (0x57, False)
KEYS["F12"] = (0x58, False)
for _i, _c in enumerate("1234567890"):
    KEYS[_c] = (0x02 + _i, False)
for _i, _c in enumerate("QWERTYUIOP"):
    KEYS[_c] = (0x10 + _i, False)
for _i, _c in enumerate("ASDFGHJKL"):
    KEYS[_c] = (0x1E + _i, False)
for _i, _c in enumerate("ZXCVBNM"):
    KEYS[_c] = (0x2C + _i, False)
KEYS.update(
    {
        "空格": (0x39, False),
        "Tab": (0x0F, False),
        "回车": (0x1C, False),
        "Esc": (0x01, False),
        "退格": (0x0E, False),
        "Shift": (0x2A, False),
        "Ctrl": (0x1D, False),
        "Alt": (0x38, False),
        "Home": (0x47, True),
        "↑": (0x48, True),
        "↓": (0x50, True),
        "←": (0x4B, True),
        "→": (0x4D, True),
    }
)

HOTKEY_VK = {"Home": 0x24}
HOTKEY_VK.update({"F%d" % (i + 1): 0x70 + i for i in range(12)})
NUM_ROWS = 12
DEFAULT_HOTKEY = "Home"

PROGRAM_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
LEGACY_CONFIG_FILE = os.path.join(PROGRAM_DIR, "key_loop_config.json")
APPDATA_DIR = os.environ.get("APPDATA")
USER_CONFIG_ROOT = (
    APPDATA_DIR
    or os.environ.get("LOCALAPPDATA")
    or os.path.expanduser("~")
)
CONFIG_DIR = os.path.join(USER_CONFIG_ROOT, "KeyLoop")
CONFIG_FILE = os.path.join(CONFIG_DIR, "key_loop_config.json")


# ---------------- 界面 ----------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("KeyLoop 按键精灵 Lite")
        root.resizable(False, False)

        self.running = False
        self.closed = False
        self.snapshot = ()
        self.hotkey_vk = HOTKEY_VK[DEFAULT_HOTKEY]
        self.hold_s = 0.03
        self.invalid_rows = 0
        self.config_error = ""
        self.send_error = ""

        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.toggle_requested = threading.Event()

        cfg = self.load_config()

        frm = ttk.Frame(root, padding=12)
        frm.grid()

        top = ttk.Frame(frm)
        top.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(top, text="开关热键").pack(side="left")
        self.hotkey_var = tk.StringVar(
            value=(
                cfg.get("hotkey")
                if cfg.get("hotkey") in HOTKEY_VK
                else DEFAULT_HOTKEY
            )
        )
        ttk.Combobox(
            top,
            textvariable=self.hotkey_var,
            width=4,
            values=list(HOTKEY_VK),
            state="readonly",
        ).pack(side="left", padx=(4, 12))
        ttk.Label(top, text="按住(毫秒)").pack(side="left")
        self.hold_var = tk.StringVar(value=str(cfg.get("hold_ms", 30)))
        ttk.Entry(top, textvariable=self.hold_var, width=5).pack(
            side="left", padx=(4, 12)
        )
        self.top_var = tk.BooleanVar(value=bool(cfg.get("topmost", True)))
        ttk.Checkbutton(
            top,
            text="窗口置顶",
            variable=self.top_var,
            command=self.apply_topmost,
        ).pack(side="left")
        self.apply_topmost()

        ttk.Label(frm, text="启用").grid(row=1, column=0, padx=4)
        ttk.Label(frm, text="按键").grid(row=1, column=1, padx=4)
        ttk.Label(frm, text="间隔(秒)").grid(row=1, column=2, padx=4)

        self.row_vars = []
        rows_cfg = cfg.get("rows") if isinstance(cfg.get("rows"), list) else []
        for i in range(NUM_ROWS):
            rc = (
                rows_cfg[i]
                if i < len(rows_cfg) and isinstance(rows_cfg[i], dict)
                else {}
            )
            en_var = tk.BooleanVar(value=bool(rc.get("enabled", i == 0)))
            key_var = tk.StringVar(
                value=(
                    rc.get("key")
                    if rc.get("key") in KEYS
                    else "F%d" % (i + 1)
                )
            )
            int_var = tk.StringVar(value=str(rc.get("interval", "1.0")))

            ttk.Checkbutton(frm, variable=en_var).grid(row=i + 2, column=0)
            ttk.Combobox(
                frm,
                textvariable=key_var,
                width=6,
                values=list(KEYS),
                state="readonly",
            ).grid(row=i + 2, column=1, padx=4, pady=2)
            ttk.Entry(frm, textvariable=int_var, width=8).grid(
                row=i + 2, column=2, padx=4
            )
            self.row_vars.append((en_var, key_var, int_var))

        bulk = ttk.Frame(frm)
        bulk.grid(
            row=NUM_ROWS + 2,
            column=0,
            columnspan=3,
            pady=(8, 0),
            sticky="ew",
        )
        ttk.Button(
            bulk, text="全部启用", command=lambda: self.set_all(True)
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(
            bulk, text="全部停用", command=lambda: self.set_all(False)
        ).pack(side="left", expand=True, fill="x")

        self.btn = ttk.Button(
            frm, text="开始 (%s)" % self.hotkey_var.get(), command=self.toggle
        )
        self.btn.grid(
            row=NUM_ROWS + 3,
            column=0,
            columnspan=3,
            pady=(6, 4),
            sticky="ew",
        )

        self.status = ttk.Label(frm, text="已停止", foreground="gray")
        self.status.grid(row=NUM_ROWS + 4, column=0, columnspan=3)

        ttk.Label(
            frm,
            text=(
                "提示: 开关热键全局有效，游戏内可直接开/关\n"
                "与开关热键相同的按键行不会被触发"
            ),
            foreground="#888",
            justify="center",
        ).grid(
            row=NUM_ROWS + 5,
            column=0,
            columnspan=3,
            pady=(6, 0),
        )

        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._sync_runtime_config()
        self.worker_thread = threading.Thread(
            target=self.worker, name="key-scheduler", daemon=True
        )
        self.hotkey_thread = threading.Thread(
            target=self.hotkey_listener, name="hotkey-listener", daemon=True
        )
        self.worker_thread.start()
        self.hotkey_thread.start()
        self.root.after(50, self._refresh_ui)

    # ---------- 配置 ----------
    def load_config(self):
        paths = [CONFIG_FILE]
        if LEGACY_CONFIG_FILE != CONFIG_FILE:
            paths.append(LEGACY_CONFIG_FILE)

        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, dict):
                    return data
                self.config_error = "配置格式无效，已使用默认值"
                return {}
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as exc:
                self.config_error = "读取配置失败: %s" % exc
                return {}
        return {}

    def save_config(self):
        rows = []
        for en_var, key_var, int_var in self.row_vars:
            try:
                interval = float(int_var.get())
            except ValueError:
                interval = int_var.get()
            rows.append(
                {
                    "enabled": en_var.get(),
                    "key": key_var.get(),
                    "interval": interval,
                }
            )
        try:
            hold_ms = float(self.hold_var.get())
        except ValueError:
            hold_ms = 30

        data = {
            "hotkey": self.hotkey_var.get(),
            "hold_ms": hold_ms,
            "topmost": self.top_var.get(),
            "rows": rows,
        }
        temporary_file = CONFIG_FILE + ".tmp"
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(temporary_file, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            os.replace(temporary_file, CONFIG_FILE)
            self.config_error = ""
            return True
        except OSError as exc:
            self.config_error = "保存配置失败: %s" % exc
            return False

    # ---------- 界面动作 ----------
    def apply_topmost(self):
        self.root.attributes("-topmost", self.top_var.get())

    def set_all(self, value):
        for en_var, _, _ in self.row_vars:
            en_var.set(value)
        self._sync_runtime_config()

    def toggle(self):
        if self.closed:
            return
        self.running = not self.running
        if self.running:
            self.send_error = ""
            self._sync_runtime_config()
            self.save_config()
        self.wake_event.set()
        self._update_status()

    def _sync_runtime_config(self):
        hotkey_name = self.hotkey_var.get()
        rows = []
        invalid_rows = 0

        for i, (en_var, key_var, int_var) in enumerate(self.row_vars):
            if not en_var.get():
                continue
            name = key_var.get()
            if name == hotkey_name:
                invalid_rows += 1
                continue
            info = KEYS.get(name)
            try:
                interval = float(int_var.get())
            except ValueError:
                invalid_rows += 1
                continue
            if not info or interval <= 0:
                invalid_rows += 1
                continue
            rows.append(KeyBinding(i, info[0], info[1], interval))

        try:
            hold_ms = float(self.hold_var.get())
        except ValueError:
            hold_ms = 30.0
            invalid_rows += 1

        new_snapshot = tuple(rows)
        new_hotkey_vk = HOTKEY_VK.get(
            hotkey_name, HOTKEY_VK[DEFAULT_HOTKEY]
        )
        new_hold_s = min(max(hold_ms, 10.0), 500.0) / 1000.0

        if (
            new_snapshot != self.snapshot
            or new_hotkey_vk != self.hotkey_vk
            or new_hold_s != self.hold_s
        ):
            self.snapshot = new_snapshot
            self.hotkey_vk = new_hotkey_vk
            self.hold_s = new_hold_s
            self.wake_event.set()
        self.invalid_rows = invalid_rows

    def _refresh_ui(self):
        if self.closed:
            return
        if self.toggle_requested.is_set():
            self.toggle_requested.clear()
            self.toggle()
        self._sync_runtime_config()
        self._update_status()
        self.root.after(50, self._refresh_ui)

    def _update_status(self):
        hotkey_name = self.hotkey_var.get()
        self.btn.config(
            text=("停止 (%s)" if self.running else "开始 (%s)") % hotkey_name
        )

        if self.config_error:
            self.status.config(text=self.config_error, foreground="red")
        elif self.send_error:
            self.status.config(text=self.send_error, foreground="red")
        elif self.running:
            suffix = (
                "，忽略 %d 项无效配置" % self.invalid_rows
                if self.invalid_rows
                else ""
            )
            self.status.config(
                text="运行中... 共 %d 个按键%s" % (len(self.snapshot), suffix),
                foreground="green",
            )
        else:
            self.status.config(text="已停止", foreground="gray")

    def on_close(self):
        if self.closed:
            return
        self.closed = True
        self.running = False
        self.save_config()
        self.stop_event.set()
        self.wake_event.set()
        self.worker_thread.join(timeout=0.5)
        self.hotkey_thread.join(timeout=0.5)
        self.root.destroy()

    # ---------- 后台线程 ----------
    def hotkey_listener(self):
        """轮询热键，只通过 Event 通知 Tk 主线程。"""

        pressed = False
        current_vk = self.hotkey_vk
        while not self.stop_event.is_set():
            if current_vk != self.hotkey_vk:
                current_vk = self.hotkey_vk
                pressed = False

            state = user32.GetAsyncKeyState(current_vk) & 0x8000
            if state and not pressed:
                pressed = True
                self.toggle_requested.set()
            elif not state:
                pressed = False
            self.stop_event.wait(0.05)

    def worker(self):
        """计算独立按键时序，并及时发送按下与松开事件。"""

        scheduler = KeyScheduler()
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                actions = scheduler.tick(
                    now, self.running, self.snapshot, self.hold_s
                )
                for action in actions:
                    success = send_key_event(
                        action.scan_code,
                        action.extended,
                        key_up=not action.key_down,
                    )
                    if not success:
                        self.send_error = (
                            "发键失败，请尝试以管理员身份运行"
                        )

                delay = scheduler.next_delay(time.monotonic())
                self.wake_event.wait(delay)
                self.wake_event.clear()
        finally:
            for action in scheduler.tick(
                time.monotonic(), False, (), self.hold_s
            ):
                send_key_event(
                    action.scan_code,
                    action.extended,
                    key_up=not action.key_down,
                )


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
