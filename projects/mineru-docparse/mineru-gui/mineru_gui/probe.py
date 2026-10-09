"""输入文件探测：页数，以及 `--ocr-mode auto` 会判定成什么。

判定逻辑**直接复用 MinerU 自己用的那个函数**（docvortex 的
`PDFDocument.classify()`），只是提前调用一次把结果显示出来，
不改变 MinerU 的任何行为。

注意：这个模块的所有函数失败时都返回 None 而不是抛异常 ——
探测只是锦上添花，不能因为探测失败就挡住转换。
"""
from __future__ import annotations

from pathlib import Path

from .config import FLASH_ONLY_EXT, IMAGE_EXT, TIERED_EXT


def page_count(path: Path) -> int | None:
    """PDF 页数；非 PDF 或读取失败返回 None。"""
    if path.suffix.lower() != '.pdf':
        return None
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def classify_ocr_mode(path: Path) -> str | None:
    """预测 `--ocr-mode auto` 的结果：'txt' 或 'ocr'。

    非 PDF/图片、或环境里没有 docvortex 时返回 None。
    图片会先被包成单页 PDF —— 和 MinerU 内部的处理完全一致。
    """
    try:
        from docvortex.document.pdf import PDFDocument
    except Exception:
        return None

    suffix = path.suffix.lower()
    if suffix not in TIERED_EXT:
        return None                     # flash-only 或纯文本：auto 不适用
    try:
        data = path.read_bytes()
        if suffix in IMAGE_EXT:
            # MinerU 内部就是这么做的：mineru_parser.py:169
            data = PDFDocument.from_image(data).bytes
        with PDFDocument(data) as doc:
            return doc.classify()
    except Exception:
        return None


def describe(path: Path) -> str:
    """给日志用的一句话说明。"""
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXT:
        return '图片输入，将被包成单页 PDF'
    if suffix in FLASH_ONLY_EXT:
        return '%s 格式只支持 flash 档，OCR 模式不生效' % suffix.lstrip('.')
    mode = classify_ocr_mode(path)
    if mode is None:
        return '非 PDF/图片，OCR 模式不适用'
    return 'auto 判定：%s' % mode
