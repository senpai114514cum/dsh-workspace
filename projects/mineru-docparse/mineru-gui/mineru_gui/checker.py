"""输出体检与清理（消幻觉）。

设计成「只依赖文件路径」的纯函数，方便：
  * 被 runner 的流水线调用
  * 单独命令行调用
  * 以后加新的检查项（往 _RULES 里加函数即可）
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SEP = re.compile(r'^\s*\|[\s:\-\|]+\|\s*$')
# MinerU 会**混用**两种表格格式：markdown 竖线表 + HTML <table>。
# 只数竖线表会系统性漏计，实测把 4 个表数成 2 个，进而误报"表格数少于原文"。
HTML_TABLE = re.compile(r'<table\b.*?</table>', re.S | re.I)
CAP_CN = re.compile(r'表\s*(\d+(?:\.\d+)*|[一二三四五六七八九十]+)')
# IEEE 等期刊大量使用罗马数字编号（TABLE I / Table II）；
# 学位论文/技术报告常用分节编号（Table 3.1 / Table 3.2），必须保留小数部分，
# 否则 3.1 和 3.2 会被归并成同一个标题而少算。
CAP_EN = re.compile(r'\bTables?\s+(\d+(?:\.\d+)*|[IVXLCDM]+)\b', re.I)
TQDM_PCT = re.compile(r'(\d{1,3})%\|')
# 交错重复：每个字符原地出现两次，连续 4 组以上。例如 "3×3, 64" → "33××33,, 6644"
# 两个限制缺一不可：
#   1. 排除空白 —— 否则 8 个空格（缩进）会被误判
#   2. 至少 3 种不同字符 —— 否则 "--------" 这类分隔线会被误判
INTERLEAVE_RUN = re.compile(r'(?:([^\s])\1){4,}')
TILDE_VAL = re.compile(r'^~\s*[-+]?\d|^~\s*\d*\^')


def count_interleave(text: str) -> int:
    n = 0
    for m in INTERLEAVE_RUN.finditer(text):
        if len(set(m.group(0))) >= 3:
            n += 1
    return n

_ROMAN = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
_CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
           '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


def label_key(tok: str) -> str:
    """把表格编号统一成阿拉伯数字字符串，便于跨写法去重与比较。

    'Table 1' / 'Table I' / '表一' → '1'
    """
    tok = tok.strip()
    if tok.isdigit():
        return str(int(tok))
    if re.fullmatch(r'\d+(?:\.\d+)+', tok):          # 分节编号 3.1 / 3.2.1 原样保留
        return tok
    upper = tok.upper()
    if upper and all(c in _ROMAN for c in upper):
        total, prev = 0, 0
        for c in reversed(upper):
            v = _ROMAN[c]
            total += v if v >= prev else -v
            prev = max(prev, v)
        return str(total)
    if tok and all(c in _CN_NUM for c in tok):
        if tok == '十':
            return '10'
        if '十' in tok:                     # 十一 ~ 十九
            a, _, b = tok.partition('十')
            return str((_CN_NUM.get(a, 1)) * 10 + (_CN_NUM.get(b, 0) if b else 0))
        return str(_CN_NUM[tok])
    return tok


@dataclass
class Finding:
    key: str
    level: str      # 'error' | 'warn' | 'info'
    title: str
    detail: str


# ---------------------------------------------------------------- 基础解析


def markdown_tables(md: str) -> list[list[str]]:
    """返回每个 markdown 表格的数据行（不含 |---| 分隔行）。"""
    blocks, cur = [], []
    for line in md.split('\n'):
        if line.strip().startswith('|'):
            cur.append(line)
        else:
            if cur:
                blocks.append(cur)
                cur = []
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        data = [l for l in b if not SEP.match(l)]
        if len(data) >= 2:
            out.append(data)
    return out


def count_tables(md: str) -> tuple[int, int]:
    """返回 (markdown 竖线表数, HTML 表数)。"""
    return len(markdown_tables(md)), len(HTML_TABLE.findall(md))


def _cells(data: list[str]) -> list[str]:
    out = []
    for l in data:
        out += [c.strip() for c in l.strip().strip('|').split('|')]
    return out


def pdf_table_captions(pdf: Path):
    """从 PDF 文字层数出真正的表格标题数。返回 (编号集合, 说明)。"""
    if pdf.suffix.lower() != '.pdf':
        return None, '非 PDF 输入，跳过原文核对'
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, 'pypdf 不可用，跳过原文核对'
    try:
        reader = PdfReader(str(pdf))
        txt = '\n'.join((p.extract_text() or '') for p in reader.pages)
    except Exception as e:
        return None, 'PDF 读取失败：%s' % str(e)[:60]
    raw = list(CAP_CN.findall(txt)) + list(CAP_EN.findall(txt))
    nums = {label_key(t) for t in raw}
    if nums:
        shown = ','.join(sorted(nums, key=lambda x: (len(x), x)))
        return nums, '原文表格标题：%d 个（%s）' % (len(nums), shown)
    return nums, '原文表格标题：0 个'


def pdf_page_count(path: Path) -> int | None:
    """保留此名以兼容旧调用；实现已移到 probe 模块。"""
    from .probe import page_count
    return page_count(path)


# ---------------------------------------------------------------- 体检规则


def _rule_table_count(pdf: Path, md: str, tbs) -> Finding | None:
    caps, note = pdf_table_captions(pdf)
    if caps is None:
        return Finding('table_count', 'info', '表格数核对', note)
    n_md, n_html = count_tables(md)
    n = n_md + n_html                    # HTML 表必须一起数，否则会误报漏检
    kind = 'markdown 表 %d + HTML 表 %d' % (n_md, n_html)
    # 原文一个编号标题都没有时无法交叉核对。实测这类文档（政府表单、
    # 无编号表格）里有大量真表格，直接判"编造"是误报。
    if not caps:
        return Finding(
            'table_count', 'info', '原文没有编号表格标题',
            '输出 %d 个表格（%s），但原文找不到 "Table N / 表N" 形式的标题，无法判定多寡。'
            '这类文档（表单、未编号表格）请人工抽查。' % (n, kind))
    diff = n - len(caps)
    # ±1 视为一致：MinerU 偶尔把一张视觉表拆成两个结构，或两个合并成一个
    if abs(diff) <= 1:
        return Finding('table_count', 'info', '表格数与原文一致',
                       '%s，输出 %d 个表格（%s）。' % (note, n, kind))
    if diff >= 2 and n >= len(caps) * 1.5:
        shapes = ', '.join(
            '%d行x%d列' % (len(d) - 1, len(d[0].strip().strip('|').split('|')))
            for d in tbs)
        # 降级为 warn：实测「超出」有两种成因，光看数量分不出来
        #   a) 曲线图被"数字化"成假表格（真问题，但通常伴随 ~ 值 / <details>，
        #      会被另外两条规则抓成 error）
        #   b) 宽表被拆成多个结构（YOLO 论文实测：3 个标题 → 5 个表格，内容其实是连续的）
        return Finding('table_count', 'warn', '表格数比原文多 %d 个' % diff,
                       '%s，输出 %d 个表格（%s）。两种可能：(a) 曲线图被"数字化"成假表格；'
                       '(b) 宽表被拆成了多个结构（实测 YOLO 论文 3 个标题拆成 5 个表）。'
                       '请对照原文抽查。markdown 表尺寸：%s' % (note, n, kind, shapes))
    if diff <= -2:
        return Finding('table_count', 'warn', '表格数少于原文 %d 个' % (-diff),
                       '%s，输出 %d 个表格（%s），可能有漏检。'
                       '（注意：正文里提到 "Table N" 也会被计入标题数，'
                       '所以这项也可能误报，请抽查。）' % (note, n, kind))
    return Finding('table_count', 'info', '表格数基本一致',
                   '%s，输出 %d 个表格（%s）。' % (note, n, kind))


def _rule_figure_blocks(pdf: Path, md: str, tbs) -> Finding | None:
    nd = md.count('<details>')
    nm = md.count('```mermaid')
    if nd or nm:
        # 实测：advanced 的图形解读产物（含被编造的表格）就包在 <details> 里，
        # 7 个 details 中有 5 个内含 markdown 表格 —— 删掉 details 等于清掉假表格。
        nested = len(re.findall(r'<details>.*?</details>', md, re.S))
        with_tbl = sum(1 for b in re.findall(r'<details>.*?</details>', md, re.S)
                       if markdown_tables(b) or HTML_TABLE.search(b))
        return Finding('figure_blocks', 'warn', '存在图像解读产物',
                       '<details> %d 个、mermaid %d 个。这些是 VLM 解读插图的产物，'
                       '实测其中 %d/%d 个内部包着被编造的表格；'
                       '图已作为图片导出，可安全删除。勾选"自动清理"会连同这些假表格一起清除。'
                       % (nd, nm, with_tbl, nested))
    return Finding('figure_blocks', 'info', '无图像解读产物', '没有 <details> / mermaid 块。')


def _rule_tilde(pdf: Path, md: str, tbs) -> Finding | None:
    hits = [c for d in tbs for c in _cells(d) if TILDE_VAL.match(c)]
    if hits:
        return Finding('tilde_values', 'error', '表格里有 %d 个 "~" 估算值' % len(hits),
                       '样例：%s。真实表格不会用 "~" 表示约等于，'
                       '这是模型在逐点估算图形坐标的指纹。' % ', '.join(hits[:5]))
    return Finding('tilde_values', 'info', '无 "~" 估算值', '正常。')


def _tighten(body: str) -> str:
    r"""收紧 $$ 块内被空格拆开的数字。

    实测到的形态（都来自 VLM 的 token 边界）：
        1. 2 3   → 1.23      0 . 4 9 → 0.49
        7 / 6    → 7/6       1 1 / 6 → 11/6

    ⚠️ 这是**纯源码可读性**的整理，不是渲染修复：
    实测（ziamath 渲染对比）证明 LaTeX 数学模式本来就忽略空格，
    `1. 2 3` 与 `1.23` 渲染结果逐字节相同；`P E` 与 `PE` 也相同。

    ⚠️ 安全性：`\text{}` / `\mbox{}` 这类命令里空格**是有意义的**，
    所以整块含这些命令时直接跳过，避免把 "\text{a b}" 改成 "\text{ab}"。
    """
    if re.search(r'\\(text|mbox|hbox|textrm|textit|textnormal)\b', body):
        return body
    s = re.sub(r'(\d)\s*\.\s+(\d)', r'\1.\2', body)   # 1. 2  → 1.2
    s = re.sub(r'(\d)\s+\.\s*(\d)', r'\1.\2', s)      # 0 . 4 → 0.4
    s = re.sub(r'(\d)\s*/\s*(\d)', r'\1/\2', s)       # 7 / 6 → 7/6
    s = re.sub(r'(\d)\s+(\d)', r'\1\2', s)            # 2 3   → 23
    return s


def _rule_formula_spacing(pdf: Path, md: str, tbs) -> Finding | None:
    disp = re.findall(r'\$\$(.+?)\$\$', md, re.S)
    bad = [f for f in disp if _tighten(f) != f]
    if bad:
        return Finding('formula_spacing', 'info',
                       '公式数字空格 %d/%d（仅影响源码可读性）' % (len(bad), len(disp)),
                       '例：%s  →  %s。'
                       '注意：实测 LaTeX 数学模式忽略空格，这两种写法的**渲染结果完全相同**，'
                       '所以这不是渲染缺陷，只是源码不够整洁。'
                       '勾选"自动清理"可整理，含 \\text{{}} 的公式会被跳过。'
                       % (re.sub(r'\s+', ' ', bad[0])[:50],
                          re.sub(r'\s+', ' ', _tighten(bad[0]))[:50]))
    return Finding('formula_spacing', 'info', '公式无需整理',
                   '块级公式 %d 个。' % len(disp))


def _rule_garbled_text(pdf: Path, md: str, tbs) -> Finding | None:
    """检测 PDF 文字层损坏：私用区字形 / 控制符 / 字符原地重复交错。

    实测（arXiv ResNet）：坏文字层会把表格单元格 "3×3, 64" 输出成
    "33××33,, 6644"，并混入 U+F8EE 之类的私用区字形（symbol 字体缺
    ToUnicode 映射）。`auto` 会把它判成 txt（因为字符数足够、看着不像乱码），
    于是 MinerU 直接用了坏文字层。

    强制 `--ocr-mode ocr` 可以绕过：实测交错重复 8→0、私用区 48→0，
    而且能正确还原堆叠单元格。
    """
    body = re.sub(r'data:image/[^\s)]+', '', md)     # 先去 base64，否则误判
    pua = len(re.findall(r'[\ue000-\uf8ff]', body))
    ctrl = len(re.findall(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', body))
    inter = count_interleave(body)
    if pua or ctrl or inter:
        return Finding(
            'garbled_text', 'error',
            '疑似文字层损坏（私用区 %d / 控制符 %d / 交错重复 %d 处）' % (pua, ctrl, inter),
            '特征：私用区字形、控制符，或字符原地重复（"3×3, 64" 变成 "33××33,, 6644"）。'
            '这是 PDF 文字层自身的问题，auto 会误判为 txt 从而沿用坏文字层。'
            '把该文件的 OCR 模式改成 ocr 强制重跑即可绕过——实测能把交错重复清零、'
            '并正确还原堆叠单元格。')
    return Finding('garbled_text', 'info', '文字层未见损坏',
                   '私用区/控制符/交错重复均为 0。')


# 散文段落：连续 4 个以上英文单词。用于识别"被整段包进 $$ 的正文"。
# 实测：arXiv 纯数学论文 37%、Shor 论文 80% 的块公式其实是散文。
PROSE_IN_MATH = re.compile(r'\b[A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){3,}')
_TEXT_CMD = re.compile(r'\\(?:text|mathrm|mbox|hbox|textrm|textit|textnormal)\s*\{[^}]*\}')


def strip_text_commands(body: str) -> str:
    """去掉 \\text{} / \\mathrm{} 等内容，只留真正的数学部分。

    这些命令里空格是有意义的，不能拿它们判断"是不是散文"。
    """
    prev = None
    while prev != body:
        prev = body
        body = _TEXT_CMD.sub('', body)
    return body


def is_prose_formula(body: str) -> bool:
    """这个 $$ 块是不是其实是正文段落。"""
    return bool(PROSE_IN_MATH.search(strip_text_commands(body)))


def _rule_prose_in_formula(pdf: Path, md: str, tbs) -> Finding | None:
    disp = re.findall(r'\$\$(.+?)\$\$', md, re.S)
    bad = [d for d in disp if is_prose_formula(d)]
    if bad:
        m = PROSE_IN_MATH.search(strip_text_commands(bad[0]))
        return Finding(
            'prose_in_formula', 'warn',
            '%d/%d 个块公式里其实是散文' % (len(bad), len(disp)),
            '样例："%s"。正文段落被整段包进了 `$$`；'
            '数学模式忽略空格，渲染时单词会连成一坨'
            '（实测："countable subadditivity" 与 "countablesubadditivity" 渲染完全相同）。'
            '勾选"自动清理"会去掉外层 `$$` 把它们还原成正文段落。'
            % (m.group(0)[:46] if m else ''))
    return Finding('prose_in_formula', 'info', '块公式里未见散文',
                   '块级公式 %d 个。' % len(disp))


# 想加新检查项？写一个 (pdf, md, tables) -> Finding | None 的函数加进来即可
_RULES = [_rule_table_count, _rule_figure_blocks, _rule_tilde,
          _rule_formula_spacing, _rule_garbled_text, _rule_prose_in_formula]


def check(pdf: Path, md_path: Path) -> list[Finding]:
    try:
        md = md_path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return [Finding('read', 'error', '无法读取输出', str(e)[:80])]
    tbs = markdown_tables(md)
    return [f for f in (r(pdf, md, tbs) for r in _RULES) if f]


def summarize(findings: list[Finding]) -> str:
    errs = sum(1 for f in findings if f.level == 'error')
    warns = sum(1 for f in findings if f.level == 'warn')
    if errs:
        return '体检：%d 项严重、%d 项警告' % (errs, warns)
    if warns:
        return '体检：%d 项警告' % warns
    return '体检：通过'


# ---------------------------------------------------------------- 清理


def clean(md_path: Path) -> dict:
    """原地清理：删除 details/mermaid 块、把误包成公式的散文还原成正文、
    整理公式里的数字空格。

    注意：实测 MinerU 会把「图形解读产物」（包括被编造成表格的假数据）
    一并包在 <details> 里，所以删掉 details 通常也把假表格清掉了。
    tables_removed 会如实报告少了多少张表。
    """
    md = md_path.read_text(encoding='utf-8', errors='replace')
    n_details = md.count('<details>')
    n_mermaid = md.count('```mermaid')
    n_tables_before = len(markdown_tables(md))

    fixed = re.sub(r'<details>.*?</details>\s*', '', md, flags=re.S)
    fixed = re.sub(r'```mermaid.*?```\s*', '', fixed, flags=re.S)

    n_fix = [0]
    n_prose = [0]

    def _merge(m):
        body = m.group(1)
        # 先看是不是散文被误包成公式：是的话直接去掉外层 $$ 还原成正文
        if is_prose_formula(body):
            n_prose[0] += 1
            return body.strip()
        new = _tighten(body)
        if new != body:
            n_fix[0] += 1
        return '$$' + new + '$$'

    fixed = re.sub(r'\$\$(.+?)\$\$', _merge, fixed, flags=re.S)
    fixed = re.sub(r'\n{3,}', '\n\n', fixed)

    n_tables_after = len(markdown_tables(fixed))
    changed = fixed != md
    if changed:
        md_path.write_text(fixed, encoding='utf-8')
    return {
        'changed': changed,
        'details_removed': n_details,
        'mermaid_removed': n_mermaid,
        'formulas_fixed': n_fix[0],
        'prose_demoted': n_prose[0],
        'tables_removed': max(0, n_tables_before - n_tables_after),
        'tables_left': n_tables_after,
    }
