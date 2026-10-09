# ============================================================
# 在桌面创建 MinerU 批量转换器的快捷方式（可重复执行）
#
#   powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1
#
# 为什么不用 venv 里的 pythonw.exe：
#   uv 建的 venv 中，Scripts\pythonw.exe 是「引导器」（247KB），它实际会启动
#   控制台版 python.exe，双击时多一个黑框（实测是新建的独立控制台）。
#   基础 Python 的 pythonw.exe 才是真正的无控制台解释器，所以快捷方式指向它，
#   由 run.py 的 ensure_venv_packages() 把 venv 的包挂进来。
#
# 如果 MinerU 环境或本工程挪了位置，改参数重跑一次即可。
# ============================================================
param(
    [string]$Venv   = '%MINERU_ROOT%\.venv',
    [string]$AppDir = '%WORKSPACE%\mineru-gui',
    [string]$Name   = 'MinerU 批量转换器'
)

$ErrorActionPreference = 'Stop'

function Resolve-PythonW {
    param([string]$VenvDir)
    # 1) 优先：从 pyvenv.cfg 的 home 找基础 Python 的 pythonw.exe（无控制台）
    $cfg = Join-Path $VenvDir 'pyvenv.cfg'
    if (Test-Path $cfg) {
        $line = Get-Content $cfg | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
        if ($line) {
            # 注意：不能用 $home，它是 PowerShell 只读自动变量
            $baseDir = ($line -replace '^\s*home\s*=\s*', '').Trim()
            $p = Join-Path $baseDir 'pythonw.exe'
            if (Test-Path $p) { return $p }
        }
    }
    # 2) 退路：venv 自己的 pythonw.exe（能跑，但会多一个控制台黑框）
    $p2 = Join-Path $VenvDir 'Scripts\pythonw.exe'
    if (Test-Path $p2) { Write-Warning '用的 venv 自带 pythonw.exe，启动时会多一个黑框'; return $p2 }
    throw "找不到可用的 pythonw.exe（venv: $VenvDir）"
}

$pythonw = Resolve-PythonW -VenvDir $Venv
$runPy   = Join-Path $AppDir 'run.py'
$icon    = Join-Path $AppDir 'assets\icon.ico'

foreach ($p in @($pythonw, $runPy)) {
    if (-not (Test-Path $p)) { throw "找不到：$p`n请先确认 MinerU 已部署、且本工程路径正确。" }
}

$desktop = [Environment]::GetFolderPath('Desktop')
if (-not (Test-Path $desktop)) { throw "找不到桌面目录：$desktop" }
$lnkPath = Join-Path $desktop ($Name + '.lnk')

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath       = $pythonw
$lnk.Arguments        = '"' + $runPy + '"'
$lnk.WorkingDirectory = $AppDir
$lnk.Description      = 'MinerU 批量转换器 —— 批量把 PDF / 图片 / Office 文档转成 Markdown'
if (Test-Path $icon) { $lnk.IconLocation = $icon + ',0' }
$lnk.Save()
[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)

# ---------- 回读校验 ----------
$check = New-Object -ComObject WScript.Shell
$v = $check.CreateShortcut($lnkPath)
Write-Host '快捷方式已创建并校验：'
Write-Host ('  路径      : ' + $lnkPath)
Write-Host ('  目标      : ' + $v.TargetPath)
Write-Host ('  参数      : ' + $v.Arguments)
Write-Host ('  工作目录  : ' + $v.WorkingDirectory)
Write-Host ('  图标      : ' + $v.IconLocation)
Write-Host '  （目标应是基础 Python 的 pythonw.exe，不是 venv 里那个引导器）'
[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($check)
