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
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


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
TOGGLE_KEY = "Home"
TOGGLE_VK = 0x24
KEY_HOLD_MS = 80
KEY_HOLD_S = KEY_HOLD_MS / 1000.0
MOUSE_HOLD_MS = 30
MOUSE_HOLD_S = MOUSE_HOLD_MS / 1000.0
ATTACK_INTERVAL_S = 0.3
BUFF_GAP_S = 1.5
DEFAULT_BUFF_INTERVAL_S = 1200

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
        self.start_job = None
        self.runtime_config = (
            ("mouse", 0, False),
            (),
            DEFAULT_BUFF_INTERVAL_S,
        )
        self.hold_s = KEY_HOLD_S
        self.invalid_buff_interval = False
        self.config_error = ""
        self.send_error = ""

        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.toggle_requested = threading.Event()

        cfg = self.load_config()

        frm = ttk.Frame(root, padding=12)
        frm.grid()

        top = ttk.Frame(frm)
        top.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(
            top,
            text=(
                "开关键: %s    攻击: %.1f 秒/次    Buff 吟唱间隔: %.1f 秒"
                % (TOGGLE_KEY, ATTACK_INTERVAL_S, BUFF_GAP_S)
            ),
        ).pack(side="left")

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

        attack = cfg.get("attack_key", MOUSE_RIGHT)
        if attack not in ATTACK_OPTIONS:
            attack = MOUSE_RIGHT
        attack_frame = ttk.LabelFrame(frm, text="攻击键", padding=8)
        attack_frame.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8)
        )
        self.attack_var = tk.StringVar(value=attack)
        ttk.Label(attack_frame, text="按键:").pack(side="left")
        ttk.Combobox(
            attack_frame,
            textvariable=self.attack_var,
            width=10,
            values=ATTACK_OPTIONS,
            state="readonly",
        ).pack(side="left", padx=(6, 14))
        ttk.Label(
            attack_frame,
            text="固定每 %.1f 秒触发一次" % ATTACK_INTERVAL_S,
        ).pack(side="left")

        combo_frame = ttk.LabelFrame(frm, text="Buff 组合", padding=8)
        combo_frame.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8)
        )
        self.buff_interval_var = tk.StringVar(value=str(configured_interval))
        ttk.Label(combo_frame, text="组合循环间隔(秒):").pack(side="left")
        ttk.Entry(
            combo_frame, textvariable=self.buff_interval_var, width=10
        ).pack(side="left", padx=(6, 14))
        ttk.Label(
            combo_frame,
            text="组合内按键依次触发，每个键留 %.1f 秒吟唱时间"
            % BUFF_GAP_S,
        ).pack(side="left")

        self.row_vars = []

        groups = ttk.Frame(frm)
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

        bulk = ttk.Frame(frm)
        bulk.grid(
            row=4,
            column=0,
            columnspan=2,
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
            frm, text="开始 (%s)" % TOGGLE_KEY, command=self.toggle
        )
        self.btn.grid(
            row=5,
            column=0,
            columnspan=2,
            pady=(6, 4),
            sticky="ew",
        )

        self.status = ttk.Label(frm, text="已停止", foreground="gray")
        self.status.grid(row=6, column=0, columnspan=2)

        ttk.Label(
            frm,
            text=(
                "提示: Home 开关键全局有效，开始后自动隐藏窗口\n"
                "Buff 组合执行时自动暂停攻击，组合结束后自动恢复"
            ),
            foreground="#888",
            justify="center",
        ).grid(
            row=7,
            column=0,
            columnspan=2,
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

    def _build_buff_group(self, parent, column, title, keys, enabled_keys):
        group = ttk.LabelFrame(parent, text=title, padding=8)
        group.grid(row=0, column=column, padx=4, sticky="n")
        ttk.Label(group, text="启用").grid(row=0, column=0, padx=4)
        ttk.Label(group, text="按键").grid(row=0, column=1, padx=8)

        for row, key_name in enumerate(keys, start=1):
            enabled_var = tk.BooleanVar(value=key_name in enabled_keys)

            ttk.Checkbutton(group, variable=enabled_var).grid(
                row=row, column=0
            )
            ttk.Label(group, text=key_name, width=4, anchor="center").grid(
                row=row, column=1, padx=8, pady=2
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
        try:
            buff_interval = float(self.buff_interval_var.get())
        except ValueError:
            buff_interval = self.buff_interval_var.get()
        data = {
            "version": 2,
            "attack_key": self.attack_var.get(),
            "buff_interval": buff_interval,
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

    def toggle(self):
        if self.closed:
            return

        if self.start_job is not None:
            self.root.after_cancel(self.start_job)
            self.start_job = None
            self._show_window()
            self._update_status()
            return

        if self.running:
            self.running = False
            self.wake_event.set()
            self._show_window()
        else:
            self.send_error = ""
            self._sync_runtime_config()
            self.save_config()
            # 隐藏而不是最小化：最小化会激活 Windows 任务栏，导致
            # 全屏游戏底部残留任务栏。隐藏后再给游戏恢复焦点的时间。
            self.root.withdraw()
            self.start_job = self.root.after(200, self._start_running)
        self._update_status()

    def _start_running(self):
        self.start_job = None
        if self.closed:
            return
        self.running = True
        self.wake_event.set()
        self._update_status()

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.after(50, self.root.focus_force)

    def _wait_buff_gap(self):
        """等待固定 Buff 间隔，同时允许 Home 停止立即打断。"""

        deadline = time.monotonic() + BUFF_GAP_S
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
        try:
            new_buff_interval = float(self.buff_interval_var.get())
            if new_buff_interval <= 0:
                raise ValueError
            invalid_buff_interval = False
        except ValueError:
            new_buff_interval = None
            invalid_buff_interval = True

        new_state = (
            new_attack_action,
            new_buff_snapshot,
            new_buff_interval,
        )
        if new_state != self.runtime_config:
            self.runtime_config = new_state
            self.wake_event.set()
        self.invalid_buff_interval = invalid_buff_interval

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
        self.btn.config(
            text=("停止 (%s)" if self.running else "开始 (%s)") % TOGGLE_KEY
        )

        if self.config_error:
            self.status.config(text=self.config_error, foreground="red")
        elif self.send_error:
            self.status.config(text=self.send_error, foreground="red")
        elif self.running:
            _, buff_snapshot, _ = self.runtime_config
            suffix = (
                "，Buff 间隔无效，组合已暂停"
                if self.invalid_buff_interval
                else ""
            )
            self.status.config(
                text="运行中... 攻击键 %s，Buff 组合 %d 个按键%s"
                % (self.attack_var.get(), len(buff_snapshot), suffix),
                foreground="green",
            )
        else:
            self.status.config(text="已停止", foreground="gray")

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

        pressed = False
        while not self.stop_event.is_set():
            state = user32.GetAsyncKeyState(TOGGLE_VK) & 0x8000
            if state and not pressed:
                pressed = True
                self.toggle_requested.set()
            elif not state:
                pressed = False
            self.stop_event.wait(0.05)

    def worker(self):
        """Buff 组合优先执行；组合外按固定频率发送攻击键。"""

        scheduler = BuffComboScheduler()
        attack_deadline = None
        while not self.stop_event.is_set():
            if not self.running:
                attack_deadline = None

            now = time.monotonic()
            attack_action, buff_snapshot, buff_interval = self.runtime_config
            combo_enabled = bool(buff_snapshot) and buff_interval is not None
            combo_due = scheduler.should_start(
                now,
                self.running,
                combo_enabled,
                buff_interval or DEFAULT_BUFF_INTERVAL_S,
            )
            if combo_due:
                # 整个组合执行期间不发送攻击键。使用本次组合快照，
                # 确保按 F1~F12、1~0 的固定顺序完整执行。
                attack_deadline = None
                for scan_code, extended in buff_snapshot:
                    if not self.running or self.stop_event.is_set():
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
                    if self.running:
                        self._wait_buff_gap()
                if self.running:
                    scheduler.complete(time.monotonic())
                continue

            now = time.monotonic()
            if self.running:
                if attack_deadline is None:
                    attack_deadline = now
                if now >= attack_deadline:
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
                    attack_deadline = now + ATTACK_INTERVAL_S
                    continue
                delay = min(
                    scheduler.next_delay(now),
                    max(0.0, attack_deadline - now),
                )
            else:
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
