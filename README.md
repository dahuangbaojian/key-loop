# KeyLoop 按键精灵 Lite

KeyLoop 是一个 Windows 定时按键小工具。它提供 12 个独立按键槽位，可以为每个
槽位选择按键、触发间隔和启用状态，并通过全局热键统一开始或停止。

## 功能

- 12 个独立槽位，支持 F1~F12、数字、字母、空格、方向键等
- 每行单独设置触发间隔，使用稳定队列逐个发键，避免形成组合键
- 自定义全局开关热键，默认 Home，也可选择 F1~F12
- 使用 Win32 `SendInput` 和扫描码发送按键
- 按住时长可在 10~500 毫秒之间调整
- 窗口置顶、全部启用和全部停用
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
写入新的用户配置目录。

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
- 与开关热键相同的按键行会被忽略，避免模拟按键触发自身开关。
- 当间隔小于按住时长，或多个槽位同时到期时，会按稳定队列依次触发。
- 部分带反作弊的软件会屏蔽模拟按键。
- 请在目标软件或游戏规则允许的范围内使用。
