




@echo off

REM 设置Python环境变量（如果需要）
REM set PATH=C:\Python313;C:\Python313\Scripts;%PATH%

REM 安装必要的依赖（如果需要）
pip install pyinstaller

REM 执行打包命令
pyinstaller --onefile --windowed --icon=temp_icon.ico 写小说软件_09.py

echo 打包完成！
pause