#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""端到端流程自检：驱动**真实的 App**走一遍完整交互。

不绕过界面直接调 runner —— 而是构造 App、设输出目录、加文件、等后台探测回报、
调用 _start()，然后泵事件循环直到全部完成，最后校验产物。

    # 默认用工程自带的一组样本（存在才用）
    python selftest_flow.py

    # 指定文件与输出目录
    python selftest_flow.py --out D:\某处输出 a.pdf b.png c.docx

会临时改写 settings.json，结束后自动还原。
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time
from pathlib import Path

APP_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

import run as launcher                          # noqa: E402  复用启动处理
launcher.fix_tcl()
launcher.ensure_venv_packages()

from mineru_gui.config import Settings          # noqa: E402
from mineru_gui.ui import App                   # noqa: E402

SETTINGS = APP_DIR / 'settings.json'

DEFAULT_SAMPLES = [
    Path(os.environ.get('MINERU_PAPERS') or (Path.home() / 'Desktop')) / '研究背景.pdf',
    Path(os.environ.get('MINERU_PAPERS') or (Path.home() / 'Desktop')) / '检焦方案'
    / '差动临界角法高精度动态检焦技术研究_彭玲娜.pdf',
    pathlib.Path(r'%PAPERS%\1-s2.0-S0030401820306362-main.pdf'),
    pathlib.Path(r'%PAPERS%\Differential_pulse-position_modulation_for_power-efficient_optical_communication.pdf'),
    APP_DIR / 'assets' / 'icon.png',
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*', help='要转换的文件；省略则用内置样本')
    ap.add_argument('--out', default=str(APP_DIR.parent.parent / 'MinerU-测试输出'),
                    help='输出目录')
    ap.add_argument('--probe-wait', type=float, default=120.0)
    ap.add_argument('--timeout', type=float, default=3600.0)
    ap.add_argument('--timeout-per-file', type=float, default=None,
                    help='单文件超时秒数；批量跑异常样本时建议调小，避免卡住')
    ap.add_argument('--tier', default=None, help='覆盖档位：flash/basic/standard/advanced')
    ap.add_argument('--ocr-mode', default=None, help='覆盖 OCR 模式：auto/txt/ocr')
    a = ap.parse_args()

    files = [Path(f) for f in (a.files or DEFAULT_SAMPLES)]
    files = [f for f in files if f.exists()]
    if not files:
        print('没有可用的输入文件')
        return 2

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    backup = SETTINGS.read_text(encoding='utf-8') if SETTINGS.exists() else None

    print('输出目录：%s' % out_dir)
    print('输入文件：%d 个' % len(files))

    app = App(Settings.load())
    if a.timeout_per_file:
        app.settings.per_file_timeout_sec = int(a.timeout_per_file)
    if a.tier:
        app.settings.tier = a.tier
    if a.ocr_mode:
        app.settings.ocr_mode = a.ocr_mode
    app._load_settings_into_ui()
    app.var_out.set(str(out_dir))
    app.update()

    # ---------- 1. 添加 + 等探测 ----------
    print('\n=== 1. 添加文件，等待后台探测 ===')
    app._append(files)
    deadline = time.time() + a.probe_wait
    while time.time() < deadline:
        app.update()
        time.sleep(0.1)
        if all(j.auto_mode for j in app.jobs):
            break
    print('%-46s %5s %6s' % ('文件', '页数', 'auto'))
    for j in app.jobs:
        print('%-46s %5s %6s' % (j.name[:44], j.pages, j.auto_mode))

    # ---------- 2. 开始 ----------
    print('\n=== 2. 开始转换（%s / OCR %s / 关图像分析=%s）==='
          % (app.settings.tier, app.settings.ocr_mode, app.settings.disable_image_analysis))
    t0 = time.time()
    app._start()
    if not app.runner.running:
        print('!! 未能启动')
        app.destroy()
        return 1

    last = ''
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        app.update()
        time.sleep(0.2)
        line = app.lbl_stat.cget('text')
        if line != last:
            print('   [%6.1fs] %s' % (time.time() - t0, line))
            last = line
        if not app.runner.running:
            break
    for _ in range(10):
        app.update()
        time.sleep(0.1)

    # ---------- 3. 结果 ----------
    print('\n=== 3. 结果（总耗时 %.0f 秒）===' % (time.time() - t0))
    print('%-46s %8s %7s  %s' % ('文件', '状态', '用时', '备注'))
    ok = fail = skip = 0
    issues = 0
    for j in app.jobs:
        ok += j.status == 'done'
        fail += j.status == 'failed'
        skip += j.status == 'skipped'
        print('%-46s %8s %6.0fs  %s' % (j.name[:44], j.status, j.seconds, j.message))
        for f in j.findings:
            if f.level in ('error', 'warn'):
                issues += 1
                print('        [%s] %s —— %s' % (f.level.upper(), f.title, f.detail[:90]))

    print('\n成功 %d / 跳过 %d / 失败 %d / 体检问题 %d 项' % (ok, skip, fail, issues))

    # ---------- 4. 产物 ----------
    print('\n=== 4. 产物校验 ===')
    missing = []
    for j in app.jobs:
        if not j.out:
            continue
        p = Path(j.out)
        exists = p.exists()
        if j.status == 'done' and not exists:
            missing.append(j.name)
        print('  %-46s %s %9.1f KB' % (p.name[:44], '存在' if exists else '缺失',
                                       p.stat().st_size / 1024 if exists else 0))
    print('\n进度条 = %.0f%%' % app.pb['value'])
    print('状态栏 = %s' % app.lbl_stat.cget('text'))
    logs = sorted(out_dir.glob('_运行日志_*.txt'))
    if logs:
        print('本次运行日志（App 自动保存）：%s' % logs[-1].name)

    app.destroy()
    if backup is not None:
        SETTINGS.write_text(backup, encoding='utf-8')
    print('settings.json 已还原')

    return 0 if (not missing and fail == 0 and issues == 0) else 1


if __name__ == '__main__':
    sys.exit(main())
