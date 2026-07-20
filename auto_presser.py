# -*- coding: utf-8 -*-
"""
按键精灵 Lite - Windows 定时按键小工具
无需安装任何第三方库，直接用系统自带 Python 运行:
    python auto_presser.py

使用 SendInput + 扫描码发送按键，对大部分游戏有效。
F8 全局开关(游戏窗口内也能用)。
"""

import ctypes
import threading
import time
import tkinter as tk
from tkinter import ttk

# ---------------- SendInput 底层实现 ----------------
user32 = ctypes.windll.user32

KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002

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


# 常用键的扫描码
SCAN_CODES = {
    "F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E,
    "F5": 0x3F, "F6": 0x40, "F7": 0x41, "F9": 0x43, "F10": 0x44,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "Q": 0x10, "W": 0x11, "E": 0x12, "R": 0x13, "T": 0x14,
    "A": 0x1E, "S": 0x1F, "D": 0x20, "F": 0x21, "G": 0x22,
    "Z": 0x2C, "X": 0x2D, "C": 0x2E, "V": 0x2F,
    "空格": 0x39, "Tab": 0x0F,
}


def press_key(scan_code, hold=0.03):
    """按下并松开一个键(扫描码方式，游戏兼容性好)"""
    extra = ctypes.c_ulong(0)
    union = InputUnion()
    union.ki = KeyBdInput(0, scan_code, KEYEVENTF_SCANCODE, 0, ctypes.pointer(extra))
    inp = Input(ctypes.c_ulong(1), union)
    user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))
    time.sleep(hold)
    union.ki = KeyBdInput(0, scan_code, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0,
                          ctypes.pointer(extra))
    inp = Input(ctypes.c_ulong(1), union)
    user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))


# ---------------- 界面 ----------------
NUM_ROWS = 4
VK_F8 = 0x77


class App:
    def __init__(self, root):
        self.root = root
        root.title("按键精灵 Lite")
        root.attributes("-topmost", True)  # 窗口置顶，方便观察状态
        root.resizable(False, False)

        self.running = False
        self.rows = []

        frm = ttk.Frame(root, padding=12)
        frm.grid()

        ttk.Label(frm, text="启用").grid(row=0, column=0, padx=4)
        ttk.Label(frm, text="按键").grid(row=0, column=1, padx=4)
        ttk.Label(frm, text="间隔(秒)").grid(row=0, column=2, padx=4)

        defaults = [("F1", "1.0", True), ("F2", "2.0", True),
                    ("F3", "5.0", False), ("F4", "10.0", False)]

        for i, (key, interval, enabled) in enumerate(defaults):
            en_var = tk.BooleanVar(value=enabled)
            key_var = tk.StringVar(value=key)
            int_var = tk.StringVar(value=interval)

            ttk.Checkbutton(frm, variable=en_var).grid(row=i + 1, column=0)
            cb = ttk.Combobox(frm, textvariable=key_var, width=6,
                              values=list(SCAN_CODES.keys()), state="readonly")
            cb.grid(row=i + 1, column=1, padx=4, pady=3)
            ttk.Entry(frm, textvariable=int_var, width=8).grid(row=i + 1, column=2, padx=4)

            self.rows.append((en_var, key_var, int_var))

        self.btn = ttk.Button(frm, text="开始 (F8)", command=self.toggle)
        self.btn.grid(row=NUM_ROWS + 1, column=0, columnspan=3, pady=(10, 4), sticky="ew")

        self.status = ttk.Label(frm, text="已停止", foreground="gray")
        self.status.grid(row=NUM_ROWS + 2, column=0, columnspan=3)

        ttk.Label(frm, text="提示: F8 可在游戏内直接开/关",
                  foreground="#888").grid(row=NUM_ROWS + 3, column=0, columnspan=3, pady=(6, 0))

        # 后台线程: 定时按键 + 监听 F8
        threading.Thread(target=self.worker, daemon=True).start()
        threading.Thread(target=self.hotkey_listener, daemon=True).start()

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.btn.config(text="停止 (F8)")
            self.status.config(text="运行中...", foreground="green")
        else:
            self.btn.config(text="开始 (F8)")
            self.status.config(text="已停止", foreground="gray")

    def hotkey_listener(self):
        """轮询 F8，全局生效(游戏窗口聚焦时也能开关)"""
        pressed = False
        while True:
            state = user32.GetAsyncKeyState(VK_F8) & 0x8000
            if state and not pressed:
                pressed = True
                self.root.after(0, self.toggle)
            elif not state:
                pressed = False
            time.sleep(0.05)

    def worker(self):
        """主循环: 到点就按对应的键"""
        next_fire = [0.0] * NUM_ROWS
        while True:
            if self.running:
                now = time.time()
                for i, (en_var, key_var, int_var) in enumerate(self.rows):
                    if not en_var.get():
                        continue
                    try:
                        interval = float(int_var.get())
                        if interval <= 0:
                            continue
                    except ValueError:
                        continue
                    if now >= next_fire[i]:
                        code = SCAN_CODES.get(key_var.get())
                        if code:
                            press_key(code)
                        next_fire[i] = now + interval
            else:
                next_fire = [0.0] * NUM_ROWS  # 停止后重置，重新开始立即触发
            time.sleep(0.02)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
