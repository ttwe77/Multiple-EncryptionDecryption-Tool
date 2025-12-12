@echo off
:: RSA4096 加密/解密工具（支持 UTF-8、Base64 交互，支持密钥选择及一键生成密钥对）

chcp 65001 >nul
setlocal enabledelayedexpansion

:: 检查 OpenSSL 是否安装
where openssl >nul 2>&1
if errorlevel 1 (
    echo 未检测到 OpenSSL，可从 https://slproweb.com/products/Win32OpenSSL.html 下载并安装后重试。
    pause
    exit /b
)

::手动设置工作目录
::cd G:\Windows11\0Tools\0Project\RSA
:: 强制切换到脚本所在目录
pushd "%~dp0"

:: 自动获取批处理脚本所在目录作为工作目录
set "WORK_DIR=%~dp0"
set "WORK_DIR=%WORK_DIR:~0,-1%"

:: 自动创建私钥和公钥目录
set PRIVATE_DIR=%WORK_DIR%\private_keys
set PUBLIC_DIR=%WORK_DIR%\public_keys
if not exist "%PRIVATE_DIR%" mkdir "%PRIVATE_DIR%"
if not exist "%PUBLIC_DIR%" mkdir "%PUBLIC_DIR%"

:menu
cls
cd %WORK_DIR%
echo.
echo ===============================
echo   RSA4096 加密/解密 工具
echo ===============================
echo 当前目录：%WORK_DIR%
echo 公钥目录：%PUBLIC_DIR%
echo 私钥目录：%PRIVATE_DIR%
echo 1. 加密文本 (Base64 输出)
echo 2. 解密文本 (Base64 输入)
echo 3. 加密文件
echo 4. 解密文件
echo 5. 查看/复制公钥内容
echo 6. 生成新密钥对 (带密码)
(echo 7. 打开项目文件夹)
echo 0. 退出
echo.
set /p choice=请选择操作 [0-6]: 
if "%choice%"=="1" goto encrypt_text
if "%choice%"=="2" goto decrypt_text
if "%choice%"=="3" goto encrypt_file
if "%choice%"=="4" goto decrypt_file
if "%choice%"=="5" goto list_public_keys
if "%choice%"=="6" goto gen_keys
if "%choice%"=="7" goto explorer
if "%choice%"=="0" goto end
echo 无效选择，请重试。
pause
goto menu

:list_public_keys
cls
echo 请选择要使用的公钥文件 (仅输入文件名，可按TAB补全)：
cd %PUBLIC_DIR%
dir /b "%PUBLIC_DIR%"\*.key
set /p pubkey=文件名: 
set "PUBLIC_KEY=%PUBLIC_DIR%\%pubkey%"
if not exist "%PUBLIC_KEY%" (
    echo 公钥 %PUBLIC_KEY% 不存在，返回主菜单。
    pause
    goto menu
)

echo.
echo 公钥内容如下：
type "%PUBLIC_KEY%"
echo.
set /p copykey=是否复制该公钥到剪贴板？(y/n): 
if /i "!copykey!"=="y" (
    clip < "%PUBLIC_KEY%"
    echo 已复制公钥到剪贴板。
)
pause
goto menu

:encrypt_text
cls
cd %PUBLIC_DIR%
echo 请选择要使用的公钥文件 (仅输入文件名，可按TAB补全)：
dir /b "%PUBLIC_DIR%"\*.key
set /p pubkey=文件名: 
set PUBLIC_KEY=%PUBLIC_DIR%\%pubkey%
if not exist "%PUBLIC_KEY%" (
    echo 公钥 %PUBLIC_KEY% 不存在，返回主菜单。
    pause
    goto menu
)
echo 请输入要加密的文本：
set /p plaintext=
echo !plaintext!>plaintext.txt
echo 正在加密...
openssl rsautl -encrypt -inkey "%PUBLIC_KEY%" -pubin -in plaintext.txt -out ciphertext.bin
echo 转换为 Base64（无换行）...
openssl base64 -in ciphertext.bin -A >ciphertext.b64
echo 加密并 Base64 编码后的结果：
type ciphertext.b64

:: 复制到剪贴板
echo.
set /p copyclip=是否复制结果到剪贴板？(y/n): 
if /i "%copyclip%"=="y" (
    clip < ciphertext.b64
    echo 已复制到剪贴板。
)
del plaintext.txt ciphertext.bin ciphertext.b64
echo.
pause
goto menu

:decrypt_text
cls
cd %PRIVATE_DIR%
echo 请选择要使用的私钥文件 (仅输入文件名，可按TAB补全)：
dir /b "%PRIVATE_DIR%"\*.key
set /p prikey=文件名: 
set PRIVATE_KEY=%PRIVATE_DIR%\%prikey%
if not exist "%PRIVATE_KEY%" (
    echo 私钥 %PRIVATE_KEY% 不存在，返回主菜单。
    pause
    goto menu
)
echo 请输入 Base64 编码的密文：
set /p b64=
echo !b64!>ciphertext.b64
echo 解码 Base64...
openssl base64 -d -in ciphertext.b64 -out ciphertext.bin
echo 解密文本...
echo 请输入私钥密码：
openssl rsautl -decrypt -inkey "%PRIVATE_KEY%" -in ciphertext.bin -out decrypted.txt
echo 解密结果：
type decrypted.txt

:: 复制到剪贴板
echo.
set /p copyclip=是否复制结果到剪贴板？(y/n): 
if /i "%copyclip%"=="y" (
    clip < decrypted.txt
    echo 已复制到剪贴板。
)
del ciphertext.b64 ciphertext.bin decrypted.txt
echo.
pause
goto menu

:encrypt_file
cls
cd %PUBLIC_DIR%
echo 请选择要使用的公钥文件 (仅输入文件名，可按TAB补全)：
dir /b "%PUBLIC_DIR%"\*.key
set /p pubkey=文件名: 
set PUBLIC_KEY=%PUBLIC_DIR%\%pubkey%
if not exist "%PUBLIC_KEY%" (
    echo 公钥 %PUBLIC_KEY% 不存在，返回主菜单。
    pause
    goto menu
)
echo 请输入要加密的文件的完整路径（含扩展名）：
echo 例如：
echo D:\Documents\新建 文本文档.txt
set /p infile=
if not exist "%infile%" (
    echo 文件 %infile% 不存在，返回主菜单。
    pause
    goto menu
)
echo 加密文件中...
openssl rsautl -encrypt -inkey "%PUBLIC_KEY%" -pubin -in "%infile%" -out "%infile%.enc"
echo 文件已加密为 %infile%.enc
pause
goto menu

:decrypt_file
cls
cd %PRIVATE_DIR%
echo 请选择要使用的私钥文件 (仅输入文件名，可按TAB补全)：
dir /b "%PRIVATE_DIR%"\*.key
set /p prikey=文件名: 
set PRIVATE_KEY=%PRIVATE_DIR%\%prikey%
if not exist "%PRIVATE_KEY%" (
    echo 私钥 %PRIVATE_KEY% 不存在，返回主菜单。
    pause
    goto menu
)
echo 请输入要解密的文件的完整路径（.enc 扩展名）：
echo 例如：
echo D:\Documents\新建 文本文档.txt.enc
set /p encfile=
if not exist "%encfile%" (
    echo 文件 %encfile% 不存在，返回主菜单。
    pause
    goto menu
)
set outfile=%encfile:.enc=.dec%
echo 解密文件中...
echo 请输入私钥密码：
openssl rsautl -decrypt -inkey "%PRIVATE_KEY%" -in "%encfile%" -out "%outfile%"
echo 文件已解密为 %outfile%
echo 请手动删除文件后缀名
pause
goto menu

:gen_keys
cls
echo 请输入网名（将用于文件名前缀）：
echo 只能输入英文、数字和下划线
set /p netname=
if "%netname%"=="" (
    echo 错误：名称不能为空！
    pause
    goto gen_keys
)

echo 生成带密码保护的私钥...
echo 在“Enter PEM pass phrase:”出现后输入2次密码：
echo 密码至少4字符以上，且不能包含特殊字符。
openssl genrsa -aes256 -out "%PRIVATE_DIR%\%netname%_rsa_aes_private.key" 4096
if errorlevel 1 (
    echo 错误：生成私钥失败，请检查密码是否符合要求！
    pause
    goto generate_key
)

echo 导出公钥...
echo 请重新输入私钥密码：
openssl rsa -in "%PRIVATE_DIR%\%netname%_rsa_aes_private.key" -pubout -out "%PUBLIC_DIR%\%netname%_rsa_public.key"
if errorlevel 1 (
    echo 错误：导出公钥失败，可能是密码输入错误！
    pause
    goto generate_key
)

echo 已生成密钥对：
echo %PRIVATE_DIR%
(call echo 私钥：%%PRIVATE_DIR%%\%netname%_rsa_aes_private.key)
(call echo 公钥：%%PUBLIC_DIR%%\%netname%_rsa_public.key)
pause
goto menu

:explorer
explorer .
goto menu

:end
echo 已退出。
popd
endlocal
exit /b
