"""验证表格计数修复：HTML 表要一起数，误报要消除、真阳性要保留。"""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
from mineru_gui import checker

# 语料不在本仓库里。默认按"与本目录同级"推导，可用环境变量覆盖；
# 找不到的用例会自动跳过，所以没有语料时这个脚本也能跑通。
TESTDATA = Path(os.environ.get('MINERU_TESTDATA') or (APP_DIR.parent / '_corpus' / 'test'))
ROOT = APP_DIR.parent.parent                      # 各测试输出目录的父目录
PAPERS = Path(os.environ.get('MINERU_PAPERS') or (Path.home() / 'Desktop'))

CASES = [
    # (标签, pdf, md, 期望的表格项 level)
    ('ResNet（之前误报"少 3 个"）',
     TESTDATA / 'dl-arxiv-resnet.pdf',
     ROOT / 'MinerU-鲁棒性测试' / 'dl-arxiv-resnet.md', 'info'),
    ('Attention（之前误报"少 2 个"）',
     TESTDATA / 'dl-arxiv-attention.pdf',
     ROOT / 'MinerU-鲁棒性测试' / 'dl-arxiv-attention.md', 'info'),
    ('IRS 表单（原文 0 标题）',
     TESTDATA / 'dl-irs-fw9-form.pdf',
     ROOT / 'MinerU-鲁棒性测试' / 'dl-irs-fw9-form.md', 'info'),
    ('罗马数字论文（更早的误报）',
     PAPERS / 'Differential_pulse-position_modulation_for_power-efficient_optical_communication.pdf',
     ROOT / 'MinerU-测试输出' / 'Differential_pulse-position_modulation_for_power-efficient_optical_communication.md', 'info'),
    ('p2 advanced 真编造（表格项降为 warn，另有 ~ 值报 error）',
     PAPERS / '1-s2.0-S0030401820306362-main.pdf',
     ROOT / 'MinerU-GPU' / 'out' / 'p2-advanced.md', 'warn'),
    ('p3 advanced 真编造（表格项降为 warn，另有 ~ 值报 error）',
     PAPERS / '检焦方案' / '差动临界角法高精度动态检焦技术研究_彭玲娜.pdf',
     ROOT / 'MinerU-GPU' / 'out' / 'p3-advanced.md', 'warn'),
    ('p2 standard 干净',
     PAPERS / '1-s2.0-S0030401820306362-main.pdf',
     ROOT / 'MinerU-GPU' / 'out' / 'p2-standard.md', 'info'),
    # 本轮新增：宽表拆分（YOLO 3 个标题 → 5 个表）与分节编号（Table 3.1/3.2）
    ('YOLO 宽表被拆分（表格项降为 warn）',
     TESTDATA.parent / 'rich' / 'en-04-图表密集-YOLO.pdf',
     ROOT / 'MinerU-富公式富图表测试' / 'en-04-图表密集-YOLO.md', 'warn'),
    ('Shor 分节编号 Table 3.1/3.2（应为 info）',
     TESTDATA.parent / 'rich' / 'en-05-经典-Shor算法.pdf',
     ROOT / 'MinerU-富公式富图表测试' / 'en-05-经典-Shor算法.md', 'info'),
]

fails = 0
print('%-38s %-6s %-6s %s' % ('用例', '期望', '实际', '表格项'))
print('-' * 104)
for label, pdf, md, want in CASES:
    pdf, md = Path(pdf), Path(md)
    if not (pdf.exists() and md.exists()):
        print('%-38s 文件缺失' % label)
        continue
    fs = checker.check(pdf, md)
    tc = next((f for f in fs if f.key == 'table_count'), None)
    got = tc.level if tc else '?'
    ok = got == want
    if not ok:
        fails += 1
    print('%-38s %-6s %-6s %s %s' % (label, want, got, '[OK]' if ok else '[!!]',
                                     (tc.title + ' —— ' + tc.detail[:60]) if tc else ''))

print()
print('失败项：%d' % fails)
sys.exit(1 if fails else 0)
