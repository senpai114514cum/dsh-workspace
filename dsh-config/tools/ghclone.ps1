<#
.SYNOPSIS
  GitHub 仓库获取：直连优先，失败自动回退 ghproxy.net 镜像或 Gitee 镜像。
.EXAMPLE
  ghclone MeteorNOX/DeepSeek-Balance-Whale-Widget
  ghclone octocat/Hello-World .\hw
  ghclone git/git -Force gitee -NoClone
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)][string]$Repo,
  [Parameter(Position = 1)][string]$Dest,
  [Parameter(Position = 2)][string]$Ref,
  [ValidateSet("auto","direct","mirror","gitee")][string]$Force = "auto",
  [switch]$NoClone
)

function Say($m) { Write-Host "[ghclone] $m" }

if ($Repo -match "^https?://github\.com/([^/]+)/([^/]+?)(\.git)?$") { $Repo = "$($Matches[1])/$($Matches[2])" }
if ($Repo -notmatch "^[^/\s]+/[^/\s]+$") { Write-Host "用法: ghclone <owner/repo> [目标目录] [分支或标签] [-Force auto|direct|mirror|gitee] [-NoClone]"; exit 2 }
$parts = $Repo -split "/"
$owner = $parts[0]; $name = ($parts[1] -replace "\.git$", "")
if (-not $Dest) { $Dest = $name }
$refNote = if ($Ref) { "(ref: $Ref)" } else { "" }

$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git) { $git = "D:\Git\cmd\git.exe" }
if (-not (Test-Path $git)) { Say "git 不在 PATH 上，也未找到 D:\Git\cmd\git.exe"; exit 3 }

$routes = [ordered]@{
  direct = "https://github.com/$owner/$name.git"
  mirror = "https://ghproxy.net/https://github.com/$owner/$name.git"
  gitee  = "https://gitee.com/mirrors/$name.git"
}
if ($Force -eq "auto") { $order = @("direct","mirror","gitee") } else { $order = @($Force) }

Say "仓库 $owner/$name -> $Dest $refNote"
foreach ($r in $order) {
  $url = $routes[$r]
  Say "尝试 $r : $url"
  & $git ls-remote --exit-code $url HEAD *> $null
  if ($LASTEXITCODE -ne 0) { Say "  -> $r 不可用"; continue }
  Say "  -> $r 可用"
  if ($NoClone) { Say "仅探测，不执行克隆"; exit 0 }
  if (Test-Path $Dest) { Say "目标已存在: $Dest"; exit 4 }
  $cloneArgs = @("clone","--depth","1")
  if ($Ref) { $cloneArgs += @("--branch",$Ref) }
  $cloneArgs += @($url,$Dest)
  & $git @cloneArgs
  if ($LASTEXITCODE -eq 0) {
    Say "完成（$r）: $Dest"
    Say ("origin = {0}" -f (& $git -C $Dest remote get-url origin))
    Say ("需要时切回官方地址: git -C {0} remote set-url origin https://github.com/{1}/{2}.git" -f $Dest, $owner, $name)
    exit 0
  }
  Say "  -> 克隆失败，继续下一条路线"
}
Say "所有路线都失败：请确认 VPN/代理（gh-proxy-on），或改用 Gitee 上的同名镜像仓库"
exit 1
