# -*- coding: utf-8 -*-
"""
KeyLoop 按键精灵 Lite
====================
Windows 定时按键工具，无需安装任何第三方库，系统自带 Python 即可运行：
    python key_loop.py

功能：
- 12 个按键槽位（默认 F1~F12），每行可自选按键、单独设置触发间隔
- 使用 SendInput + 扫描码发送按键，大部分游戏可识别
- 全局开关热键可自定义（默认 F8），游戏窗口聚焦时也能开/关
- 配置自动保存（key_loop_config.json），下次打开自动恢复

打包成 exe（在 Windows 上执行）：
    pip install pyinstaller
    pyinstaller -F -w -n KeyLoop key_loop.py
    生成的文件在 dist/KeyLoop.exe
"""

import ctypes
import json
import os
import sys
import threading
import time

if os.name != "nt":
    raise SystemExit("此工具仅支持 Windows（依赖 Win32 SendInput）")

import tkinter as tk
from tkinter import ttk

# ---------------- Win32 SendInput 底层实现 ----------------
user32 = ctypes.windll.user32

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]


class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]


class InputUnion(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),
                ("mi", MouseInput),
                ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("union", InputUnion)]


def press_key(scan_code, extended=False, hold=0.03):
    """按下并松开一个键（扫描码方式，游戏兼容性好）"""
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    extra = ctypes.c_ulong(0)
    union = InputUnion()
    union.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
    inp = Input(ctypes.c_ulong(1), union)
    user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))
    time.sleep(hold)
    union.ki = KeyBdInput(0, scan_code, flags | KEYEVENTF_KEYUP, 0,
                          ctypes.pointer(extra))
    inp = Input(ctypes.c_ulong(1), union)
    user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))


# ---------------- 按键表 ----------------
# 键名 -> (扫描码, 是否扩展键)
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
KEYS.update({
    "空格": (0x39, False), "Tab": (0x0F, False), "回车": (0x1C, False),
    "Esc": (0x01, False), "退格": (0x0E, False),
    "Shift": (0x2A, False), "Ctrl": (0x1D, False), "Alt": (0x38, False),
    "↑": (0x48, True), "↓": (0x50, True), "←": (0x4B, True), "→": (0x4D, True),
})

# 开关热键可选项（GetAsyncKeyState 轮询用的是虚拟键码）
HOTKEY_VK = {"F%d" % (i + 1): 0x70 + i for i in range(12)}

NUM_ROWS = 12
DEFAULT_HOTKEY = "F8"
# 配置文件放在脚本 / exe 同目录下
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                           "key_loop_config.json")


# ---------------- 界面 ----------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("KeyLoop 按键精灵 Lite")
        root.resizable(False, False)

        self.running = False
        # 后台线程只读这几个普通属性，所有 tk 变量都只在主线程访问
        self.snapshot = []          # [(行号, 扫描码, 扩展键, 间隔秒)]
        self.hotkey_vk = HOTKEY_VK[DEFAULT_HOTKEY]
        self.hold_s = 0.03

        cfg = self.load_config()

        frm = ttk.Frame(root, padding=12)
        frm.grid()

        # 顶部：开关热键 / 按住时长 / 窗口置顶
        top = ttk.Frame(frm)
        top.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(top, text="开关热键").pack(side="left")
        self.hotkey_var = tk.StringVar(
            value=cfg.get("hotkey") if cfg.get("hotkey") in HOTKEY_VK else DEFAULT_HOTKEY)
        ttk.Combobox(top, textvariable=self.hotkey_var, width=4,
                     values=list(HOTKEY_VK), state="readonly").pack(side="left", padx=(4, 12))
        ttk.Label(top, text="按住(毫秒)").pack(side="left")
        self.hold_var = tk.StringVar(value=str(cfg.get("hold_ms", 30)))
        ttk.Entry(top, textvariable=self.hold_var, width=5).pack(side="left", padx=(4, 12))
        self.top_var = tk.BooleanVar(value=bool(cfg.get("topmost", True)))
        ttk.Checkbutton(top, text="窗口置顶", variable=self.top_var,
                        command=self.apply_topmost).pack(side="left")
        self.apply_topmost()

        ttk.Label(frm, text="启用").grid(row=1, column=0, padx=4)
        ttk.Label(frm, text="按键").grid(row=1, column=1, padx=4)
        ttk.Label(frm, text="间隔(秒)").grid(row=1, column=2, padx=4)

        self.row_vars = []
        rows_cfg = cfg.get("rows") if isinstance(cfg.get("rows"), list) else []
        for i in range(NUM_ROWS):
            rc = rows_cfg[i] if i < len(rows_cfg) and isinstance(rows_cfg[i], dict) else {}
            en_var = tk.BooleanVar(value=bool(rc.get("enabled", i == 0)))
            key_var = tk.StringVar(
                value=rc.get("key") if rc.get("key") in KEYS else "F%d" % (i + 1))
            int_var = tk.StringVar(value=str(rc.get("interval", "1.0")))

            ttk.Checkbutton(frm, variable=en_var).grid(row=i + 2, column=0)
            ttk.Combobox(frm, textvariable=key_var, width=6,
                         values=list(KEYS), state="readonly").grid(
                row=i + 2, column=1, padx=4, pady=2)
            ttk.Entry(frm, textvariable=int_var, width=8).grid(row=i + 2, column=2, padx=4)
            self.row_vars.append((en_var, key_var, int_var))

        bulk = ttk.Frame(frm)
        bulk.grid(row=NUM_ROWS + 2, column=0, columnspan=3, pady=(8, 0), sticky="ew")
        ttk.Button(bulk, text="全部启用",
                   command=lambda: self.set_all(True)).pack(
            side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(bulk, text="全部停用",
                   command=lambda: self.set_all(False)).pack(
            side="left", expand=True, fill="x")

        self.btn = ttk.Button(frm, text="开始 (%s)" % self.hotkey_var.get(),
                              command=self.toggle)
        self.btn.grid(row=NUM_ROWS + 3, column=0, columnspan=3, pady=(6, 4), sticky="ew")

        self.status = ttk.Label(frm, text="已停止", foreground="gray")
        self.status.grid(row=NUM_ROWS + 4, column=0, columnspan=3)

        ttk.Label(frm, text="提示: 开关热键全局有效，游戏内可直接开/关\n与开关热键相同的按键行不会被触发",
                  foreground="#888", justify="center").grid(
            row=NUM_ROWS + 5, column=0, columnspan=3, pady=(6, 0))

        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._refresh_snapshot()
        threading.Thread(target=self.worker, daemon=True).start()
        threading.Thread(target=self.hotkey_listener, daemon=True).start()

    # ---------- 配置 ----------
    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_config(self):
        rows = []
        for en_var, key_var, int_var in self.row_vars:
            try:
                interval = float(int_var.get())
            except ValueError:
                interval = int_var.get()
            rows.append({"enabled": en_var.get(),
                         "key": key_var.get(),
                         "interval": interval})
        try:
            hold_ms = float(self.hold_var.get())
        except ValueError:
            hold_ms = 30
        data = {"hotkey": self.hotkey_var.get(),
                "hold_ms": hold_ms,
                "topmost": self.top_var.get(),
                "rows": rows}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 界面动作 ----------
    def apply_topmost(self):
        self.root.attributes("-topmost", self.top_var.get())

    def set_all(self, value):
        for en_var, _, _ in self.row_vars:
            en_var.set(value)

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.save_config()

    def _refresh_snapshot(self):
        """主线程定时把 tk 变量整理成普通数据，供后台线程读取"""
        hotkey_name = self.hotkey_var.get()
        rows = []
        for i, (en_var, key_var, int_var) in enumerate(self.row_vars):
            if not en_var.get():
                continue
            name = key_var.get()
            if name == hotkey_name:      # 与开关热键冲突，跳过防止自我开关
                continue
            info = KEYS.get(name)
            if not info:
                continue
            try:
                interval = float(int_var.get())
            except ValueError:
                continue
            if interval <= 0:
                continue
            rows.append((i, info[0], info[1], interval))
        self.snapshot = rows
        self.hotkey_vk = HOTKEY_VK.get(hotkey_name, HOTKEY_VK[DEFAULT_HOTKEY])
        try:
            hold = float(self.hold_var.get())
        except ValueError:
            hold = 30.0
        self.hold_s = min(max(hold, 10.0), 500.0) / 1000.0

        btn_text = ("停止 (%s)" if self.running else "开始 (%s)") % hotkey_name
        if self.btn["text"] != btn_text:
            self.btn.config(text=btn_text)
        if self.running:
            self.status.config(text="运行中... 共 %d 个按键" % len(rows),
                               foreground="green")
        else:
            self.status.config(text="已停止", foreground="gray")

        self.root.after(200, self._refresh_snapshot)

    def on_close(self):
        self.save_config()
        self.root.destroy()

    # ---------- 后台线程 ----------
    def hotkey_listener(self):
        """轮询开关热键，全局生效（游戏窗口聚焦时也能开关）"""
        pressed = False
        while True:
            state = user32.GetAsyncKeyState(self.hotkey_vk) & 0x8000
            if state and not pressed:
                pressed = True
                self.root.after(0, self.toggle)
            elif not state:
                pressed = False
            time.sleep(0.05)

    def worker(self):
        """主循环：到点就按对应的键"""
        next_fire = [0.0] * NUM_ROWS
        was_running = False
        while True:
            if self.running:
                if not was_running:
                    was_running = True
                    next_fire = [0.0] * NUM_ROWS   # 每次启动都立即触发一轮
                now = time.time()
                for i, scan, extended, interval in self.snapshot:
                    if now >= next_fire[i]:
                        press_key(scan, extended, self.hold_s)
                        next_fire[i] = now + interval
            else:
                was_running = False
            time.sleep(0.02)


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # 高分屏下界面不发虚
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()
