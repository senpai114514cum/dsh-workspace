# 把本目录的全局指令 / 技能 / 自建命令安装到本机（新机器重建用）
param(
  [string]$DshHome = "$env:USERPROFILE\.dsh",
  [string]$ToolsDir = "D:\Tools\bin"
)
Copy-Item (Join-Path $PSScriptRoot "AGENTS.md") (Join-Path $DshHome "AGENTS.md") -Force
New-Item -ItemType Directory -Force (Join-Path $DshHome "skills") | Out-Null
Copy-Item (Join-Path $PSScriptRoot "skills\*") (Join-Path $DshHome "skills") -Recurse -Force
New-Item -ItemType Directory -Force $ToolsDir | Out-Null
Copy-Item (Join-Path $PSScriptRoot "tools\*") $ToolsDir -Force
Write-Host "已安装: $DshHome\AGENTS.md、$DshHome\skills、$ToolsDir"
