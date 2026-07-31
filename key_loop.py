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

from key_loop_core import BuffComboScheduler, perform_key_press


if os.name != "nt":
    raise SystemExit("此工具仅支持 Windows（依赖 Win32 SendInput）")


# ---------------- Win32 SendInput 底层实现 ----------------
user32 = ctypes.windll.user32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
GA_ROOT = 2
SW_RESTORE = 9


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
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL


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


def root_window_handle(window_handle):
    """将子窗口句柄规范化为所属顶层窗口句柄。"""

    if not window_handle:
        return 0
    return user32.GetAncestor(window_handle, GA_ROOT) or window_handle


def send_key_press(scan_code, extended, hold_s, shutdown_event):
    """发送一次完整按键，并从实际按下时刻计算按住时间。"""

    # 只允许程序退出提前结束等待；普通停止操作仍会完成本次按键，
    # 保证目标程序看到足够长且成对的按下/松开事件。
    return perform_key_press(
        scan_code,
        extended,
        hold_s,
        lambda code, ext, key_up: send_key_event(code, ext, key_up),
        shutdown_event.wait,
    )


def send_mouse_event(flags):
    """发送一个鼠标事件，成功时返回 True。"""

    union = InputUnion()
    union.mi = MouseInput(0, 0, 0, flags, 0, 0)
    event = Input(INPUT_MOUSE, union)
    return user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) == 1


def send_mouse_move(dx, dy):
    """发送相对鼠标移动，用于让游戏进入右键视角输入状态。"""

    union = InputUnion()
    union.mi = MouseInput(dx, dy, 0, MOUSEEVENTF_MOVE, 0, 0)
    event = Input(INPUT_MOUSE, union)
    return user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) == 1


def send_right_click(hold_s, shutdown_event):
    """发送一次完整右键点击。"""

    pressed = send_mouse_event(MOUSEEVENTF_RIGHTDOWN)
    if pressed:
        shutdown_event.wait(hold_s)
    released = send_mouse_event(MOUSEEVENTF_RIGHTUP)
    return pressed and released


# ---------------- 按键与配置 ----------------
BUFF_KEYS = {}
for _i in range(10):
    BUFF_KEYS["F%d" % (_i + 1)] = (0x3B + _i, False)
BUFF_KEYS["F11"] = (0x57, False)
BUFF_KEYS["F12"] = (0x58, False)
for _i, _c in enumerate("1234567890"):
    BUFF_KEYS[_c] = (0x02 + _i, False)

KEYBOARD_KEYS = dict(BUFF_KEYS)
for _i, _c in enumerate("QWERTYUIOP"):
    KEYBOARD_KEYS[_c] = (0x10 + _i, False)
for _i, _c in enumerate("ASDFGHJKL"):
    KEYBOARD_KEYS[_c] = (0x1E + _i, False)
for _i, _c in enumerate("ZXCVBNM"):
    KEYBOARD_KEYS[_c] = (0x2C + _i, False)
KEYBOARD_KEYS.update(
    {
        "空格": (0x39, False),
        "Tab": (0x0F, False),
        "回车": (0x1C, False),
        "Esc": (0x01, False),
        "退格": (0x0E, False),
        "Shift": (0x2A, False),
        "Ctrl": (0x1D, False),
        "Alt": (0x38, False),
        "↑": (0x48, True),
        "↓": (0x50, True),
        "←": (0x4B, True),
        "→": (0x4D, True),
    }
)

FUNCTION_BUFF_KEYS = tuple("F%d" % i for i in range(1, 13))
NUMBER_BUFF_KEYS = tuple("1234567890")
MOUSE_RIGHT = "鼠标右键"
ATTACK_OPTIONS = (MOUSE_RIGHT,) + tuple(KEYBOARD_KEYS)
START_KEY = "Home"
START_VK = 0x24
STOP_KEY = "End"
STOP_VK = 0x23
KEY_HOLD_MS = 80
KEY_HOLD_S = KEY_HOLD_MS / 1000.0
MOUSE_HOLD_MS = 30
MOUSE_HOLD_S = MOUSE_HOLD_MS / 1000.0
BUFF_MOUSE_CAPTURE_SETTLE_MS = 150
BUFF_MOUSE_CAPTURE_SETTLE_S = BUFF_MOUSE_CAPTURE_SETTLE_MS / 1000.0
DEFAULT_ATTACK_INTERVAL_S = 0.3
DEFAULT_BUFF_INTERVAL_S = 1200
DEFAULT_BUFF_KEY_INTERVAL_S = 3.0
FOCUS_SETTLE_MS = 300
START_CAPTURE_MS = 5000

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
        root.title("KeyLoop 游戏辅助")
        root.resizable(False, False)
        self._configure_styles()

        self.running = False
        self.closed = False
        self.start_job = None
        self.window_handle = 0
        self.target_window = 0
        self.runtime_config = (
            ("mouse", 0, False),
            DEFAULT_ATTACK_INTERVAL_S,
            (),
            DEFAULT_BUFF_INTERVAL_S,
            DEFAULT_BUFF_KEY_INTERVAL_S,
        )
        self.hold_s = KEY_HOLD_S
        self.validation_error = ""
        self.config_error = ""
        self.send_error = ""

        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.start_requested = threading.Event()
        self.stop_requested = threading.Event()
        self.focus_lost_requested = threading.Event()

        cfg = self.load_config()

        frm = ttk.Frame(root, padding=16, style="App.TFrame")
        frm.grid()

        header = ttk.Frame(frm, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(
            header,
            text="KeyLoop 游戏辅助",
            style="Title.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="%s 启动  ·  %s 停止" % (START_KEY, STOP_KEY),
            style="Hotkey.TLabel",
        ).pack(side="right")

        rows_cfg = cfg.get("rows") if isinstance(cfg.get("rows"), list) else []
        legacy_enabled_keys = {
            row.get("key")
            for row in rows_cfg
            if (
                isinstance(row, dict)
                and row.get("key") in BUFF_KEYS
                and bool(row.get("enabled", False))
            )
        }
        configured_keys = cfg.get("buff_keys")
        if isinstance(configured_keys, list):
            enabled_keys = {
                key for key in configured_keys if key in BUFF_KEYS
            }
        else:
            enabled_keys = legacy_enabled_keys

        configured_interval = cfg.get(
            "buff_interval", DEFAULT_BUFF_INTERVAL_S
        )
        configured_key_interval = cfg.get(
            "buff_key_interval", DEFAULT_BUFF_KEY_INTERVAL_S
        )
        configured_attack_interval = cfg.get(
            "attack_interval", DEFAULT_ATTACK_INTERVAL_S
        )

        attack = cfg.get("attack_key", MOUSE_RIGHT)
        if attack not in ATTACK_OPTIONS:
            attack = MOUSE_RIGHT

        attack_frame = ttk.LabelFrame(
            frm, text="攻击设置", padding=12, style="Section.TLabelframe"
        )
        attack_frame.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8)
        )
        self.attack_var = tk.StringVar(value=attack)
        ttk.Label(
            attack_frame, text="攻击键", style="Card.TLabel"
        ).pack(side="left")
        ttk.Combobox(
            attack_frame,
            textvariable=self.attack_var,
            width=10,
            values=ATTACK_OPTIONS,
            state="readonly",
        ).pack(side="left", padx=(6, 14))
        ttk.Label(
            attack_frame,
            text="攻击间隔（秒）",
            style="Card.TLabel",
        ).pack(side="left")
        self.attack_interval_var = tk.StringVar(
            value=str(configured_attack_interval)
        )
        ttk.Entry(
            attack_frame, textvariable=self.attack_interval_var, width=8
        ).pack(side="left", padx=(6, 0))

        combo_frame = ttk.LabelFrame(
            frm, text="Buff 设置", padding=12, style="Section.TLabelframe"
        )
        combo_frame.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8)
        )
        self.buff_interval_var = tk.StringVar(value=str(configured_interval))
        ttk.Label(
            combo_frame, text="整套间隔（秒）", style="Card.TLabel"
        ).pack(side="left")
        ttk.Entry(
            combo_frame, textvariable=self.buff_interval_var, width=10
        ).pack(side="left", padx=(6, 16))
        ttk.Label(
            combo_frame,
            text="按键间隔（秒）",
            style="Card.TLabel",
        ).pack(side="left")
        self.buff_key_interval_var = tk.StringVar(
            value=str(configured_key_interval)
        )
        ttk.Entry(
            combo_frame, textvariable=self.buff_key_interval_var, width=8
        ).pack(side="left", padx=(6, 0))

        self.row_vars = []

        groups = ttk.Frame(frm, style="App.TFrame")
        groups.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self._build_buff_group(
            groups,
            0,
            "F 键 Buff",
            FUNCTION_BUFF_KEYS,
            enabled_keys,
        )
        self._build_buff_group(
            groups,
            1,
            "数字键 Buff",
            NUMBER_BUFF_KEYS,
            enabled_keys,
        )

        bulk = ttk.Frame(frm, style="App.TFrame")
        bulk.grid(
            row=4,
            column=0,
            columnspan=2,
            pady=(8, 0),
            sticky="ew",
        )
        ttk.Button(
            bulk,
            text="全选 Buff",
            command=lambda: self.set_all(True),
            style="Secondary.TButton",
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(
            bulk,
            text="清空 Buff",
            command=lambda: self.set_all(False),
            style="Secondary.TButton",
        ).pack(side="left", expand=True, fill="x")

        actions = ttk.Frame(frm, style="App.TFrame")
        actions.grid(
            row=5,
            column=0,
            columnspan=2,
            pady=(10, 6),
            sticky="ew",
        )
        self.start_btn = ttk.Button(
            actions,
            text="启动  %s" % START_KEY,
            command=self.start,
            style="Primary.TButton",
        )
        self.start_btn.pack(
            side="left", expand=True, fill="x", padx=(0, 5)
        )
        self.stop_btn = ttk.Button(
            actions,
            text="停止  %s" % STOP_KEY,
            command=self.stop,
            style="Stop.TButton",
        )
        self.stop_btn.pack(
            side="left", expand=True, fill="x", padx=(5, 0)
        )

        self.status = ttk.Label(
            frm, text="● 已停止", style="Stopped.TLabel", anchor="center"
        )
        self.status.grid(row=6, column=0, columnspan=2)

        ttk.Label(
            frm,
            text="%s 启动后，请在 5 秒内切换到游戏；%s 停止。"
            % (START_KEY, STOP_KEY),
            style="Footer.TLabel",
            justify="center",
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            pady=(6, 0),
        )

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.update_idletasks()
        self.window_handle = root_window_handle(root.winfo_id())

        self._sync_runtime_config()
        self._update_status()
        self.worker_thread = threading.Thread(
            target=self.worker, name="key-scheduler", daemon=True
        )
        self.hotkey_thread = threading.Thread(
            target=self.hotkey_listener, name="hotkey-listener", daemon=True
        )
        self.worker_thread.start()
        self.hotkey_thread.start()
        self.root.after(50, self._refresh_ui)

    def _configure_styles(self):
        """使用轻量配色改善 Tk 默认界面。"""

        background = "#F3F6FB"
        card = "#FFFFFF"
        text = "#172033"
        muted = "#64748B"
        primary = "#2563EB"

        self.root.configure(background=background)
        self.root.option_add("*Font", ("Microsoft YaHei UI", 10))

        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background=background)
        style.configure(
            "Title.TLabel",
            background=background,
            foreground=text,
            font=("Microsoft YaHei UI", 17, "bold"),
        )
        style.configure(
            "Hotkey.TLabel",
            background=background,
            foreground=primary,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure(
            "Section.TLabelframe",
            background=card,
            bordercolor="#DCE3EE",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Section.TLabelframe.Label",
            background=background,
            foreground=text,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure("Card.TLabel", background=card, foreground=text)
        style.configure(
            "MutedCard.TLabel", background=card, foreground=muted
        )
        style.configure(
            "Card.TCheckbutton", background=card, foreground=text
        )
        style.map(
            "Card.TCheckbutton",
            background=[("active", card)],
        )
        style.configure(
            "Secondary.TButton",
            background="#E8EEF8",
            foreground=text,
            borderwidth=0,
            padding=(12, 7),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#DCE6F5")],
        )
        style.configure(
            "Primary.TButton",
            background=primary,
            foreground="#FFFFFF",
            borderwidth=0,
            padding=(14, 9),
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#1D4ED8"), ("disabled", "#AFC4EE")],
        )
        style.configure(
            "Stop.TButton",
            background="#E9EEF5",
            foreground="#334155",
            borderwidth=0,
            padding=(14, 9),
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map(
            "Stop.TButton",
            background=[("active", "#DCE3EC"), ("disabled", "#EEF2F7")],
        )
        style.configure(
            "Running.TLabel",
            background=background,
            foreground="#15803D",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure(
            "Stopped.TLabel", background=background, foreground=muted
        )
        style.configure(
            "Error.TLabel", background=background, foreground="#DC2626"
        )
        style.configure(
            "Footer.TLabel",
            background=background,
            foreground=muted,
            font=("Microsoft YaHei UI", 9),
        )

    def _build_buff_group(self, parent, column, title, keys, enabled_keys):
        parent.columnconfigure(column, weight=1)
        group = ttk.LabelFrame(
            parent, text=title, padding=10, style="Section.TLabelframe"
        )
        group.grid(row=0, column=column, padx=4, sticky="nsew")
        ttk.Label(group, text="启用", style="MutedCard.TLabel").grid(
            row=0, column=0, padx=6
        )
        ttk.Label(group, text="按键", style="MutedCard.TLabel").grid(
            row=0, column=1, padx=12
        )

        for row, key_name in enumerate(keys, start=1):
            enabled_var = tk.BooleanVar(value=key_name in enabled_keys)

            ttk.Checkbutton(
                group, variable=enabled_var, style="Card.TCheckbutton"
            ).grid(
                row=row, column=0
            )
            ttk.Label(
                group,
                text=key_name,
                width=5,
                anchor="center",
                style="Card.TLabel",
            ).grid(
                row=row, column=1, padx=12, pady=3
            )
            self.row_vars.append((key_name, enabled_var))

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
        def number_or_text(variable):
            try:
                return float(variable.get())
            except ValueError:
                return variable.get()

        data = {
            "version": 3,
            "attack_key": self.attack_var.get(),
            "attack_interval": number_or_text(self.attack_interval_var),
            "buff_interval": number_or_text(self.buff_interval_var),
            "buff_key_interval": number_or_text(
                self.buff_key_interval_var
            ),
            "buff_keys": [
                key_name
                for key_name, enabled_var in self.row_vars
                if enabled_var.get()
            ],
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
    def set_all(self, value):
        for _, enabled_var in self.row_vars:
            enabled_var.set(value)
        self._sync_runtime_config()

    def start(self):
        if self.closed or self.running or self.start_job is not None:
            return

        self.send_error = ""
        self._sync_runtime_config()
        if self.validation_error:
            self._update_status()
            return
        self.save_config()
        # 隐藏而不是最小化：最小化会激活 Windows 任务栏，导致
        # 全屏游戏底部残留任务栏。5 秒后才捕获前台游戏并启动。
        self.root.withdraw()
        self.start_job = self.root.after(
            START_CAPTURE_MS, self._capture_game_and_start
        )
        self._update_status()

    def _capture_game_and_start(self):
        self.start_job = None
        if self.closed:
            return

        foreground = root_window_handle(user32.GetForegroundWindow())
        if (
            not foreground
            or foreground == self.window_handle
            or not user32.IsWindow(foreground)
        ):
            self.running = False
            self.send_error = "未捕获到游戏，请按 Home 后在 5 秒内切到游戏"
            self._show_window()
            self._update_status()
            return

        self.target_window = foreground
        self.running = True
        self.wake_event.set()
        self._update_status()

    def stop(self):
        if self.closed:
            return

        if not self.running and self.start_job is None:
            return
        if self.start_job is not None:
            self.root.after_cancel(self.start_job)
            self.start_job = None
        self.running = False
        self.wake_event.set()
        self._show_window()
        self._update_status()

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.after(50, self.root.focus_force)

    def _ensure_game_focus(self):
        """每次发送输入前确认游戏焦点，必要时尝试恢复一次。"""

        if not self.running:
            return False

        target = self.target_window
        if not target or not user32.IsWindow(target):
            self._mark_focus_lost("游戏窗口已关闭，辅助已停止")
            return False

        if root_window_handle(user32.GetForegroundWindow()) == target:
            return True

        if user32.IsIconic(target):
            user32.ShowWindow(target, SW_RESTORE)
        user32.SetForegroundWindow(target)

        deadline = time.monotonic() + FOCUS_SETTLE_MS / 1000.0
        while self.running and not self.stop_event.is_set():
            if root_window_handle(user32.GetForegroundWindow()) == target:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self.wake_event.wait(min(remaining, 0.05))
            self.wake_event.clear()

        if self.running:
            self._mark_focus_lost("游戏失去焦点，辅助已停止")
        return False

    def _mark_focus_lost(self, message):
        self.send_error = message
        self.running = False
        self.wake_event.set()
        self.focus_lost_requested.set()

    def _show_focus_error(self):
        self._show_window()
        self._update_status()

    def _wait_buff_key_interval(self, seconds):
        """等待组合内按键间隔，同时允许 End 停止立即打断。"""

        deadline = time.monotonic() + seconds
        while self.running and not self.stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.wake_event.wait(remaining)
            self.wake_event.clear()

    def _sync_runtime_config(self):
        attack_name = self.attack_var.get()
        if attack_name == MOUSE_RIGHT:
            new_attack_action = ("mouse", 0, False)
        else:
            info = KEYBOARD_KEYS.get(attack_name)
            new_attack_action = (
                ("keyboard", info[0], info[1])
                if info
                else ("mouse", 0, False)
            )

        new_buff_snapshot = tuple(
            BUFF_KEYS[key_name]
            for key_name, enabled_var in self.row_vars
            if enabled_var.get()
        )

        validation_errors = []

        def positive_interval(variable, label):
            try:
                value = float(variable.get())
                if value <= 0:
                    raise ValueError
                return value
            except ValueError:
                validation_errors.append("%s必须大于 0" % label)
                return None

        new_attack_interval = positive_interval(
            self.attack_interval_var, "攻击间隔"
        )
        new_buff_interval = positive_interval(
            self.buff_interval_var, "整套 Buff 间隔"
        )
        new_buff_key_interval = positive_interval(
            self.buff_key_interval_var, "Buff 按键间隔"
        )

        new_state = (
            new_attack_action,
            new_attack_interval,
            new_buff_snapshot,
            new_buff_interval,
            new_buff_key_interval,
        )
        if new_state != self.runtime_config:
            self.runtime_config = new_state
            self.wake_event.set()
        self.validation_error = "；".join(validation_errors)

    def _refresh_ui(self):
        if self.closed:
            return
        if self.focus_lost_requested.is_set():
            self.focus_lost_requested.clear()
            self.start_requested.clear()
            self.stop_requested.clear()
            self._show_focus_error()
        elif self.stop_requested.is_set():
            self.stop_requested.clear()
            self.start_requested.clear()
            self.stop()
        elif self.start_requested.is_set():
            self.start_requested.clear()
            self.start()
        self._sync_runtime_config()
        self._update_status()
        self.root.after(50, self._refresh_ui)

    def _update_status(self):
        active = self.running or self.start_job is not None
        self.start_btn.config(state="disabled" if active else "normal")
        self.stop_btn.config(state="normal" if active else "disabled")

        if self.config_error:
            self.status.config(text=self.config_error, style="Error.TLabel")
        elif self.send_error:
            self.status.config(text=self.send_error, style="Error.TLabel")
        elif self.validation_error:
            self.status.config(
                text=self.validation_error, style="Error.TLabel"
            )
        elif self.start_job is not None:
            self.status.config(
                text="● 请在 5 秒内切换到游戏...",
                style="Running.TLabel",
            )
        elif self.running:
            _, _, buff_snapshot, _, _ = self.runtime_config
            self.status.config(
                text="● 运行中 · 攻击键 %s · Buff %d 个"
                % (self.attack_var.get(), len(buff_snapshot)),
                style="Running.TLabel",
            )
        else:
            self.status.config(text="● 已停止", style="Stopped.TLabel")

    def on_close(self):
        if self.closed:
            return
        self.closed = True
        self.running = False
        if self.start_job is not None:
            self.root.after_cancel(self.start_job)
            self.start_job = None
        self.save_config()
        self.stop_event.set()
        self.wake_event.set()
        self.worker_thread.join(timeout=0.5)
        self.hotkey_thread.join(timeout=0.5)
        self.root.destroy()

    # ---------- 后台线程 ----------
    def hotkey_listener(self):
        """轮询热键，只通过 Event 通知 Tk 主线程。"""

        start_pressed = False
        stop_pressed = False
        while not self.stop_event.is_set():
            start_state = user32.GetAsyncKeyState(START_VK) & 0x8000
            stop_state = user32.GetAsyncKeyState(STOP_VK) & 0x8000
            if start_state and not start_pressed:
                start_pressed = True
                self.start_requested.set()
            elif not start_state:
                start_pressed = False
            if stop_state and not stop_pressed:
                stop_pressed = True
                self.stop_requested.set()
            elif not stop_state:
                stop_pressed = False
            self.stop_event.wait(0.05)

    def worker(self):
        """Buff 组合优先执行；组合外按固定频率发送攻击键。"""

        scheduler = BuffComboScheduler()
        attack_deadline = None
        while not self.stop_event.is_set():
            if not self.running:
                attack_deadline = None

            now = time.monotonic()
            (
                attack_action,
                attack_interval,
                buff_snapshot,
                buff_interval,
                buff_key_interval,
            ) = self.runtime_config
            combo_enabled = (
                bool(buff_snapshot)
                and buff_interval is not None
                and buff_key_interval is not None
            )
            combo_due = scheduler.should_start(
                now,
                self.running,
                combo_enabled,
                buff_interval or DEFAULT_BUFF_INTERVAL_S,
            )
            if combo_due:
                # 整个组合期间按住右键，让游戏保持在视角输入状态。
                # 使用本次组合快照，确保按固定顺序完整执行。
                attack_deadline = None
                right_button_held = False
                try:
                    if not self._ensure_game_focus():
                        continue
                    right_button_held = send_mouse_event(
                        MOUSEEVENTF_RIGHTDOWN
                    )
                    if not right_button_held:
                        self._mark_focus_lost(
                            "无法按住鼠标右键，辅助已停止；请尝试以管理员身份运行"
                        )
                        continue

                    # 右移再移回，光标位置不变，但可触发游戏的视角捕获。
                    moved = send_mouse_move(1, 0)
                    moved_back = send_mouse_move(-1, 0)
                    if not moved or not moved_back:
                        self.send_error = "触发游戏视角输入失败"
                    self._wait_buff_key_interval(
                        BUFF_MOUSE_CAPTURE_SETTLE_S
                    )

                    for scan_code, extended in buff_snapshot:
                        if not self.running or self.stop_event.is_set():
                            break
                        if not self._ensure_game_focus():
                            break
                        success = send_key_press(
                            scan_code,
                            extended,
                            self.hold_s,
                            self.stop_event,
                        )
                        if not success:
                            self.send_error = (
                                "发送 Buff 失败，请尝试以管理员身份运行"
                            )
                        if not self.running or self.stop_event.is_set():
                            break
                        if not self._ensure_game_focus():
                            break

                        # 包括最后一个 Buff，给技能留下完整的生效时间。
                        self._wait_buff_key_interval(buff_key_interval)
                finally:
                    if right_button_held:
                        released = send_mouse_event(MOUSEEVENTF_RIGHTUP)
                        if not released:
                            released = send_mouse_event(MOUSEEVENTF_RIGHTUP)
                        if not released:
                            self._mark_focus_lost(
                                "无法松开鼠标右键，请手动右击一次"
                            )
                if self.running:
                    scheduler.complete(time.monotonic())
                continue

            now = time.monotonic()
            if self.running and attack_interval is not None:
                if attack_deadline is None:
                    attack_deadline = now
                if now >= attack_deadline:
                    if not self._ensure_game_focus():
                        continue
                    action_type, scan_code, extended = attack_action
                    if action_type == "mouse":
                        success = send_right_click(
                            MOUSE_HOLD_S, self.stop_event
                        )
                    else:
                        success = send_key_press(
                            scan_code,
                            extended,
                            self.hold_s,
                            self.stop_event,
                        )
                    if not success:
                        self.send_error = (
                            "发送攻击键失败，请尝试以管理员身份运行"
                        )
                    attack_deadline = now + attack_interval
                    continue
                delay = min(
                    scheduler.next_delay(now),
                    max(0.0, attack_deadline - now),
                )
            else:
                attack_deadline = None
                delay = scheduler.next_delay(now)
            self.wake_event.wait(delay)
            self.wake_event.clear()


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
