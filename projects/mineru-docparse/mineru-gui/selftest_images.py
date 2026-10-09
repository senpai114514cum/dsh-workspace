"""验证：图片抽取 + 乱码检测 + 各模块回归。"""
import os
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
from mineru_gui import checker, images

# 测试用的原文/产物目录。本仓库不含语料，所以默认按"与本目录同级"推导；
# 换机器时用 MINERU_TESTDATA / MINERU_OUTDIR 指过去即可，缺失的用例会自动跳过。
TESTDATA = Path(os.environ.get('MINERU_TESTDATA') or (APP_DIR.parent / '_corpus' / 'test'))
OUTDIR = Path(os.environ.get('MINERU_OUTDIR') or (APP_DIR.parent.parent / 'MinerU-鲁棒性测试'))

fails = []


def expect(cond, label):
    print('  %s %s' % ('[OK]' if cond else '[!!]', label))
    if not cond:
        fails.append(label)


TMP = APP_DIR / '_imgtest'
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True, exist_ok=True)

print('=== images.extract_inline_images ===')
# 造一份含两张内联图（其中一张重复引用）的 md
PNG = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
JPG = ('/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a'
       'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA'
       'AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==')
md = TMP / 'doc.md'
md.write_text(
    '# 标题\n\n图1：![](data:image/png;base64,%s)\n\n正文\n\n'
    '图2：![](data:image/jpeg;base64,%s)\n\n'
    '再引用图1：![](data:image/png;base64,%s)\n' % (PNG, JPG, PNG),
    encoding='utf-8')

r = images.extract_inline_images(md)
after = md.read_text(encoding='utf-8')
expect(r['count'] == 3, '抽出 3 处引用（count=%d）' % r['count'])
expect(r['unique'] == 2, '去重后 2 个文件（unique=%d）' % r['unique'])
expect('data:image' not in after, 'md 里已无 base64')
expect(after.count('doc.assets/img_001_') == 2, '同一张图两处引用共用同一文件')
expect(str(Path(r['dir']).name) == 'doc.assets', '资源目录名为 doc.assets')
expect(len(list(Path(r['dir']).iterdir())) == 2, '磁盘上确实只有 2 个图片文件')
expect(r['after'] < r['before'] / 2, 'md 体积明显缩小（%d → %d 字节）' % (r['before'], r['after']))
print('    md 内容: ' + after.replace('\n', ' | ')[:120])

print()
print('=== 没有内联图时应当是空操作 ===')
md2 = TMP / 'plain.md'
md2.write_text('# 纯文本\n\n没有图。\n', encoding='utf-8')
r2 = images.extract_inline_images(md2)
expect(r2['count'] == 0 and not r2['changed'], '空操作')
expect(md2.read_text(encoding='utf-8') == '# 纯文本\n\n没有图。\n', '文件未被改动')

print()
print('=== checker._rule_garbled_text ===')
garbled = '# t\n\n| a | b |\n|---|---|\n| \x1433××33,, 6644\x15 | \uf8ee\uf8f0 |\n'
f = checker._rule_garbled_text(Path('x.pdf'), garbled, checker.markdown_tables(garbled))
expect(f.level == 'error', '交错重复 + 私用区 → error')
expect('ocr' in f.detail, 'detail 里给出了 ocr 的解决办法')

clean = '# t\n\n| a | b |\n|---|---|\n| 3×3, 64 | ok |\n'
f2 = checker._rule_garbled_text(Path('x.pdf'), clean, checker.markdown_tables(clean))
expect(f2.level == 'info', '正常文本 → info')

# base64 不能被误判成交错重复
b64 = '![](' + 'data:image/png;base64,' + 'AAaaBBbbCCccDDddEEeeFFff' * 3 + ')'
f3 = checker._rule_garbled_text(Path('x.pdf'), b64, [])
expect(f3.level == 'info', 'base64 内联图不误判为乱码')

# 缩进 / 分隔线 / ASCII art 不能被误判（实测踩过：8 个空格被判成交错重复）
for label, text in [
    ('8 个空格缩进', '1. a\n' + '        ' + '2. b\n'),
    ('16 个空格缩进', 'x\n' + ' ' * 16 + 'y\n'),
    ('markdown 分隔线', 'a\n\n--------\n\nb\n'),
    ('代码块里的等号线', '```\n========\n```\n'),
    ('点号填充（目录）', 'Chapter 1 .............. 5\n'),
]:
    f = checker._rule_garbled_text(Path('x.pdf'), text, [])
    expect(f.level == 'info', '%s 不误判为乱码' % label)

# 真正的交错重复必须仍被抓到
f4 = checker._rule_garbled_text(Path('x.pdf'), '33××33,, 6644', [])
expect(f4.level == 'error', '真实交错重复仍报 error')
expect(checker.count_interleave('33××33,, 6644') == 1, 'count_interleave 计数正确')
expect(checker.count_interleave(' ' * 20) == 0, 'count_interleave 忽略空白')
expect(checker.count_interleave('-' * 20) == 0, 'count_interleave 忽略单一字符重复')

print()
print('=== 真实文件：ResNet 已用 ocr 修复，现在应报 info ===')
res = OUTDIR / 'dl-arxiv-resnet.md'
if res.exists():
    fs = checker.check(TESTDATA / 'dl-arxiv-resnet.pdf', res)
    g = next((x for x in fs if x.key == 'garbled_text'), None)
    expect(g is not None and g.level == 'info',
           'ResNet 修复后不再报文字层损坏（%s）' % (g.title if g else '?'))
else:
    print('  （跳过：语料不在，设 MINERU_TESTDATA / MINERU_OUTDIR 可启用）')

print()
print('=== 真实文件：arXiv Attention（本来就干净）应为 info ===')
att = OUTDIR / 'dl-arxiv-attention.md'
if att.exists():
    fs = checker.check(TESTDATA / 'dl-arxiv-attention.pdf', att)
    g = next((x for x in fs if x.key == 'garbled_text'), None)
    expect(g is not None and g.level == 'info', 'Attention 未误报')
else:
    print('  （跳过：语料不在）')

print()
print('=== checker 散文误包公式：检测与还原 ===')
_prose = ('$$\n, countable subadditivity yields indices $i \\in \\{ 1 , \\ldots , n \\}$ '
          'and $k \\geq 1$ for which\n$$\n\n正常段落。\n')
f = checker._rule_prose_in_formula(Path('x.pdf'), _prose, [])
expect(f.level == 'warn', '散文被包进 $$ → warn')
expect('连成一坨' in f.detail, 'detail 说明了渲染后果')

_ok = '$$E = mc^{2}$$'
expect(checker._rule_prose_in_formula(Path('x.pdf'), _ok, []).level == 'info',
       '正常公式不误报')
# \text{} 里有很多英文单词也不能算散文
_txt = r'$$y = \text{countable subadditivity yields indices}$$'
expect(checker._rule_prose_in_formula(Path('x.pdf'), _txt, []).level == 'info',
       r'\text{} 里的英文不算散文')

_md = TMP / 'prose.md'
_md.write_text(_prose, encoding='utf-8')
_r = checker.clean(_md)
_after = _md.read_text(encoding='utf-8')
expect(_r['prose_demoted'] == 1, 'clean 还原了 1 个散文块')
expect(not _after.lstrip().startswith('$$'), '还原后不再是公式块')
expect('countable subadditivity yields' in _after, '正文保留')
expect('$i \\in \\{ 1 , \\ldots , n \\}$' in _after, '内层行内公式保留')

print()
print('=' * 50)
print('失败项：%d' % len(fails))
for x in fails:
    print('  -', x)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if fails else 0)
