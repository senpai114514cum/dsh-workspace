@echo off
setlocal
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
setx HTTP_PROXY http://127.0.0.1:7890 >nul
setx HTTPS_PROXY http://127.0.0.1:7890 >nul
echo [gh-proxy] ON  git/curl -> http://127.0.0.1:7890
git config --global --get http.proxy
exit /b 0
