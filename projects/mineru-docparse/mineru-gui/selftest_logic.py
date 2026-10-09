"""关键逻辑分支自检（不开界面、不跑 MinerU）。"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mineru_gui import checker
from mineru_gui.config import Settings
from mineru_gui.runner import Job, plan_output

fails = []


def expect(cond, label):
    print('  %s %s' % ('[OK]' if cond else '[!!]', label))
    if not cond:
        fails.append(label)


print('=== plan_output：绝不覆盖已有文件 ===')
d = Path(__file__).resolve().parent / '_logic_tmp'
shutil.rmtree(d, ignore_errors=True)
d.mkdir(parents=True, exist_ok=True)
src = d / 'paper.pdf'
src.write_bytes(b'%PDF-1.4')
s = Settings(output_dir=str(d))

out = plan_output(src, s)
expect(out == d / 'paper.md', '输出不存在时 → paper.md')

(d / 'paper.md').write_text('old', encoding='utf-8')
s.skip_existing = True
expect(plan_output(src, s) is None, '已存在 + 勾选跳过 → 返回 None（跳过）')

s.skip_existing = False
out2 = plan_output(src, s)
expect(out2 == d / 'paper (2).md', '已存在 + 不跳过 → 自动改名 paper (2).md')
expect((d / 'paper.md').read_text(encoding='utf-8') == 'old', '原文件未被改动')

(d / 'paper (2).md').write_text('old2', encoding='utf-8')
expect(plan_output(src, s) == d / 'paper (3).md', '再冲突 → paper (3).md')

print()
print('=== checker._tighten：数字空格整理 + \\text{} 保护 ===')
for src_t, want in [
    ('1. 2 3', '1.23'),
    ('0 . 4 9', '0.49'),
    ('k ^ {7 / 6}', 'k ^ {7/6}'),
    ('l _ {fso} ^ {1 1 / 6}', 'l _ {fso} ^ {11/6}'),
    (r'2 \times 3', r'2 \times 3'),          # 合法写法不能改坏
    (r'\frac {a} {b}', r'\frac {a} {b}'),
    # \text{} 里空格有意义，必须原样跳过（实测踩过这个风险）
    (r'\text{Fig 1 2}', r'\text{Fig 1 2}'),
    (r'\text{a b} + 1. 2 3', r'\text{a b} + 1. 2 3'),
]:
    got = checker._tighten(src_t)
    expect(got == want, '%-26s → %-22s (got %s)' % (src_t, want, got))

print()
print('=== 公式空格项应为 info（实测证明不影响渲染）===')
_f = checker._rule_formula_spacing(Path('x.pdf'), '$$1. 2 3$$', [])
expect(_f.level == 'info', '公式空格降级为 info（当前 %s）' % _f.level)
expect('渲染结果完全相同' in _f.detail, 'detail 里说明了不影响渲染')

print()
print('=== checker.label_key：表格编号写法归一 ===')
for src_t, want in [
    ('1', '1'), ('01', '1'), ('I', '1'), ('II', '2'), ('IV', '4'),
    ('IX', '9'), ('X', '10'), ('XI', '11'), ('XX', '20'),
    ('一', '1'), ('三', '3'), ('十', '10'), ('十二', '12'),
]:
    got = checker.label_key(src_t)
    expect(got == want, 'Table %-4s → %-3s (got %s)' % (src_t, want, got))

print()
print('=== 表格编号正则能认出罗马数字编号 ===')
for s, want in [('Table I.', '1'), ('TABLE II:', '2'), ('Table 3', '3'),
                ('表1', '1'), ('表 二', '2')]:
    toks = checker.CAP_CN.findall(s) + checker.CAP_EN.findall(s)
    keys = [checker.label_key(t) for t in toks]
    expect(keys == [want], '%-12s → %s' % (s, keys))

print()
print('=== config.effective_tier：flash-only 格式必须降档 ===')
from mineru_gui.config import effective_tier, reject_reason   # noqa: E402
for name, tier, want in [
    ('a.pdf', 'standard', 'standard'),
    ('a.PDF', 'advanced', 'advanced'),
    ('a.png', 'advanced', 'advanced'),
    ('a.tiff', 'standard', 'standard'),
    ('a.jpg', 'basic', 'basic'),
    ('a.docx', 'standard', 'flash'),      # ← 实测：传 standard 会直接报错
    ('a.xlsx', 'advanced', 'flash'),
    ('a.pptx', 'standard', 'flash'),
    ('a.html', 'standard', 'flash'),
    ('a.epub', 'standard', 'flash'),
    ('a.rtf', 'standard', 'flash'),
    ('a.odt', 'standard', 'flash'),
    ('a.ofd', 'standard', 'flash'),
    ('a.csv', 'standard', 'flash'),
]:
    got = effective_tier(name, tier)
    expect(got == want, '%-10s tier=%-9s → %-9s (got %s)' % (name, tier, want, got))

print()
print('=== config.reject_reason：入口拦截不能解析的类型 ===')
for name, want_none in [
    ('a.pdf', True), ('a.png', True), ('a.tiff', True), ('a.gif', True),
    ('a.jp2', True), ('a.webp', True), ('a.docx', True), ('a.ofd', True),
    ('a.tif', False),          # ← MinerU 只认 tiff，不认 tif
    ('a.txt', False),          # ← 纯文本只有文档库能读
    ('a.md', False),
    ('a.mobi', False),
    ('a.djvu', False),
]:
    why = reject_reason(name)
    expect((why is None) == want_none,
           '%-8s → %s' % (name, '可解析' if why is None else why))

print()
print('=== checker.clean：清理 details / mermaid / 公式空格 ===')
md = d / 'dirty.md'
md.write_text(
    '# 标题\n\n'
    '$$1. 2 3 \\mathrm{C}$$\n\n'
    '<details>\n<summary>flowchart</summary>\n编造内容\n</details>\n\n'
    '```mermaid\ngraph LR\n  A-->B\n```\n\n'
    '正文结束\n',
    encoding='utf-8')
r = checker.clean(md)
after = md.read_text(encoding='utf-8')
expect(r['details_removed'] == 1, '删除 1 个 <details>')
expect(r['mermaid_removed'] == 1, '删除 1 个 mermaid 块')
expect(r['formulas_fixed'] == 1, '修复 1 个公式的数字空格')
expect('1.23' in after, '公式变成 1.23')
expect('<details>' not in after and 'mermaid' not in after, '编造块已清除')
expect('正文结束' in after and '# 标题' in after, '正文保留')

print()
print('=== checker.markdown_tables：表格识别 ===')
t = checker.markdown_tables('| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\n正文\n')
expect(len(t) == 1 and len(t[0]) == 3, '识别 1 个表、3 行（含表头）')

print()
print('=== Settings.build_env：环境变量注入 ===')
s2 = Settings(mineru_home=r'D:\x', output_dir=str(d))
env = s2.build_env()
expect(env.get('MINERU_HOME') == r'D:\x', 'MINERU_HOME 已注入')
expect(env.get('MINERU_MODEL_VLM_ENGINE') == 'lmdeploy', 'VLM 引擎默认 lmdeploy')
expect(env.get('PYTHONIOENCODING') == 'utf-8', '强制 UTF-8 输出')

print()
print('=== Settings.validate：advanced 未关图像分析要报警 ===')
s3 = Settings(mineru_kit=sys.executable, mineru_home='x', output_dir='y',
              tier='advanced', disable_image_analysis=False)
expect(any('图像分析' in e for e in s3.validate()), 'advanced + 开图像分析 → 报警')
s3.disable_image_analysis = True
expect(not any('图像分析' in e for e in s3.validate()), '关掉后 → 不报警')

shutil.rmtree(d, ignore_errors=True)
print()
print('=' * 50)
print('失败项：%d' % len(fails))
for f in fails:
    print('  -', f)
sys.exit(1 if fails else 0)
