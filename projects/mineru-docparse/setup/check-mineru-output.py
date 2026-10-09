#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
MinerU 输出体检 / 消幻觉校验工具

用法（用 MinerU 环境自带的 python 跑，因为需要 pypdf）：

    # 只体检，不改文件
    & '%MINERU_ROOT%\.venv\Scripts\python.exe' check-mineru-output.py 原文.pdf 输出.md

    # 体检并自动清理（删除 mermaid/details 块、合并被空格拆开的公式数字）
    & '%MINERU_ROOT%\.venv\Scripts\python.exe' check-mineru-output.py 原文.pdf 输出.md --fix

体检项：
  1. 表格数 vs 原文"表N / Table N"标题数  —— 最主要的幻觉判据
  2. <details> 与 ```mermaid 块            —— 图像解读的产物，幻觉载体
  3. 表格里带 "~" 前缀的数值               —— VLM 估算图形坐标的指纹
  4. 公式里被空格拆开的数字                —— 渲染缺陷
"""
from __future__ import annotations

import argparse
import os
import re
import sys

# 中文 Windows 控制台默认是 GBK 代码页，直接 print 会因编码崩溃：统一转 UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

SEP = re.compile(r'^\s*\|[\s:\-\|]+\|\s*$')
CAP_CN = re.compile(r'表\s*(\d+)')
CAP_EN = re.compile(r'Table\s*(\d+)')


def read(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read()


def tables(md: str):
    """返回 [ [行,...], ... ]，每项是一个 markdown 表格的数据行（不含分隔行）"""
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


def pdf_table_captions(pdf: str):
    """从 PDF 文字层里数出真正的表格标题编号"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, 'pypdf 未安装，跳过原文核对'
    try:
        r = PdfReader(pdf)
        txt = '\n'.join((pg.extract_text() or '') for pg in r.pages)
    except Exception as e:
        return None, 'PDF 读取失败: %s' % str(e)[:50]
    cn = set(CAP_CN.findall(txt))
    en = set(CAP_EN.findall(txt))
    return {'cn': cn, 'en': en, 'total': len(cn | en)}, None


def cells(data):
    out = []
    for l in data:
        out += [c.strip() for c in l.strip().strip('|').split('|')]
    return out


def check(pdf: str, md_path: str, do_fix: bool) -> int:
    md = read(md_path)
    problems = 0

    print('=' * 70)
    print('体检: %s' % os.path.basename(md_path))
    print('=' * 70)

    # ---- 1. 表格数核对 ----
    tbs = tables(md)
    caps, err = pdf_table_captions(pdf)
    print('\n[1] 表格数核对')
    if caps is None:
        print('    %s' % err)
    else:
        print('    原文表格标题: %d 个  (中文 表%s / 英文 Table %s)'
              % (caps['total'], sorted(caps['cn']) or '-', sorted(caps['en']) or '-'))
        print('    输出表格:     %d 个' % len(tbs))
        if len(tbs) > caps['total']:
            print('    [!!] 多出 %d 个，几乎可以确定是**编造的**（曲线图被数字化成表格）'
                  % (len(tbs) - caps['total']))
            for i, d in enumerate(tbs, 1):
                c = len(d[0].strip().strip('|').split('|'))
                print('        表%d  %d行 x %d列' % (i, len(d) - 1, c))
            problems += 1
        elif len(tbs) < caps['total']:
            print('    ! 少了 %d 个，可能有表格被漏掉' % (caps['total'] - len(tbs)))
            problems += 1
        else:
            print('    [OK] 数量一致')

    # ---- 2. details / mermaid ----
    nd = md.count('<details>')
    nm = md.count('```mermaid')
    print('\n[2] 图像解读产物（幻觉载体）')
    print('    <details> 块: %d    ```mermaid 块: %d' % (nd, nm))
    if nd or nm:
        print('    ! 这些是 VLM "解读"插图的产物，实测包含大量编造内容')
        print('      图本身已经作为图片文件导出，这些块可以直接删')
        problems += 1
    else:
        print('    [OK] 无')

    # ---- 3. 表格里的 "~" 估算值 ----
    print('\n[3] 表格中的 "~" 估算值')
    tilde = []
    for i, d in enumerate(tbs, 1):
        for c in cells(d):
            if re.match(r'^~\s*[-+]?\d', c) or re.match(r'^~\s*\d*\^', c):
                tilde.append((i, c))
    if tilde:
        print('    ! 找到 %d 个，样例: %s' % (len(tilde), [c for _, c in tilde[:6]]))
        print('      真实表格不会用 "~" 表示约等于；这是模型在估算图形坐标')
        problems += 1
    else:
        print('    [OK] 无')

    # ---- 4. 公式数字被空格拆开 ----
    print('\n[4] 公式中的数字空格缺陷')
    disp = re.findall(r'\$\$(.+?)\$\$', md, re.S)
    bad = [f for f in disp if re.search(r'\d\s*\.\s+\d|\d\s+\d\s+\d', f)]
    print('    块级公式 %d 个，其中 %d 个含缺陷' % (len(disp), len(bad)))
    if bad:
        for f in bad[:2]:
            m = re.search(r'.{0,40}(?:\d\s*\.\s+\d|\d\s+\d\s+\d).{0,40}', f, re.S)
            if m:
                print('      例: %s' % m.group(0).replace('\n', ' ')[:90])
        problems += 1
    else:
        print('    [OK] 无')

    # ---- 结论 ----
    print('\n' + '-' * 70)
    if problems == 0:
        print('结论: 未发现幻觉迹象 [OK]')
    else:
        print('结论: 发现 %d 类问题，见上' % problems)

    # ---- 自动清理 ----
    if do_fix:
        fixed = md
        fixed = re.sub(r'<details>.*?</details>\s*', '', fixed, flags=re.S)
        fixed = re.sub(r'```mermaid.*?```\s*', '', fixed, flags=re.S)
        # 仅在本行是 $$ 块内部时合并数字空格（保守做法：整体对 $$..$$ 内容处理）
        def merge(m):
            return '$$' + re.sub(r'(?<=\d)\s+(?=[\d.])', '', m.group(1)) + '$$'
        fixed = re.sub(r'\$\$(.+?)\$\$', merge, fixed, flags=re.S)
        out = md_path.replace('.md', '-fixed.md')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(fixed)
        print('已清理并写出: %s' % out)
        print('  （删除了 details/mermaid 块，合并了公式里的数字空格）')
        print('  注意: 编造的表格需要人工确认后删除，脚本不敢自动删表')

    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf', help='原始 PDF 路径')
    ap.add_argument('md', help='MinerU 输出的 markdown 路径')
    ap.add_argument('--fix', action='store_true', help='体检后自动清理 details/mermaid 并修公式空格')
    a = ap.parse_args()
    if not os.path.exists(a.md):
        print('找不到 %s' % a.md)
        sys.exit(2)
    sys.exit(1 if check(a.pdf, a.md, a.fix) else 0)


if __name__ == '__main__':
    main()
