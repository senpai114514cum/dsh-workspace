# ============================================================
# MinerU 4.0 全自动部署（Windows + NVIDIA）—— 最高质量 Markdown 配置
#
# 机器：RTX 3080 Ti 12GB / 驱动 617.42 / Python 3.13
# 用法：powershell -ExecutionPolicy Bypass -File .\deploy-mineru-gpu.ps1
#
# 做的事：
#   1) 装 uv，用 Python 3.13 建独立环境到 D 盘
#   2) 装 mineru[full]（Windows 上 = torch + LMDeploy 全精度 VLM）
#   3) 覆盖安装 CUDA 12.8 版 PyTorch（Windows 上 PyPI 默认是 CPU 版）
#   4) 验证 GPU 真的可用，不通就直接停
#   5) 环境变量持久化（MINERU_HOME 落 D 盘 / 走 ModelScope）
#   6) 下载 standard 档模型（该档同时服务 advanced，无需重复下载）
#   7) 写入 llm_aided 后处理配置段
# ============================================================

param(
    [string]$Root          = '%MINERU_ROOT%',
    [string]$Python313     = '%LOCALAPPDATA%\\Programs\\Python\Python313\python.exe',
    [string]$PipMirror     = 'https://pypi.tuna.tsinghua.edu.cn/simple',
    [string]$TorchMirror   = 'https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/',
    [string]$TorchBackend  = 'cu128',
    [string]$TorchPin      = '2.11.0',
    [string]$TorchVisionPin = '0.26.0',
    [string]$DownloadTier  = 'standard'
)

# PS 5.1 在 Stop 模式下，原生程序写一行 stderr（uv/pip 进度条就会）就会中断脚本
$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

$VENV        = Join-Path $Root '.venv'
$VPY         = Join-Path $VENV 'Scripts\python.exe'
$KIT         = Join-Path $VENV 'Scripts\mineru-kit.exe'
$MINERU_HOME = Join-Path $Root 'home'
$CONFIG      = Join-Path $MINERU_HOME 'config.yaml'
$LOGFILE     = Join-Path $Root 'deploy.log'

$env:UV_CACHE_DIR        = Join-Path $Root 'uvcache'
$env:UV_PYTHON_DOWNLOADS = 'never'
$env:MINERU_HOME         = $MINERU_HOME
$env:MINERU_MODEL_SOURCE = 'modelscope'
$env:HF_HUB_DISABLE_XET  = '1'

function Step($n, $t) { Write-Host "`n=== [$n] $t ===" }
function Ok($m)       { Write-Host "  OK   $m" }
function Info($m)     { Write-Host "  ..   $m" }
function Warn($m)     { Write-Host "  !!   $m" }
function Die($m)      { Write-Host "  XX   $m"; Stop-Transcript | Out-Null; exit 1 }

New-Item -ItemType Directory -Force -Path $Root, $MINERU_HOME | Out-Null
Start-Transcript -Path $LOGFILE -Force | Out-Null

Write-Host "部署根目录：$Root"
Write-Host "日志：$LOGFILE"

# ---------- 0. 环境自检 ----------
Step 0 '环境自检'

$gpu = & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null
if ($LASTEXITCODE -ne 0 -or -not $gpu) { Die 'nvidia-smi 不可用。' }
Ok "GPU: $gpu"

if (-not (Test-Path $Python313)) { Die "找不到 Python 3.13：$Python313" }
Ok "Python: $(& $Python313 -c "import sys;print('.'.join(map(str,sys.version_info[:3])))")"

try {
    $free = [math]::Round(([System.IO.DriveInfo]::new('D')).AvailableFreeSpace / 1GB, 1)
    Ok "D 盘剩余: $free GB"
    if ($free -lt 25) { Warn '空间偏紧，建议 25GB+。' }
} catch { Warn '读不到磁盘空间。' }

# ---------- 1. uv ----------
Step 1 '准备 uv'

function Find-Uv {
    $c = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if ($c) { return $c }
    $cands = @()
    $scripts = (& python -c "import sys,os;print(os.path.join(sys.prefix,'Scripts'))" 2>$null)
    if ($scripts) { $cands += (Join-Path $scripts 'uv.exe') }
    $pipCmd = Get-Command pip -ErrorAction SilentlyContinue
    if ($pipCmd) { $cands += (Join-Path (Split-Path $pipCmd.Source) 'uv.exe') }
    foreach ($cand in $cands) { if ($cand -and (Test-Path $cand)) { return $cand } }
    return $null
}

$UVEXE = Find-Uv
if (-not $UVEXE) {
    Info '通过 pip 安装 uv ...'
    & python -m pip install -U uv -i $PipMirror --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { & pip install -U uv -i $PipMirror --disable-pip-version-check }
    $UVEXE = Find-Uv
}
if (-not $UVEXE) { Die 'uv 不可用。请手动 python -m pip install -U uv 后重跑。' }
# 刚装完的 uv 可能还不在本会话 PATH 里，临时补上
$uvDir = Split-Path $UVEXE
if ($env:PATH -notlike "*$uvDir*") { $env:PATH = "$uvDir;$env:PATH" }
Ok "uv: $(& $UVEXE --version)"

# ---------- 2. 虚拟环境 ----------
Step 2 '创建 Python 3.13 虚拟环境'

if (Test-Path $VPY) {
    Ok "已存在，跳过：$VENV"
} else {
    & $UVEXE venv $VENV --python $Python313
    if ($LASTEXITCODE -ne 0) { Die '创建虚拟环境失败。' }
    Ok "已创建：$VENV"
}

# ---------- 3. mineru[full] ----------
Step 3 '安装 mineru[full]（torch + LMDeploy）'

if (Test-Path $KIT) {
    # 已在环境里就别再 -U 重解析：那会把 torch 换回 PyPI 的 CPU 版，白折腾一轮
    Ok "已安装，跳过：$KIT"
} else {
    & $UVEXE pip install --python $VPY -U 'mineru[full]>=4.0,<5' --index-url $PipMirror
    if ($LASTEXITCODE -ne 0) {
        Warn 'mineru[full] 安装失败，回退为 mineru[torch] + 单独装 LMDeploy ...'
        & $UVEXE pip install --python $VPY -U 'mineru[torch]>=4.0,<5' --index-url $PipMirror
        if ($LASTEXITCODE -ne 0) { Die 'mineru 安装失败，请看日志。' }
        & $UVEXE pip install --python $VPY -U 'lmdeploy>=0.17.0,<0.18' --index-url $PipMirror
        if ($LASTEXITCODE -ne 0) { Warn 'LMDeploy 装不上，VLM 将退回 llama.cpp（量化，精度略低）。' }
    }
    Ok 'mineru 安装完成'
}

# ---------- 4. CUDA 版 torch ----------
# 这一步有四个坑叠在一起，必须一起处理，否则会静默装成 CPU 版：
#   1) Windows 上 PyPI 的 torch 默认是 CPU 版，必须显式换 CUDA 构建
#   2) uv 默认只认「第一个包含该包的索引」，一旦叠加 PyPI 镜像，就永远看不到 cu128 版本
#      （实测栽在这：拿到了版本号更高的 2.14.1+cpu，且 exit code 是 0，不报错）
#      -> 用「精确版本号」+ --index-strategy unsafe-best-match 绕开
#   3) download.pytorch.org 的轮子 CDN（download-r2）在本机被重置，装不上
#      -> 换 SJTU 的 PyTorch 镜像（标准 PEP503 索引；阿里云那个是目录列表，uv 不认）
#   4) LMDeploy 0.17.0 按 CUDA 12.8 编译，torch 必须同为 cu128，否则 ABI 不匹配
Step 4 "安装 CUDA 版 PyTorch（$TorchBackend @ SJTU 镜像）"

& $UVEXE pip install --python $VPY `
    --index-url $TorchMirror --extra-index-url $PipMirror --index-strategy unsafe-best-match `
    --reinstall-package torch --reinstall-package torchvision `
    "torch==$TorchPin+$TorchBackend" "torchvision==$TorchVisionPin+$TorchBackend"
if ($LASTEXITCODE -ne 0) {
    Warn '精确版本装不上，改为取该镜像上最新的 cu128 版本 ...'
    & $UVEXE pip install --python $VPY `
        --index-url $TorchMirror --extra-index-url $PipMirror --index-strategy unsafe-best-match `
        --reinstall-package torch --reinstall-package torchvision torch torchvision
}
if ($LASTEXITCODE -ne 0) {
    Warn 'SJTU 镜像失败，回退 uv 内置 --torch-backend ...'
    & $UVEXE pip install --python $VPY --torch-backend=$TorchBackend `
        --reinstall-package torch --reinstall-package torchvision `
        --index-url $PipMirror torch torchvision
}
if ($LASTEXITCODE -ne 0) { Die 'CUDA 版 torch 安装失败。' }
Ok 'torch(CUDA) 安装完成'

# ---------- 5. 验证 GPU ----------
Step 5 '验证 PyTorch 能用 GPU'

$check = & $VPY -c @"
import torch
print('torch     :', torch.__version__)
print('cuda ver  :', torch.version.cuda)
print('avail     :', torch.cuda.is_available())
print('device    :', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')
print('compute   :', torch.cuda.get_device_capability(0) if torch.cuda.is_available() else 'N/A')
print('vram GB   :', round(torch.cuda.get_device_properties(0).total_memory/1024**3,1) if torch.cuda.is_available() else 'N/A')
"@
$check | ForEach-Object { Info $_ }
if (($check -join "`n") -notmatch 'avail\s+:\s+True') { Die 'PyTorch 看不到 GPU。' }
# CUDA 大版本必须和 LMDeploy 的 12.8 对齐，否则 lmdeploy 加载会失败
$cuv = ($check | Select-String 'cuda ver\s+:\s+(\S+)').Matches.Groups[1].Value
if ($cuv -notlike '12.8*') {
    Warn "torch 的 CUDA 是 $cuv，而 LMDeploy 0.17.0 按 CUDA 12.8 编译 —— 可能 ABI 不匹配。"
} else {
    Ok "CUDA 版本与 LMDeploy 对齐（$cuv）"
}
Ok 'GPU 可用'

# ---------- 6. 环境变量持久化 ----------
Step 6 '写入用户级环境变量'

$envs = [ordered]@{
    MINERU_HOME                = $MINERU_HOME
    MINERU_MODEL_SOURCE        = 'modelscope'
    MINERU_MODEL_SMALL_BACKEND = 'torch'
    MINERU_MODEL_VLM_ENGINE    = 'lmdeploy'
    HF_HUB_DISABLE_XET         = '1'
}
foreach ($k in $envs.Keys) {
    [Environment]::SetEnvironmentVariable($k, $envs[$k], 'User')
    Set-Item -Path "env:$k" -Value $envs[$k]
    Ok "$k = $($envs[$k])"
}

# ---------- 7. 下载并校验模型 ----------
Step 7 "下载 $DownloadTier 档模型（同时服务 advanced）"

& $KIT models download --tier $DownloadTier --small-backend torch --vlm-engine lmdeploy --source modelscope
if ($LASTEXITCODE -ne 0) { Warn '模型下载返回非 0，继续尝试校验（可能已下完）。' }
& $KIT models verify --tier $DownloadTier --small-backend torch --vlm-engine lmdeploy
Info '--- 生效的后端 / 引擎 ---'
& $KIT models show

# ---------- 8. llm_aided 后处理配置 ----------
Step 8 '写入 llm_aided 后处理配置段'

$block = @'


# ===== 最高质量 Markdown 后处理（默认关闭；需要 OpenAI 兼容的 LLM 服务）=====
# 打开后：title_leveling 把段落标题归入 H2~H6；cross_page_table_cell_merge 让 LLM
# 判断跨页表格的边界行是否连续。两者都要求 api_key / base_url / model 三者非空。
# 注意：title_leveling 只在「整篇解析」时生效，指定页码范围会被跳过。
llm_aided:
  api_key: ${MINERU_LLM_API_KEY:-}
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  model: qwen3.5-plus
  enable_thinking: false
  max_concurrency: 16
  features:
    title_leveling: false
    cross_page_table_cell_merge: false
'@

if (-not (Test-Path $CONFIG)) {
    Set-Content -Path $CONFIG -Value $block.TrimStart("`r", "`n") -Encoding UTF8
    Ok "已创建并写入：$CONFIG"
} elseif ((Get-Content -Raw $CONFIG) -match 'llm_aided\s*:') {
    Ok "已存在 llm_aided 段，跳过：$CONFIG"
} else {
    Add-Content -Path $CONFIG -Value $block -Encoding UTF8
    Ok "已追加 llm_aided 段：$CONFIG"
}

# ---------- 完成 ----------
Step 9 '部署完成'
& $VPY -c "import mineru;print('mineru', getattr(mineru,'__version__','?'))" 2>$null
Write-Host @"

环境      : $VENV
模型/配置 : $MINERU_HOME
日志      : $LOGFILE

最高质量转换命令：
  & '$VENV\Scripts\Activate.ps1'
  mineru-kit parse 'D:\某文件.pdf' -o 'D:\某文件.md' --tier advanced
"@

Stop-Transcript | Out-Null
