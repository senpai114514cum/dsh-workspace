@echo off
setlocal
for %%H in (github.com codeload.github.com raw.githubusercontent.com objects.githubusercontent.com gist.githubusercontent.com) do (
  git config --global --unset "url.https://ghproxy.net/https://%%H/.insteadOf" 2>nul
  echo [gh-mirror] OFF %%H
  )
echo done
exit /b 0
