# KeyLoop 按键精灵 Lite

KeyLoop 是一个 Windows 游戏辅助按键小工具。攻击键可以选择鼠标右键或键盘键，
Buff 区固定提供 F1~F12 和数字键 1~0，可勾选任意数量组成一个循环组合。

## 功能

- 攻击键支持鼠标右键、F1~F12、数字、字母和常用功能键
- 攻击键常驻运行，触发间隔可配置，默认 0.3 秒
- 固定提供 F1~F12 和数字键 1~0，共 22 个可选 Buff 组合键
- 整套 Buff 循环间隔可配置，默认 1200 秒（20 分钟）
- 组合内相邻 Buff 按键间隔可配置，默认 3 秒
- Home 启动后先按顺序执行完整 Buff 组合，再开始攻击
- Home 后预留 5 秒切换到游戏，倒计时结束时记录当前游戏窗口
- 记录后锁定本次游戏窗口，每个 Buff 和攻击键发送前都会重新校验焦点
- Buff 组合期间自动暂停攻击，组合完成后自动恢复
- 全局热键固定为 Home 启动、End 停止，游戏内也可直接操作
- 使用 Win32 `SendInput` 和扫描码发送按键
- 键盘按住时长固定为 80 毫秒，鼠标右键按住时长固定为 30 毫秒
- 开始后自动隐藏到后台，停止时自动恢复窗口，不激活 Windows 任务栏
- 配置自动保存，并兼容旧版同目录配置
- 每次按键都保证完整的按下时长并成对松开

## 直接运行

需要 Windows 以及 Python 3.8 或更高版本。程序本身只使用 Python 标准库：

```bat
python key_loop.py
```

配置保存在：

```text
%APPDATA%\KeyLoop\key_loop_config.json
```

如果程序目录中存在旧版 `key_loop_config.json`，首次启动时仍会读取；下一次保存会
写入新的用户配置目录。旧配置会按键名迁移已启用的 F1~F12 和 1~0；整套 Buff
间隔、Buff 按键间隔和攻击间隔分别使用 1200、3 和 0.3 秒的默认值。其他过期配置
会被忽略。

## 打包成 exe

必须在 Windows 上打包。可以双击 `build.bat`，也可以手动执行：

```bat
python -m pip install pyinstaller
python -m PyInstaller -F -w -n KeyLoop key_loop.py
```

生成文件位于 `dist\KeyLoop.exe`。使用 exe 的用户不需要安装 Python。

常用选项：

- 自定义图标：增加 `-i icon.ico`
- 默认请求管理员权限：增加 `--uac-admin`
- 降低单文件打包的误报概率：把 `-F` 改成 `-D`

## 开发与测试

调度逻辑位于 `key_loop_core.py`，不依赖 Windows API，可以在任意平台运行测试：

```shell
python -m unittest discover -s tests
python -m py_compile key_loop.py key_loop_core.py
```

GitHub Actions 会先运行测试，再在 Windows 环境构建 exe。

## 注意事项

- 如果目标程序以管理员身份运行，KeyLoop 通常也需要以管理员身份运行，否则会受到
  Windows UIPI 限制。
- Home 固定启动，End 固定停止；F1~F12 和 1~0 固定作为 Buff 组合列表。
- 点击启动或按 Home 后，KeyLoop 会隐藏并等待 5 秒；在倒计时内切到游戏，第 5 秒
  记录当前前台窗口并开始 Buff。未捕获到有效窗口时不会发送按键。
- 运行中若游戏意外失焦，会先尝试恢复；恢复失败则立即停止，不向其他窗口发送按键。
- Buff 组合按照 F1~F12、1~0 的固定顺序串行触发，攻击键不会插入组合。
- 下一轮循环间隔从整套 Buff 组合执行完成后开始计算，不会出现组合重叠或集中补发。
- 部分带反作弊的软件会屏蔽模拟按键。
- 请在目标软件或游戏规则允许的范围内使用。
