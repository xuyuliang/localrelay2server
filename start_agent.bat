@echo off

rem 显示启动信息
echo 正在启动腾讯元器智能体代理服务...
echo.

rem 激活虚拟环境
echo 正在激活虚拟环境...
call venv\Scripts\activate

if %ERRORLEVEL% neq 0 (
    echo 错误：无法激活虚拟环境，请检查venv目录是否存在
    pause
    exit /b 1
)

echo 虚拟环境激活成功！
echo.

rem 运行Python脚本
echo 正在启动connAgent.py...
python local-lama.py

rem 脚本结束后的处理
if %ERRORLEVEL% neq 0 (
    echo 错误：程序异常退出
    pause
    exit /b 1
)

rem 按任意键退出
echo 程序已结束
pause