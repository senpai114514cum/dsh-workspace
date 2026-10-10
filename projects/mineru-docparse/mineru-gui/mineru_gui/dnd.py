r"""Windows 原生文件拖放（零依赖，纯 ctypes）。

为什么不用 tkinterdnd2
----------------------
它需要加载 tkdnd 这个 Tcl 扩展包。而本机 Python 3.13 的 Tcl 运行库路径本来就没被
正确编入（run.py 的 fix_tcl() 得手工补 TCL_LIBRARY / TK_LIBRARY 才能建窗口），
再叠一层 Tcl 包加载容易出问题，也会给部署多一个依赖。

这里直接用 Win32 的 WM_DROPFILES：调用 DragAcceptFiles 把窗口登记成放置目标，
再用 SetWindowLongPtr 子类化窗口过程拦下 WM_DROPFILES，取路径用 DragQueryFileW。
和 Tk 的交互只有"给窗口挂一个回调"，出问题时能整体降级成"拖放不可用"，
不会影响其它功能。

平台边界
--------
仅 Windows 可用。其它平台 available() 返回 False，界面会隐藏拖放提示。
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4
GWLP_USERDATA = -21

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

_IS_WINDOWS = sys.platform == 'win32'


def available() -> bool:
    """当前平台能不能用原生拖放。"""
    return _IS_WINDOWS


if _IS_WINDOWS:
    _user32 = ctypes.WinDLL('user32', use_last_error=True)
    _shell32 = ctypes.WinDLL('shell32', use_last_error=True)

    _shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    _shell32.DragAcceptFiles.restype = None
    _shell32.DragQueryFileW.argtypes = [
        wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    _shell32.DragQueryFileW.restype = wintypes.UINT
    _shell32.DragFinish.argtypes = [wintypes.HANDLE]
    _shell32.DragFinish.restype = None

    _user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
        wintypes.WPARAM, wintypes.LPARAM]
    _user32.CallWindowProcW.restype = LRESULT
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND

    # 32 位系统没有 ...Ptr 版本，按指针宽度选
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        _get_wndproc = _user32.GetWindowLongPtrW
        _set_wndproc = _user32.SetWindowLongPtrW
    else:
        _get_wndproc = _user32.GetWindowLongW
        _set_wndproc = _user32.SetWindowLongW
    _get_wndproc.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_wndproc.restype = ctypes.c_void_p
    _set_wndproc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    _set_wndproc.restype = ctypes.c_void_p


def _query_paths(hdrop) -> list[str]:
    """从一个 HDROP 里取出所有路径。"""
    count = _shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
    out = []
    for i in range(count):
        need = _shell32.DragQueryFileW(hdrop, i, None, 0)
        buf = ctypes.create_unicode_buffer(need + 1)
        _shell32.DragQueryFileW(hdrop, i, buf, need + 1)
        if buf.value:
            out.append(buf.value)
    return out


class DropTarget:
    """把一个 Tk 控件变成文件放置目标。

    用法::

        self._drop = DropTarget(self.root, self._on_drop)

    `on_drop(paths)` 会在**空闲时**被调用（不是直接在窗口过程里），
    避免在窗口过程内部重入 Tk 造成状态错乱。
    """

    def __init__(self, widget, on_drop):
        self.widget = widget
        self.on_drop = on_drop
        self.hwnds: list[int] = []
        self.ok = False
        self.reason = ''
        self._hooks: list[tuple[int, int, WNDPROC]] = []      # (hwnd, oldproc, newproc)
        if not _IS_WINDOWS:
            self.reason = '仅 Windows 支持原生拖放'
            return
        try:
            self._install()
            self.ok = True
        except Exception as exc:                              # 拖放失败不能拖垮界面
            self.reason = '%s: %s' % (type(exc).__name__, exc)

    # ---------------------------------------------------------------- 安装
    def _install(self) -> None:
        widget = self.widget
        widget.update_idletasks()                             # 确保窗口真的建出来了
        inner = int(widget.winfo_id())
        targets = [inner]
        parent = _user32.GetParent(inner)
        # Tk 的顶层窗口外面还套了一层 wrapper 窗口，边框区域属于它；
        # 两个都登记，拖到哪儿都能收到。
        if parent and int(parent) != inner:
            targets.append(int(parent))

        self._proc = WNDPROC(self._wndproc)                   # 必须留引用，否则被 GC
        for hwnd in targets:
            _shell32.DragAcceptFiles(hwnd, True)
            old = _get_wndproc(hwnd, GWLP_WNDPROC)
            _set_wndproc(hwnd, GWLP_WNDPROC, ctypes.cast(self._proc, ctypes.c_void_p))
            self._hooks.append((hwnd, old, self._proc))
            self.hwnds.append(hwnd)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            try:
                paths = _query_paths(wparam)
            except Exception:
                paths = []
            finally:
                try:
                    _shell32.DragFinish(wparam)
                except Exception:
                    pass
            if paths:
                # 不在窗口过程里直接碰 Tk，排到空闲时执行
                try:
                    self.widget.after_idle(lambda: self._deliver(paths))
                except Exception:
                    pass
            return 0
        old = next((o for h, o, _ in self._hooks if h == hwnd), None)
        if old:
            return _user32.CallWindowProcW(old, hwnd, msg, wparam, lparam)
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _deliver(self, paths: list[str]) -> None:
        try:
            self.on_drop(paths)
        except Exception:
            pass

    def close(self) -> None:
        """把窗口过程还原回去（关闭窗口前调用）。"""
        for hwnd, old, _ in self._hooks:
            try:
                _set_wndproc(hwnd, GWLP_WNDPROC, old)
                _shell32.DragAcceptFiles(hwnd, False)
            except Exception:
                pass
        self._hooks.clear()


# ---------------------------------------------------------------- 路径展开

def expand_paths(paths, supported_ext) -> tuple[list[Path], list[Path], int]:
    """把拖进来的路径展开成待转换的文件列表。

    文件夹会**递归**扫描，只保留 supported_ext 里的格式（大小写不敏感）。

    返回 (文件列表, 不支持的文件, 扫描过的文件夹数)

    排序规则：同一批里先按传入顺序，文件夹内部按路径字典序 —— 这样拖多个文件夹时
    顺序是可预期的。
    """
    files: list[Path] = []
    unsupported: list[Path] = []
    n_dirs = 0
    seen: set[Path] = set()

    for raw in paths:
        try:
            p = Path(raw)
        except Exception:
            continue
        if p.is_dir():
            n_dirs += 1
            try:
                found = sorted(q for q in p.rglob('*')
                               if q.is_file() and q.suffix.lower() in supported_ext)
            except OSError:
                found = []
            for q in found:
                if q not in seen:
                    seen.add(q)
                    files.append(q)
        elif p.is_file():
            if p.suffix.lower() in supported_ext:
                if p not in seen:
                    seen.add(p)
                    files.append(p)
            else:
                unsupported.append(p)
        # 其它情况（不存在的路径、特殊文件）静默忽略

    return files, unsupported, n_dirs


def describe_drop(paths, supported_ext) -> str:
    """给日志用的一句话描述。"""
    files, unsupported, n_dirs = expand_paths(paths, supported_ext)
    bits = []
    if n_dirs:
        bits.append('%d 个文件夹' % n_dirs)
    n_top = len(paths) - n_dirs
    if n_top:
        bits.append('%d 个文件' % n_top)
    head = '拖入 ' + ' + '.join(bits or ['0 项'])
    tail = '，得到 %d 个待转换文件' % len(files)
    if unsupported:
        tail += '（%d 个格式不支持，已忽略）' % len(unsupported)
    return head + tail
