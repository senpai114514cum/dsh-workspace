"""拖放功能自检。

分两层：
  1. 纯逻辑：文件夹展开、格式过滤、去重、顺序
  2. 真消息：在全局内存里造一个真正的 DROPFILES 结构，用 SendMessageW 投递
     WM_DROPFILES 给窗口，验证窗口过程钩子确实收到并解析出路径

第 2 层是关键 —— 它不是"调用一下回调函数"，而是走完整的 Win32 消息通路。
"""
from __future__ import annotations

import ctypes
import shutil
import struct
import sys
import time
from ctypes import wintypes
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

# 不用系统临时目录：沙箱下在 %TEMP% 里建子目录会被拒（WinError 5）
SCRATCH = APP_DIR / '_dndtest'
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)

import run as launcher                                    # noqa: E402
launcher.fix_tcl()
launcher.ensure_venv_packages()

from mineru_gui import dnd                                # noqa: E402
from mineru_gui.config import SUPPORTED_EXT               # noqa: E402

fails: list[str] = []


def expect(cond, label):
    print('  %s %s' % ('[OK]' if cond else '[!!]', label))
    if not cond:
        fails.append(label)


def _mainloop_probe() -> int:
    """在**真实 mainloop** 下投递一次拖放。

    这一项必须单独跑，而且必须走 mainloop 而不是 update()：
    窗口过程里若调用任何 Tk 函数，Tcl 派发消息时 GIL 已释放，会直接
    Fatal Python error（实测踩过）。而 update() 是在 Python 调用栈内
    同步派发、GIL 一直在手上，**测不出这个崩溃**。所以这里单独进程 + mainloop。
    """
    import ctypes
    import struct
    import time
    from ctypes import wintypes

    import tkinter as tk

    from mineru_gui import dnd

    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _u32 = ctypes.WinDLL('user32', use_last_error=True)
    _k32.GlobalAlloc.restype = wintypes.HGLOBAL
    _k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _k32.GlobalLock.restype = ctypes.c_void_p
    _k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    root = tk.Tk()
    root.geometry('240x120')
    got: list[list[str]] = []
    target = dnd.DropTarget(root, lambda p: got.append(list(p)))
    if not target.ok:
        print('安装失败: %s' % target.reason)
        root.destroy()
        return 1

    def drop():
        png = APP_DIR / 'assets' / 'icon.png'
        payload = ('\0'.join([str(png)]) + '\0\0').encode('utf-16-le')
        blob = struct.pack('<IiiII', 20, 0, 0, 0, 1) + payload
        h = _k32.GlobalAlloc(0x0002 | 0x0040, len(blob))
        ptr = _k32.GlobalLock(h)
        ctypes.memmove(ptr, blob, len(blob))
        _k32.GlobalUnlock(h)
        _u32.PostMessageW(wintypes.HWND(target.hwnds[0]), dnd.WM_DROPFILES,
                          wintypes.WPARAM(h), 0)

    root.after(250, drop)
    root.after(2200, root.quit)
    t0 = time.time()
    root.mainloop()                     # ← 关键：真 mainloop，不是 update()
    elapsed = time.time() - t0
    print('mainloop 正常退出，用时 %.1f 秒，收到 %d 次' % (elapsed, len(got)))
    target.close()
    root.destroy()
    if not got:
        print('未收到拖放')
        return 1
    print('OK %s' % Path(got[0][0]).name)
    return 0


# 子进程模式：只跑 mainloop 探测，绝不执行下面的父测试
if '--mainloop' in sys.argv:
    sys.exit(_mainloop_probe())


# ============================================================ 1. 纯逻辑
print('=== expand_paths：文件夹递归展开与格式过滤 ===')
TMP = SCRATCH / 'tree'
try:
    (TMP / 'sub' / 'deep').mkdir(parents=True)
    (TMP / 'a.pdf').write_text('x')
    (TMP / 'b.DOCX').write_text('x')          # 大写扩展名
    (TMP / 'skip.txt').write_text('x')        # txt 不可解析
    (TMP / 'sub' / 'c.png').write_text('x')
    (TMP / 'sub' / 'deep' / 'd.epub').write_text('x')
    (TMP / 'sub' / 'note.md').write_text('x')

    files, unsupported, ndirs = dnd.expand_paths([str(TMP)], SUPPORTED_EXT)
    names = sorted(f.name for f in files)
    expect(ndirs == 1, '识别出 1 个文件夹')
    expect(names == ['a.pdf', 'b.DOCX', 'c.png', 'd.epub'],
           '递归拿到 4 个支持的文件（含大写扩展名），实际 %s' % names)
    expect(all(f.name not in ('skip.txt', 'note.md') for f in files),
           'txt/md 未被当作可解析文件（它们是 INGESTIBLE 但不是 PARSEABLE）')

    only = TMP / 'sub'
    files2, _, _ = dnd.expand_paths([str(only)], SUPPORTED_EXT)
    expect(sorted(f.name for f in files2) == ['c.png', 'd.epub'],
           '只扫子目录时拿到 2 个')

    # 混合拖入：文件 + 文件夹 + 不支持的 + 不存在的
    (TMP / 'z.pdf').write_text('x')
    mixed, unsup, nd = dnd.expand_paths(
        [str(TMP / 'z.pdf'), str(TMP / 'skip.txt'), str(TMP / 'nope.pdf'), str(TMP)],
        SUPPORTED_EXT)
    expect(len(mixed) == 5, '混合拖入得到 5 个文件，实际 %d' % len(mixed))
    expect(len(unsup) == 1 and unsup[0].name == 'skip.txt', '不支持的单独列出')
    expect(nd == 1, '文件夹计数为 1')

    # 去重：同一个文件通过两条路径进来只算一次
    dup, _, _ = dnd.expand_paths([str(TMP / 'a.pdf'), str(TMP / 'a.pdf'), str(TMP)],
                                 SUPPORTED_EXT)
    expect(sum(1 for f in dup if f.name == 'a.pdf') == 1, '同一文件不会重复入列')

    print()
    print('=== describe_drop ===')
    msg = dnd.describe_drop([str(TMP / 'a.pdf'), str(TMP)], SUPPORTED_EXT)
    expect('文件夹' in msg and '得到' in msg, '描述含文件夹与结果：%s' % msg)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

# ============================================================ 2. 真实消息
print()
print('=== 真实 WM_DROPFILES 消息投递 ===')
if not dnd.available():
    print('  （跳过：非 Windows）')
else:
    import tkinter as tk

    WM_DROPFILES = dnd.WM_DROPFILES
    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _u32 = ctypes.WinDLL('user32', use_last_error=True)
    _k32.GlobalAlloc.restype = wintypes.HGLOBAL
    _k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _k32.GlobalLock.restype = ctypes.c_void_p
    _k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    def make_hdrop(paths):
        """在全局内存里造一个真正的 DROPFILES 结构（fWide=1）。"""
        payload = ('\0'.join(str(p) for p in paths) + '\0\0').encode('utf-16-le')
        header = struct.pack('<IiiII', 20, 0, 0, 0, 1)   # pFiles=20, pt, fNC=0, fWide=1
        blob = header + payload
        h = _k32.GlobalAlloc(0x0002 | 0x0040, len(blob))  # GMEM_MOVEABLE|ZEROINIT
        ptr = _k32.GlobalLock(h)
        ctypes.memmove(ptr, blob, len(blob))
        _k32.GlobalUnlock(h)
        return h

    tmp2 = SCRATCH / 'msg'
    tmp2.mkdir(parents=True, exist_ok=True)
    try:
        f1 = tmp2 / 'drop1.pdf'
        f2 = tmp2 / 'drop2.pdf'
        f1.write_text('x')
        f2.write_text('x')

        root = tk.Tk()
        root.withdraw()
        got: list[list[str]] = []
        target = dnd.DropTarget(root, lambda paths: got.append(list(paths)))

        expect(target.ok, 'DropTarget 安装成功（%s）' % (target.reason or 'ok'))
        expect(len(target.hwnds) >= 1, '至少登记了 1 个窗口句柄，实际 %d' % len(target.hwnds))

        hwnd = target.hwnds[0]
        hdrop = make_hdrop([f1, f2])
        _u32.SendMessageW(wintypes.HWND(hwnd), WM_DROPFILES, wintypes.WPARAM(hdrop), 0)

        for _ in range(40):                       # 泵事件，等 after_idle 回调
            root.update()
            if got:
                break
            time.sleep(0.02)

        expect(len(got) == 1, '窗口过程收到 1 次拖放（实际 %d 次）' % len(got))
        if got:
            names = sorted(Path(p).name for p in got[0])
            expect(names == ['drop1.pdf', 'drop2.pdf'],
                   '解析出正确路径：%s' % names)

        # 再投一次，确认可重复
        got.clear()
        hdrop2 = make_hdrop([f1])
        _u32.SendMessageW(wintypes.HWND(hwnd), WM_DROPFILES, wintypes.WPARAM(hdrop2), 0)
        for _ in range(40):
            root.update()
            if got:
                break
            time.sleep(0.02)
        expect(len(got) == 1 and Path(got[0][0]).name == 'drop1.pdf',
               '二次拖放同样有效')

        # 非 WM_DROPFILES 消息必须继续传给原窗口过程，否则界面会失灵
        root.deiconify()
        root.update()
        alive = False
        try:
            root.title('dnd-probe')
            root.update()
            alive = root.title() == 'dnd-probe'
        except Exception:
            alive = False
        expect(alive, '钩子链式转发正常 —— 窗口其它消息未被吞掉')

        target.close()
        expect(not target._hooks, 'close() 已还原窗口过程')
        root.destroy()
    except Exception as exc:
        expect(False, '真实消息测试抛异常：%s: %s' % (type(exc).__name__, exc))
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

# ============================================================ 3. 真实 mainloop
print()
print('=== 真实 mainloop（单独子进程，崩溃不会带走整个自检）===')
if not dnd.available():
    print('  （跳过：非 Windows）')
else:
    import subprocess

    log = SCRATCH / '_mainloop.txt'
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with open(log, 'w', encoding='utf-8') as fh:
        # 不用管道（沙箱下会失败），输出重定向到文件
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--mainloop'],
                              stdout=fh, stderr=subprocess.STDOUT, timeout=60)
    text = log.read_text(encoding='utf-8', errors='replace')
    for line in text.strip().splitlines():
        print('    %s' % line)
    expect(proc.returncode == 0,
           'mainloop 下未崩溃（退出码 %d）%s'
           % (proc.returncode,
              '—— 窗口过程里是不是碰了 Tk？' if proc.returncode != 0 else ''))
    expect('OK icon.png' in text, 'mainloop 下拖放确实进入了回调')

print()
print('=' * 52)
print('失败项：%d' % len(fails))
for f in fails:
    print('  -', f)
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if fails else 0)