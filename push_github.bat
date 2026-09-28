@echo off
chcp 936 >nul
setlocal

set REPO=https://github.com/radix-angelicae/PhigrosSaveEditor.git
set BRANCH=main
rem ---- 代理设置（按你的环境填；不需要代理就设为空） ----
set PROXY=http://127.0.0.1:10808

echo ==========================================
echo   PhigrosSaveEditor  -  Force Push to GitHub
echo ==========================================
echo.

cd /d "%~dp0"

rem ---- [1/9] 检查 git ----
where git >nul 2>nul
if errorlevel 1 (
    echo [错误] 找不到 git，请先安装 Git for Windows:
    echo        https://git-scm.com/download/win
    goto :fail
)
for /f "tokens=3" %%v in ('git --version') do set GITVER=%%v
echo [1/9] git 版本: %GITVER%

rem ---- [2/9] 清理构建产物与缓存 ----
echo [2/9] 清理构建产物与缓存 ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist .venv_build rmdir /s /q .venv_build
for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
del /s /q *.pyc >nul 2>nul

rem ---- [3/9] 初始化仓库 ----
if not exist .git (
    echo [3/9] 初始化 git 仓库 ...
    git init -b %BRANCH%
    if errorlevel 1 goto :fail
) else (
    echo [3/9] 已存在 git 仓库
)

rem ---- [4/9] 用户信息 ----
echo [4/9] 检查 git 用户配置 ...
git config user.name >nul 2>nul
if errorlevel 1 (
    set /p UNAME=请输入 git 用户名: 
    git config user.name "%UNAME%"
) else (
    for /f "delims=" %%n in ('git config user.name') do echo       用户名: %%n
)
git config user.email >nul 2>nul
if errorlevel 1 (
    set /p UMAIL=请输入 git 邮箱: 
    git config user.email "%UMAIL%"
) else (
    for /f "delims=" %%e in ('git config user.email') do echo       邮箱: %%e
)

rem ---- [5/9] 远端 ----
echo [5/9] 远端: %REPO%
git remote remove origin >nul 2>nul
git remote add origin %REPO%
if errorlevel 1 goto :fail

rem ---- [6/9] 暂存（按 .gitignore 重新整理，剔除无关文件） ----
echo [6/9] 暂存文件 ...
git rm -r --cached . -q >nul 2>nul
git add -A
if errorlevel 1 goto :fail
echo       本次将提交:
git diff --cached --name-only
echo.

rem ---- [7/9] 代理连通性检查 ----
if "%PROXY%"=="" goto :noproxy
echo [7/9] 代理: %PROXY%
where curl >nul 2>nul
if errorlevel 1 goto :nocurl
curl -s -o nul -w "%{http_code}" --max-time 10 -x %PROXY% https://github.com > "%TEMP%\_ghcode.txt" 2>nul
set /p GHCODE=<"%TEMP%\_ghcode.txt"
del "%TEMP%\_ghcode.txt" >nul 2>nul
if "%GHCODE%"=="" echo       [警告] 代理无响应，请确认代理软件已开启（端口 10808）
if not "%GHCODE%"=="" if not "%GHCODE%"=="200" echo       [警告] 返回码 %GHCODE%，代理可能未放行 github.com
if "%GHCODE%"=="200" echo       代理连通正常
goto :proxyok
:nocurl
echo       （未安装 curl，跳过连通性检查）
goto :proxyok
:noproxy
echo [7/9] 未配置代理，直连
:proxyok

rem ---- [8/9] 确认 ----
if /i "%1"=="/y" goto :noconfirm
echo [!] 即将强制推送到 %REPO%
echo     远端 %BRANCH% 分支历史将被完全覆盖，不可恢复。
set /p ANS=输入 Y 继续，其它任意键取消: 
if /i not "%ANS%"=="Y" goto :cancel
:noconfirm

echo [8/9] 提交（含 [skip ci]，不触发 GitHub Actions）...
git commit -m "Update PhigrosSaveEditor [skip ci]"
if errorlevel 1 echo       （没有新改动，直接推送）
if exist .github\workflows (
    echo       [提示] 检测到 .github\workflows，已用 [skip ci] 跳过本次构建
)

rem ---- [9/9] 强推 ----
echo [9/9] 强制推送到 %BRANCH% ...
if "%PROXY%"=="" git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 push -f -u origin %BRANCH%
if not "%PROXY%"=="" git -c http.proxy=%PROXY% -c https.proxy=%PROXY% -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 push -f -u origin %BRANCH%
if errorlevel 1 goto :retry
goto :ok

:retry
echo.
echo [!] 带代理推送失败，尝试直连 ...
git -c http.proxy= -c https.proxy= -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 push -f -u origin %BRANCH%
if errorlevel 1 goto :fail
goto :ok

:ok
echo.
echo ==========================================
echo   推送成功！
echo   https://github.com/radix-angelicae/PhigrosSaveEditor
echo ==========================================
goto :end

:fail
echo.
echo [失败] 推送未成功，请看上面的错误信息。
echo 排查建议：
echo   1) 代理 —— 确认代理软件已开启且端口是 10808；可修改本脚本开头的 PROXY
echo   2) 认证 —— GitHub 已不支持密码，请用 Personal Access Token（勾选 repo）
echo      或: winget install GitHub.cli  然后 gh auth login
echo   3) 仓库 —— 确认仓库已存在且你有写权限
echo   4) 可先手动测试: curl -x %PROXY% -I https://github.com
goto :end

:cancel
echo.
echo 已取消，未做任何推送。
goto :end

:end
echo.
pause
