@echo off
:: RSA4096 Encryption/Decryption Tool (Supports UTF-8, Base64 interactions, key selection, and one-click key pair generation)

chcp 65001 >nul
setlocal enabledelayedexpansion

:: Check if OpenSSL is installed
where openssl >nul 2>&1
if errorlevel 1 (
    echo OpenSSL not detected. You can download and install it from https://slproweb.com/products/Win32OpenSSL.html and try again.
    pause
    exit /b
)

:: Automatically get the directory of the batch script as the working directory
set "WORK_DIR=%~dp0"
set "WORK_DIR=%WORK_DIR:~0,-1%"

:: Automatically create private and public key directories
set PRIVATE_DIR=%WORK_DIR%\private_keys
set PUBLIC_DIR=%WORK_DIR%\public_keys
if not exist "%PRIVATE_DIR%" mkdir "%PRIVATE_DIR%"
if not exist "%PUBLIC_DIR%" mkdir "%PUBLIC_DIR%"

:menu
cls
cd %WORK_DIR%
echo.
echo ===============================
echo   RSA4096 Encryption/Decryption Tool
echo ===============================
echo Current directory: %WORK_DIR%
echo 1. Encrypt text (Base64 output)
echo 2. Decrypt text (Base64 input)
echo 3. Encrypt file
echo 4. Decrypt file
echo 5. View/Copy public key content
echo 6. Generate new key pair (with password)
echo 0. Exit
echo.
set /p choice=Please select an option [0-6]: 
if "%choice%"=="1" goto encrypt_text
if "%choice%"=="2" goto decrypt_text
if "%choice%"=="3" goto encrypt_file
if "%choice%"=="4" goto decrypt_file
if "%choice%"=="5" goto list_public_keys
if "%choice%"=="6" goto gen_keys
if "%choice%"=="0" goto end
echo Invalid selection, please try again.
pause
goto menu

:list_public_keys
cls
echo Please select the public key file to use (only enter the file name, TAB completion is supported):
cd %PUBLIC_DIR%
dir /b "%PUBLIC_DIR%"\*.key
set /p pubkey=Filename: 
set "PUBLIC_KEY=%PUBLIC_DIR%\%pubkey%"
if not exist "%PUBLIC_KEY%" (
    echo Public key %PUBLIC_KEY% does not exist, returning to main menu.
    pause
    goto menu
)

echo.
echo Public key content:
type "%PUBLIC_KEY%"
echo.
set /p copykey=Copy this public key to clipboard? (y/n): 
if /i "!copykey!"=="y" (
    clip < "%PUBLIC_KEY%"
    echo Public key copied to clipboard.
)
pause
goto menu

:encrypt_text
cls
cd %PUBLIC_DIR%
echo Please select the public key file to use (only enter the file name, TAB completion is supported):
dir /b "%PUBLIC_DIR%"\*.key
set /p pubkey=Filename: 
set PUBLIC_KEY=%PUBLIC_DIR%\%pubkey%
if not exist "%PUBLIC_KEY%" (
    echo Public key %PUBLIC_KEY% does not exist, returning to main menu.
    pause
    goto menu
)
echo Please enter the text to encrypt:
set /p plaintext=
echo !plaintext!>plaintext.txt
echo Encrypting...
openssl rsautl -encrypt -inkey "%PUBLIC_KEY%" -pubin -in plaintext.txt -out ciphertext.bin
echo Converting to Base64 (no line breaks)...
openssl base64 -in ciphertext.bin -A >ciphertext.b64
echo Encrypted and Base64 encoded result:
type ciphertext.b64

:: Copy to clipboard
echo.
set /p copyclip=Copy result to clipboard? (y/n): 
if /i "%copyclip%"=="y" (
    clip < ciphertext.b64
    echo Copied to clipboard.
)
del plaintext.txt ciphertext.bin ciphertext.b64
echo.
pause
goto menu

:decrypt_text
cls
cd %PRIVATE_DIR%
echo Please select the private key file to use (only enter the file name, TAB completion is supported):
dir /b "%PRIVATE_DIR%"\*.key
set /p prikey=Filename: 
set PRIVATE_KEY=%PRIVATE_DIR%\%prikey%
if not exist "%PRIVATE_KEY%" (
    echo Private key %PRIVATE_KEY% does not exist, returning to main menu.
    pause
    goto menu
)
echo Please enter the Base64 encoded ciphertext:
set /p b64=
echo !b64!>ciphertext.b64
echo Decoding Base64...
openssl base64 -d -in ciphertext.b64 -out ciphertext.bin
echo Decrypting text...
echo Please enter private key password:
openssl rsautl -decrypt -inkey "%PRIVATE_KEY%" -in ciphertext.bin -out decrypted.txt
echo Decryption result:
type decrypted.txt

:: Copy to clipboard
echo.
set /p copyclip=Copy result to clipboard? (y/n): 
if /i "%copyclip%"=="y" (
    clip < decrypted.txt
    echo Copied to clipboard.
)
del ciphertext.b64 ciphertext.bin decrypted.txt
echo.
pause
goto menu

:encrypt_file
cls
cd %PUBLIC_DIR%
echo Please select the public key file to use (only enter the file name, TAB completion is supported):
dir /b "%PUBLIC_DIR%"\*.key
set /p pubkey=Filename: 
set PUBLIC_KEY=%PUBLIC_DIR%\%pubkey%
if not exist "%PUBLIC_KEY%" (
    echo Public key %PUBLIC_KEY% does not exist, returning to main menu.
    pause
    goto menu
)
echo Enter the full path of the file to encrypt (with extension):
echo Example:
echo D:\Documents\New Text Document.txt
set /p infile=
if not exist "%infile%" (
    echo File %infile% does not exist, returning to main menu.
    pause
    goto menu
)
echo Encrypting file...
openssl rsautl -encrypt -inkey "%PUBLIC_KEY%" -pubin -in "%infile%" -out "%infile%.enc"
echo File encrypted as %infile%.enc
pause
goto menu

:decrypt_file
cls
cd %PRIVATE_DIR%
echo Please select the private key file to use (only enter the file name, TAB completion is supported):
dir /b "%PRIVATE_DIR%"\*.key
set /p prikey=Filename: 
set PRIVATE_KEY=%PRIVATE_DIR%\%prikey%
if not exist "%PRIVATE_KEY%" (
    echo Private key %PRIVATE_KEY% does not exist, returning to main menu.
    pause
    goto menu
)
echo Enter the full path of the file to decrypt (.enc extension):
echo Example:
echo D:\Documents\New Text Document.txt.enc
set /p encfile=
if not exist "%encfile%" (
    echo File %encfile% does not exist, returning to main menu.
    pause
    goto menu
)
set outfile=%encfile:.enc=.dec%
echo Decrypting file...
echo Please enter private key password:
openssl rsautl -decrypt -inkey "%PRIVATE_KEY%" -in "%encfile%" -out "%outfile%"
echo File decrypted as %outfile%
echo Please manually remove the file extension
pause
goto menu

:gen_keys
cls
echo Please enter a username (used as filename prefix):
echo Only English letters, numbers, and underscores are allowed
set /p netname=
if "%netname%"=="" (
    echo Error: Name cannot be empty!
    pause
    goto gen_keys
)

echo Generating password-protected private key...
echo When "Enter PEM pass phrase:" appears, input the password twice:
echo Password must be at least 4 characters, and cannot contain special characters.
openssl genrsa -aes256 -out "%PRIVATE_DIR%\%netname%_rsa_aes_private.key" 4096
if errorlevel 1 (
    echo Error: Failed to generate private key. Please check if the password meets requirements!
    pause
    goto generate_key
)

echo Exporting public key...
echo Please re-enter private key password:
openssl rsa -in "%PRIVATE_DIR%\%netname%_rsa_aes_private.key" -pubout -out "%PUBLIC_DIR%\%netname%_rsa_public.key"
if errorlevel 1 (
    echo Error: Failed to export public key, possibly due to incorrect password!
    pause
    goto generate_key
)

echo Key pair generated:
echo %PRIVATE_DIR%
(call echo Private key: %%PRIVATE_DIR%%\%netname%_rsa_aes_private.key)
(call echo Public key: %%PUBLIC_DIR%%\%netname%_rsa_public.key)
pause
goto menu

:end
echo Exited.
endlocal
exit /b
