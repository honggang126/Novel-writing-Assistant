@echo off
echo 正在连接到GitHub仓库...

"C:\Program Files\Git\bin\git.exe" add .
"C:\Program Files\Git\bin\git.exe" commit -m "更新项目文件"
"C:\Program Files\Git\bin\git.exe" push -u origin master

echo.
echo 上传完成！
echo 项目已成功上传到：https://github.com/honggang126/Novel-writing-Assistant
pause