@echo off
setlocal
for %%H in (github.com codeload.github.com raw.githubusercontent.com objects.githubusercontent.com gist.githubusercontent.com) do (
  git config --global "url.https://ghproxy.net/https://%%H/.insteadOf" "https://%%H/"
  echo [gh-mirror] ON  %%H
  )
git config --global --get-regexp "^url\."
exit /b 0
