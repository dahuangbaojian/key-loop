@echo off
chcp 65001 >nul
cd /d %~dp0

echo [1/2] 安装 PyInstaller...
python -m pip install pyinstaller

echo [2/2] 开始打包...
python -m PyInstaller -F -w -n KeyLoop key_loop.py

echo.
echo 打包完成! 生成文件: dist\KeyLoop.exe
pause
