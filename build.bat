@echo off
setlocal
chcp 65001 >nul
cd /d %~dp0

echo [1/3] 运行测试...
python -m unittest discover -s tests || goto :error

echo [2/3] 安装 PyInstaller...
python -m pip install pyinstaller || goto :error

echo [3/3] 开始打包...
python -m PyInstaller -F -w -n KeyLoop key_loop.py || goto :error

echo.
echo 打包完成! 生成文件: dist\KeyLoop.exe
pause
exit /b 0

:error
echo.
echo 操作失败，请检查上方错误信息。
pause
exit /b 1
