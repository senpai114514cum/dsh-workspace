#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""MinerU 批量转换器 —— 启动入口。

    python run.py                    启动图形界面
    python run.py --selftest 文件.pdf  不开界面，跑一遍完整流水线（自检用）
    python run.py --uicheck          只构建界面然后退出（自检用）

为什么需要 fix_tcl()：
    本机 Python 3.13 的 Tcl 运行库路径没被正确编入，直接 tkinter.Tk() 会报
    "Can't find a usable init.tcl"。这里按 sys.base_prefix 自动补上
    TCL_LIBRARY / TK_LIBRARY，不需要手工设环境变量。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

# 基础 Python 的 pythonw.exe 是真正的「无控制台」解释器；
# 而 venv 里的 pythonw.exe 是 uv 的引导器（247KB），它会拉起控制台版 python.exe，
# 双击时会多出一个黑框（实测：新建的独立控制台，不是继承）。
# 所以快捷方式指向基础 pythonw.exe，这里再把 MinerU 环境的包挂进来。
# 用 MINERU_ROOT 覆盖 MinerU 安装位置（默认见 mineru_gui/config.py）。
DEFAULT_VENV_SITE = str(
    Path(os.environ.get('MINERU_ROOT') or r'%MINERU_ROOT%')
    / '.venv' / 'Lib' / 'site-packages')


def _venv_site_candidates():
    yield DEFAULT_VENV_SITE
    try:                                    # 从 settings.json 里的 mineru-kit 反推
        import json
        cfg = APP_DIR / 'settings.json'
        kit = json.loads(cfg.read_text(encoding='utf-8')).get('mineru_kit', '')
        if kit:
            yield str(Path(kit).resolve().parent.parent / 'Lib' / 'site-packages')
    except Exception:
        pass


def ensure_venv_packages() -> None:
    """用基础解释器启动时，把 MinerU 环境的 site-packages 追加进 sys.path。

    只有真的要用基础解释器跑时才生效（sys.prefix == sys.base_prefix）；
    用 venv 的 python 跑时什么也不做。
    用 append 而不是 insert，保证标准库优先。
    """
    if sys.prefix != sys.base_prefix:
        return
    for cand in _venv_site_candidates():
        if cand and os.path.isdir(cand) and cand not in sys.path:
            sys.path.append(cand)
            return


def fix_tcl() -> None:
    base = Path(sys.base_prefix)
    for var, sub in (('TCL_LIBRARY', 'tcl/tcl8.6'), ('TK_LIBRARY', 'tcl/tk8.6')):
        if os.environ.get(var):
            continue
        p = base / sub
        if p.is_dir():
            os.environ[var] = str(p)


def main() -> int:
    fix_tcl()
    ensure_venv_packages()

    args = sys.argv[1:]
    if args and args[0] == '--selftest':
        return _selftest(args[1:])
    if args and args[0] == '--uicheck':
        return _uicheck()
    if args and args[0] == '--check':
        return _check(args[1:])
    if args and args[0] == '--probe':
        return _probe(args[1:])

    try:
        from mineru_gui.ui import main as ui_main
        ui_main()
    except Exception:
        # 用 pythonw 启动时没有控制台，出错也得让人看见
        import traceback
        msg = traceback.format_exc()
        print(msg, file=sys.stderr)
        try:
            import tkinter
            from tkinter import messagebox
            r = tkinter.Tk()
            r.withdraw()
            messagebox.showerror('启动失败', msg[-1800:])
            r.destroy()
        except Exception:
            pass
        return 1
    return 0


def _selftest(args: list[str]) -> int:
    """不开界面跑一遍真实流水线，用来在没有显示器/不方便点界面时验证。"""
    from mineru_gui.config import Settings
    from mineru_gui.runner import Job, Runner

    if not args:
        print('用法: python run.py --selftest <输入文件> [输出目录]')
        return 2
    src = Path(args[0])
    if not src.exists():
        print('找不到输入文件：%s' % src)
        return 2
    out_dir = Path(args[1]) if len(args) > 1 else Path(__file__).parent / '_selftest_out'
    out_dir.mkdir(parents=True, exist_ok=True)

    s = Settings.load()
    s.output_dir = str(out_dir)
    s.tier = 'flash'            # 自检用最快档位
    s.ocr_mode = 'txt'
    s.skip_existing = False
    s.auto_check = True
    s.auto_fix = True

    errs = s.validate()
    if errs:
        print('环境校验未通过：')
        for e in errs:
            print('  -', e)
        return 2

    print('mineru-kit :', s.mineru_kit)
    print('MINERU_HOME:', s.mineru_home)
    print('输入       :', src)
    print('输出目录   :', out_dir)
    print('档位       :', s.tier, '/ OCR:', s.ocr_mode)
    print('-' * 60)

    runner = Runner(s, print_ev)
    job = Job(src=src, index=0, pages=None)
    runner.start([job])
    runner.join(timeout=s.per_file_timeout_sec + 60)

    print('-' * 60)
    print('状态  :', job.status)
    print('输出  :', job.out)
    print('用时  : %.1f 秒' % job.seconds)
    print('体检  : %s' % ', '.join('%s/%s' % (f.level, f.title) for f in job.findings))
    ok = job.status == 'done' and job.out and Path(job.out).exists()
    print('结果  :', '通过' if ok else '失败')
    return 0 if ok else 1


def print_ev(ev: dict) -> None:
    t = ev.get('type')
    if t == 'log':
        print(ev['text'])
    elif t == 'job':
        print('[状态] %s %s' % (ev['status'], ev['message']))
    elif t == 'all_done':
        print('[结束] 成功 %d 跳过 %d 失败 %d' % (ev['ok'], ev['skip'], ev['fail']))


def _check(args: list[str]) -> int:
    """命令行体检：python run.py --check 原文.pdf 输出.md [--clean]"""
    from pathlib import Path as _P
    from mineru_gui import checker

    clean_it = '--clean' in args
    args = [a for a in args if a != '--clean']
    if len(args) < 2:
        print('用法: python run.py --check <原文.pdf> <输出.md> [--clean]')
        return 2
    pdf, md = _P(args[0]), _P(args[1])
    if not md.exists():
        print('找不到 %s' % md)
        return 2

    findings = checker.check(pdf, md)
    print('=' * 64)
    print('体检 %s' % md.name)
    print('=' * 64)
    for f in findings:
        mark = {'error': '[严重]', 'warn': '[警告]', 'info': '[信息]'}[f.level]
        print('%s %s' % (mark, f.title))
        print('       %s' % f.detail)
    print('-' * 64)
    print(checker.summarize(findings))

    if clean_it and any(f.level in ('error', 'warn') for f in findings):
        r = checker.clean(md)
        print()
        print('已清理：details %d、mermaid %d、公式 %d 处'
              % (r['details_removed'], r['mermaid_removed'], r['formulas_fixed']))
        if r['tables_removed']:
            print('        顺带清掉了 %d 个被编造在 <details> 里的假表格，剩 %d 个表'
                  % (r['tables_removed'], r['tables_left']))
        after = checker.check(pdf, md)
        print('清理后：%s' % checker.summarize(after))

    return 1 if any(f.level == 'error' for f in findings) else 0


def _probe(args: list[str]) -> int:
    """探测输入：python run.py --probe <文件...>

    打印每个文件的页数，以及 --ocr-mode auto 会判定成 txt 还是 ocr。
    判定用的是 MinerU 自己那个函数，所以结果就是实际会用的模式。
    """
    from pathlib import Path as _P
    from mineru_gui import probe

    if not args:
        print('用法: python run.py --probe <文件...>')
        return 2
    print('%-46s %6s  %-10s %s' % ('文件', '页数', 'auto 判定', '说明'))
    print('-' * 96)
    rc = 0
    for a in args:
        p = _P(a)
        if not p.exists():
            print('%-46s %6s  %-10s %s' % (p.name[:44], '-', '-', '文件不存在'))
            rc = 2
            continue
        pages = probe.page_count(p)
        mode = probe.classify_ocr_mode(p)
        print('%-46s %6s  %-10s %s' % (
            p.name[:44], pages if pages else '-',
            mode if mode else '-', probe.describe(p)))
    return rc


def _uicheck() -> int:
    """构建界面并跑一遍真实交互（加文件 → 等探测回报 → 渲染行），然后退出。

    只构建窗口是不够的：添加文件 / 刷新队列这些路径的缺陷必须真的走一遍。
    """
    import time
    from pathlib import Path as _P
    from mineru_gui.config import Settings
    from mineru_gui.ui import App

    app = App(Settings.load())
    app.update_idletasks()
    app.update()
    print('界面构建成功：%s' % app.title())

    samples = [p for p in (_P(__file__), _P(__file__).with_name('README.md')) if p.exists()]
    app._append(samples)
    # 首次导入 docvortex/pdfium 可能要几秒（冷启动还会重编译 pyc），给足时间
    deadline = time.time() + 25
    while time.time() < deadline:
        app.update()
        time.sleep(0.05)
        if all(j.auto_mode for j in app.jobs):
            break

    rows = app.tree.get_children()
    print('队列渲染成功：%d 行（样例 %d 个，探测耗时 %.1f 秒）'
          % (len(rows), len(samples), 25 - max(0.0, deadline - time.time())))
    bad = [j.name for j in app.jobs if not j.auto_mode]
    if bad:
        print('探测未回报：%s' % bad)
        app.destroy()
        return 1

    for i in rows:
        print('   行%s = %s' % (i, app.tree.item(i, 'values')))

    # ---- 拖放：投递一条真实的 WM_DROPFILES，验证从窗口过程一路进到队列 ----
    if not _dropcheck(app):
        app.destroy()
        return 1

    app.destroy()
    print('交互自检通过')
    return 0


def _dropcheck(app) -> bool:
    """在真实 App 上模拟一次文件拖放（走 win32 消息，不是直接调回调）。"""
    import ctypes
    import struct
    import time
    from ctypes import wintypes
    from pathlib import Path as _P

    from mineru_gui import dnd

    if not dnd.available():
        print('拖放：非 Windows，跳过')
        return True
    if not getattr(app, '_drop', None) or not app._drop.ok:
        print('拖放：安装失败（%s）' % getattr(app._drop, 'reason', '?'))
        return False
    print('拖放：已安装，登记 %d 个窗口句柄' % len(app._drop.hwnds))

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    u32 = ctypes.WinDLL('user32', use_last_error=True)
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    def make_hdrop(paths):
        payload = ('\0'.join(str(p) for p in paths) + '\0\0').encode('utf-16-le')
        blob = struct.pack('<IiiII', 20, 0, 0, 0, 1) + payload
        h = k32.GlobalAlloc(0x0002 | 0x0040, len(blob))
        ptr = k32.GlobalLock(h)
        ctypes.memmove(ptr, blob, len(blob))
        k32.GlobalUnlock(h)
        return h

    def post(paths):
        before = len(app.jobs)
        hdrop = make_hdrop(paths)
        u32.SendMessageW(wintypes.HWND(app._drop.hwnds[0]), dnd.WM_DROPFILES,
                         wintypes.WPARAM(hdrop), 0)
        deadline = time.time() + 5
        while time.time() < deadline and len(app.jobs) == before:
            app.update()
            time.sleep(0.02)
        return len(app.jobs) - before

    # 1) 格式不支持的文件：应当被挡在门外，队列不变
    n = post([_P(__file__)])                      # run.py 不是可解析格式
    if n != 0:
        print('拖放：不支持格式本应被拒，队列却 +%d' % n)
        return False
    print('拖放：不支持格式已正确拒绝（run.py 不在可解析集合里）')

    # 2) 拖一个文件夹：应递归展开出里面的 icon.png
    assets = _P(__file__).with_name('assets')
    if not assets.is_dir():
        print('拖放：缺少测试目录 %s' % assets)
        return False
    n = post([assets])
    if n != 1:
        print('拖放：拖入文件夹后队列应 +1（assets 里的 icon.png），实际 +%d' % n)
        return False
    print('拖放：拖入文件夹后递归展开 +1，末项 = %s' % app.jobs[-1].name)

    # 3) 再拖同一个文件：应被去重，队列不变
    n = post([assets / 'icon.png'])
    if n != 0:
        print('拖放：重复文件本应去重，队列却 +%d' % n)
        return False
    print('拖放：重复文件已去重')

    print('拖放提示条 = %s' % app.lbl_drop.cget('text').splitlines()[0])
    return True


if __name__ == '__main__':
    sys.exit(main())
