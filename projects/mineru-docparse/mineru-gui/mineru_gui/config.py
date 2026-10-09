"""设置项、MinerU 路径自动探测与持久化。

扩展方式：在 Settings 里加字段即可，UI 与 runner 会自动带上；
不想改代码的临时参数可以放进 Settings.extra。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = APP_DIR / 'settings.json'
LOG_DIR = APP_DIR / 'logs'

# ---------------------------------------------------------------- 常量

TIERS = ['standard', 'advanced', 'flash', 'basic']
TIER_LABEL = {
    'standard': 'standard —— 标准（推荐默认）',
    'advanced': 'advanced —— 高级（务必关图像分析）',
    'flash':    'flash —— 极速（不跑模型，公式会丢）',
    'basic':    'basic —— 基础（无 VLM）',
}

OCR_MODES = ['auto', 'txt', 'ocr']
OCR_LABEL = {
    'auto': 'auto —— 自动判断（默认）',
    'txt':  'txt —— 只用文字层（有文字层的 PDF 首选，零 OCR 误识）',
    'ocr':  'ocr —— 强制 OCR（扫描件必须）',
}

# ---------------------------------------------------------------- 输入类型
# 与 mineru/filetypes.py 严格对齐（照着装的包抄的，不要凭印象改）
#   TIERED     = 可跑 basic/standard/advanced
#   FLASH_ONLY = 只接受 flash，传别的档位会直接报错
#   注意 .tif 不在支持列表里，只有 .tiff；.txt/.md 等纯文本只有文档库能读，
#   命令行解析不支持（PARSEABLE 不含 TEXT）。
PDF_EXT = {'.pdf'}
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff', '.jp2'}
FLASH_ONLY_EXT = {
    '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.rtf',
    '.odt', '.ods', '.odp',
    '.html', '.htm', '.shtml', '.mhtml', '.mht',
    '.csv', '.tsv', '.epub', '.ofd',
}
TEXT_ONLY_EXT = {'.txt', '.text', '.ftxt', '.md', '.markdown', '.mdx',
                 '.rst', '.tex', '.latex', '.adoc', '.asciidoc'}

TIERED_EXT = PDF_EXT | IMAGE_EXT
SUPPORTED_EXT = TIERED_EXT | FLASH_ONLY_EXT      # mineru-kit parse 能处理的
ALL_KNOWN_EXT = SUPPORTED_EXT | TEXT_ONLY_EXT    # 加上只能入库的纯文本


def effective_tier(path, tier: str) -> str:
    """某个文件实际该用的档位。

    flash-only 格式（Office/HTML/EPUB/CSV/ODT/OFD/RTF）只能用 flash，
    传别的档位 MinerU 会报 "Tier 'standard' is only supported for PDF and
    image files" 并直接失败。等价于 MinerU 的 batch_effective_parse_tier()。
    """
    from pathlib import Path as _P
    return 'flash' if _P(str(path)).suffix.lower() in FLASH_ONLY_EXT else tier


def reject_reason(path) -> str | None:
    """文件为什么不能被解析；能解析则返回 None。"""
    from pathlib import Path as _P
    ext = _P(str(path)).suffix.lower()
    if ext in SUPPORTED_EXT:
        return None
    if ext in TEXT_ONLY_EXT:
        return '纯文本（%s）只支持文档库读取，命令行解析不支持' % ext
    return '不支持的扩展名：%s' % (ext or '(无)')


# ---------------------------------------------------------------- 路径探测


def _first_existing(paths) -> Path | None:
    for p in paths:
        if p and Path(p).exists():
            return Path(p)
    return None


# MinerU 部署根目录的默认值。用环境变量 MINERU_ROOT 覆盖即可，
# 例如把 MinerU 装在 E:\AI\MinerU 就设 MINERU_ROOT=E:\AI\MinerU。
# 这里保留一个默认值只是为了开箱即用，不依赖任何机器专属信息。
DEFAULT_MINERU_ROOT = Path(os.environ.get('MINERU_ROOT') or r'%MINERU_ROOT%')


def detect_mineru_home() -> Path:
    """找 MINERU_HOME：环境变量 > 部署目录 > 默认位置。"""
    env = os.environ.get('MINERU_HOME')
    if env and Path(env).exists():
        return Path(env)
    found = _first_existing([
        DEFAULT_MINERU_ROOT / 'home',
        Path.home() / '.mineru',
    ])
    return found if found else Path.home() / '.mineru'


def detect_mineru_kit() -> Path | None:
    """找 mineru-kit 可执行文件。"""
    env = os.environ.get('MINERU_KIT')
    if env and Path(env).exists():
        return Path(env)
    cands = [DEFAULT_MINERU_ROOT / '.venv' / 'Scripts' / 'mineru-kit.exe']
    which = shutil.which('mineru-kit')
    if which:
        cands.insert(0, which)
    # 退而求其次：在 MINERU_HOME 的同级找 .venv
    home = detect_mineru_home()
    cands.append(home.parent / '.venv' / 'Scripts' / 'mineru-kit.exe')
    return _first_existing(cands)


def detect_venv_python() -> Path | None:
    """找 MinerU 环境的 python（体检需要 pypdf）。"""
    return _first_existing([
        DEFAULT_MINERU_ROOT / '.venv' / 'Scripts' / 'python.exe',
        Path(sys.executable),
    ])


# ---------------------------------------------------------------- 设置


@dataclass
class Settings:
    # 输出
    output_dir: str = ''
    skip_existing: bool = True

    # 解析参数
    tier: str = 'standard'
    ocr_mode: str = 'auto'
    disable_image_analysis: bool = True   # advanced 档的消幻觉开关，默认开

    # 解析后处理（消幻觉流水线）
    auto_check: bool = True               # 自动体检
    auto_fix: bool = True                 # 自动清理 details/mermaid + 修公式空格
    extract_images: bool = True           # 把内联 base64 图片抽成独立文件

    # 环境
    mineru_kit: str = ''
    mineru_home: str = ''
    per_file_timeout_sec: int = 1800      # 单个文件超时（秒），防止卡死

    # 预留：以后加的功能只管往里塞，不用改文件格式
    extra: dict = field(default_factory=dict)

    # ---------------- 持久化 ----------------

    @classmethod
    def load(cls) -> 'Settings':
        s = cls()
        if SETTINGS_PATH.exists():
            try:
                raw = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
                for k, v in raw.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
                    else:
                        s.extra[k] = v      # 旧版本遗留字段不丢
            except Exception:
                pass
        # 自动补全未设置的路径
        if not s.mineru_kit:
            p = detect_mineru_kit()
            s.mineru_kit = str(p) if p else ''
        if not s.mineru_home:
            s.mineru_home = str(detect_mineru_home())
        if not s.output_dir:
            s.output_dir = str(Path.home() / 'Documents' / 'MinerU输出')
        return s

    def save(self) -> None:
        try:
            SETTINGS_PATH.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding='utf-8')
        except Exception:
            pass

    # ---------------- 校验 ----------------

    def validate(self) -> list[str]:
        errs = []
        kit = Path(self.mineru_kit) if self.mineru_kit else None
        if not kit or not kit.exists():
            errs.append('找不到 mineru-kit，请在设置里指定，或先运行 deploy-mineru-gpu.ps1 完成部署')
        if self.tier not in TIERS:
            errs.append('未知档位：%s' % self.tier)
        if self.ocr_mode not in OCR_MODES:
            errs.append('未知 OCR 模式：%s' % self.ocr_mode)
        if self.tier == 'advanced' and not self.disable_image_analysis:
            errs.append('advanced 档未关闭图像分析 —— 实测会编造表格，强烈建议勾选"禁用图像分析"')
        return errs

    def build_env(self) -> dict:
        env = os.environ.copy()
        env['MINERU_HOME'] = self.mineru_home
        env.setdefault('MINERU_MODEL_SOURCE', 'modelscope')
        env.setdefault('MINERU_MODEL_SMALL_BACKEND', 'torch')
        env.setdefault('MINERU_MODEL_VLM_ENGINE', 'lmdeploy')
        env.setdefault('HF_HUB_DISABLE_XET', '1')
        env['PYTHONIOENCODING'] = 'utf-8'
        return env
