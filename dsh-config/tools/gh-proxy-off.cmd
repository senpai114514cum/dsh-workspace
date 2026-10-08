@echo off
setlocal
git config --global --unset http.proxy 2>nul
git config --global --unset https.proxy 2>nul
setx HTTP_PROXY "" >nul
setx HTTPS_PROXY "" >nul
echo [gh-proxy] OFF (github will need gh-mirror-on)
exit /b 0
