"""tkinter 图形界面。

界面只负责「收集参数 + 展示状态」，所有转换逻辑都在 runner 里。
新增设置项时，改 _build_settings_row 加一个控件、加进 _collect_settings 即可。
"""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, __version__
from . import checker, probe
from .config import (OCR_LABEL, OCR_MODES, SUPPORTED_EXT, TIER_LABEL, TIERS,
                     Settings, reject_reason)
from .runner import Job, Runner

STATUS_TEXT = {
    'pending': '等待中',
    'running': '转换中',
    'done': '完成',
    'failed': '失败',
    'skipped': '已跳过',
}
STATUS_TAG = {
    'pending': 'pending', 'running': 'running', 'done': 'done',
    'failed': 'failed', 'skipped': 'skipped',
}


class App(tk.Tk):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.jobs: list[Job] = []
        self.active: dict[int, Job] = {}
        self.events: queue.Queue = queue.Queue()
        self._probe_q: queue.Queue = queue.Queue()
        self.runner = Runner(settings, self.events.put)
        self._t0 = 0.0
        self._log_lines = 0
        self._last_progress_emit = 0.0

        # 页数与 auto 判定放后台探测，避免一次加几百个文件时界面卡住
        threading.Thread(target=self._probe_worker, daemon=True).start()

        self.title('%s v%s' % (APP_NAME, __version__))
        self.geometry('1120x780')
        self.minsize(940, 660)
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        self._build_ui()
        self._load_settings_into_ui()
        self.after(100, self._pump)
        self._log('就绪。先添加文件 → 选输出文件夹 → 开始转换。')
        warn = self.settings.validate()
        for w in warn:
            self._log('提示：%s' % w)

    # ================================================== 界面搭建

    def _build_ui(self) -> None:
        pad = dict(padx=8, pady=4)
        root = ttk.Frame(self)
        root.pack(fill='both', expand=True, padx=10, pady=8)

        # ---------- 输出文件夹 ----------
        f_out = ttk.LabelFrame(root, text='输出')
        f_out.pack(fill='x')
        self.var_out = tk.StringVar()
        ttk.Label(f_out, text='Markdown 输出到：').grid(row=0, column=0, sticky='w', **pad)
        e = ttk.Entry(f_out, textvariable=self.var_out)
        e.grid(row=0, column=1, sticky='ew', **pad)
        f_out.columnconfigure(1, weight=1)
        ttk.Button(f_out, text='选择文件夹…', command=self._pick_out).grid(row=0, column=2, **pad)
        ttk.Button(f_out, text='打开', width=6, command=self._open_out).grid(row=0, column=3, **pad)

        # ---------- 设置 ----------
        f_set = ttk.LabelFrame(root, text='解析设置')
        f_set.pack(fill='x', pady=(8, 0))

        self.var_tier = tk.StringVar()
        self.var_ocr = tk.StringVar()
        ttk.Label(f_set, text='档位：').grid(row=0, column=0, sticky='w', **pad)
        cb = ttk.Combobox(f_set, textvariable=self.var_tier, state='readonly', width=40,
                          values=[TIER_LABEL[t] for t in TIERS])
        cb.grid(row=0, column=1, sticky='w', **pad)

        ttk.Label(f_set, text='OCR 模式：').grid(row=0, column=2, sticky='w', **pad)
        cb2 = ttk.Combobox(f_set, textvariable=self.var_ocr, state='readonly', width=46,
                           values=[OCR_LABEL[m] for m in OCR_MODES])
        cb2.grid(row=0, column=3, sticky='w', **pad)

        self.var_noimg = tk.BooleanVar()
        self.var_check = tk.BooleanVar()
        self.var_fix = tk.BooleanVar()
        self.var_skip = tk.BooleanVar()
        self.var_imgs = tk.BooleanVar()

        row = ttk.Frame(f_set)
        row.grid(row=1, column=0, columnspan=4, sticky='w', **pad)
        ttk.Checkbutton(row, text='禁用图像分析（推荐）', variable=self.var_noimg).pack(side='left', padx=(0, 14))
        ttk.Checkbutton(row, text='转换后自动体检', variable=self.var_check).pack(side='left', padx=(0, 14))
        ttk.Checkbutton(row, text='自动清理', variable=self.var_fix).pack(side='left', padx=(0, 14))
        ttk.Checkbutton(row, text='跳过已存在的输出', variable=self.var_skip).pack(side='left')

        row2 = ttk.Frame(f_set)
        row2.grid(row=2, column=0, columnspan=4, sticky='w', **pad)
        ttk.Checkbutton(row2, text='图片抽成独立文件', variable=self.var_imgs).pack(side='left')
        ttk.Label(row2, foreground='#666',
                  text='（默认开。关闭则图片以 base64 内联进 md，会变成一大段"乱码"且体积暴增）'
                  ).pack(side='left', padx=(6, 0))

        ttk.Label(
            f_set, foreground='#666', justify='left',
            text='· standard 本身不做图像解读；advanced 会，实测会编造表格，选它时必须勾"禁用图像分析"。\n'
                 '· OCR 模式 auto = 由 MinerU 检查 PDF 文字层质量后自动决定用 txt 还是 ocr，'
                 '每个文件的结果显示在队列的「auto 判定」列。\n'
                 '· Office / HTML / CSV / EPUB / OFD 走原生解析，只能用 flash 档（会自动降档），该列显示为 -。'
        ).grid(row=3, column=0, columnspan=4, sticky='w', padx=8, pady=(2, 4))

        # ---------- 中间：左队列 右进度日志 ----------
        mid = ttk.Frame(root)
        mid.pack(fill='both', expand=True, pady=(8, 0))
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=2)
        mid.rowconfigure(0, weight=1)

        # 队列
        f_q = ttk.LabelFrame(mid, text='转换队列（按此顺序逐个处理）')
        f_q.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        f_q.rowconfigure(0, weight=1)
        f_q.columnconfigure(0, weight=1)

        cols = ('idx', 'name', 'pages', 'automode', 'status', 'time', 'note')
        tv = ttk.Treeview(f_q, columns=cols, show='headings', selectmode='extended')
        for c, t, w, anchor in [
            ('idx', '#', 36, 'center'), ('name', '文件名', 240, 'w'),
            ('pages', '页数', 50, 'center'), ('automode', 'auto 判定', 76, 'center'),
            ('status', '状态', 66, 'center'),
            ('time', '用时', 62, 'center'), ('note', '备注', 190, 'w'),
        ]:
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor=anchor, stretch=(c in ('name', 'note')))
        tv.grid(row=0, column=0, sticky='nsew', padx=6, pady=6)
        sb = ttk.Scrollbar(f_q, orient='vertical', command=tv.yview)
        sb.grid(row=0, column=1, sticky='ns', pady=6)
        tv.configure(yscrollcommand=sb.set)
        tv.tag_configure('done', foreground='#0a7d28')
        tv.tag_configure('failed', foreground='#c0392b')
        tv.tag_configure('running', foreground='#1a6fc4')
        tv.tag_configure('skipped', foreground='#888')
        self.tree = tv
        tv.bind('<Double-1>', lambda e: self._open_selected_output())

        bar = ttk.Frame(f_q)
        bar.grid(row=1, column=0, columnspan=2, sticky='ew', padx=6, pady=(0, 6))
        for text, cmd in [('添加文件…', self._add_files), ('添加文件夹…', self._add_folder),
                          ('移除选中', self._remove_selected), ('上移', lambda: self._move(-1)),
                          ('下移', lambda: self._move(1)), ('清空', self._clear)]:
            ttk.Button(bar, text=text, command=cmd).pack(side='left', padx=(0, 6))

        # 进度 + 日志
        f_r = ttk.LabelFrame(mid, text='进度')
        f_r.grid(row=0, column=1, sticky='nsew')
        f_r.rowconfigure(2, weight=1)
        f_r.columnconfigure(0, weight=1)

        self.pb = ttk.Progressbar(f_r, mode='determinate', maximum=100)
        self.pb.grid(row=0, column=0, sticky='ew', padx=8, pady=(8, 2))
        self.lbl_stat = ttk.Label(f_r, text='等待开始', font=('Microsoft YaHei UI', 9, 'bold'))
        self.lbl_stat.grid(row=1, column=0, sticky='w', padx=8)
        self.lbl_queue = ttk.Label(f_r, text='', foreground='#555')
        self.lbl_queue.grid(row=2, column=0, sticky='nw', padx=8)
        self.lbl_eta = ttk.Label(f_r, text='', foreground='#555')
        self.lbl_eta.grid(row=3, column=0, sticky='nw', padx=8)

        ttk.Label(f_r, text='运行日志：').grid(row=4, column=0, sticky='w', padx=8, pady=(6, 0))
        self.txt = tk.Text(f_r, height=16, wrap='none', font=('Consolas', 9),
                           background='#1e1e1e', foreground='#d4d4d4',
                           insertbackground='#d4d4d4')
        self.txt.grid(row=5, column=0, sticky='nsew', padx=8, pady=(0, 8))
        self.txt.configure(state='disabled')
        f_r.rowconfigure(5, weight=1)
        ys = ttk.Scrollbar(f_r, orient='vertical', command=self.txt.yview)
        ys.grid(row=5, column=1, sticky='ns', pady=(0, 8))
        self.txt.configure(yscrollcommand=ys.set)

        # ---------- 底部按钮 ----------
        f_b = ttk.Frame(root)
        f_b.pack(fill='x', pady=(8, 0))
        self.btn_start = ttk.Button(f_b, text='▶  开始转换', command=self._start)
        self.btn_start.pack(side='left')
        self.btn_stop = ttk.Button(f_b, text='■  停止', command=self._stop, state='disabled')
        self.btn_stop.pack(side='left', padx=8)
        ttk.Button(f_b, text='保存设置', command=self._save_settings).pack(side='right')
        self.lbl_hint = ttk.Label(f_b, text='', foreground='#c0392b')
        self.lbl_hint.pack(side='left', padx=16)

    # ================================================== 设置读写

    def _load_settings_into_ui(self) -> None:
        s = self.settings
        self.var_out.set(s.output_dir)
        self.var_tier.set(TIER_LABEL.get(s.tier, TIER_LABEL['standard']))
        self.var_ocr.set(OCR_LABEL.get(s.ocr_mode, OCR_LABEL['auto']))
        self.var_noimg.set(s.disable_image_analysis)
        self.var_check.set(s.auto_check)
        self.var_fix.set(s.auto_fix)
        self.var_skip.set(s.skip_existing)
        self.var_imgs.set(s.extract_images)

    def _collect_settings(self) -> None:
        s = self.settings
        s.output_dir = self.var_out.get().strip()
        s.tier = TIERS[[TIER_LABEL[t] for t in TIERS].index(self.var_tier.get())] \
            if self.var_tier.get() in [TIER_LABEL[t] for t in TIERS] else 'standard'
        s.ocr_mode = OCR_MODES[[OCR_LABEL[m] for m in OCR_MODES].index(self.var_ocr.get())] \
            if self.var_ocr.get() in [OCR_LABEL[m] for m in OCR_MODES] else 'auto'
        s.disable_image_analysis = bool(self.var_noimg.get())
        s.auto_check = bool(self.var_check.get())
        s.auto_fix = bool(self.var_fix.get())
        s.skip_existing = bool(self.var_skip.get())
        s.extract_images = bool(self.var_imgs.get())

    def _save_settings(self) -> None:
        self._collect_settings()
        self.settings.save()
        self._log('设置已保存到 settings.json')

    # ================================================== 队列操作

    def _add_files(self) -> None:
        types = [('支持的文档', ' '.join('*' + e for e in sorted(SUPPORTED_EXT))), ('所有文件', '*.*')]
        paths = filedialog.askopenfilenames(title='选择要转换的文件', filetypes=types)
        self._append([Path(p) for p in paths])

    def _add_folder(self) -> None:
        d = filedialog.askdirectory(title='选择文件夹（会递归扫描支持的格式）')
        if not d:
            return
        found = sorted(p for p in Path(d).rglob('*')
                       if p.is_file() and p.suffix.lower() in SUPPORTED_EXT)
        if not found:
            messagebox.showinfo('提示', '该文件夹里没有找到支持的文档格式。')
            return
        self._append(found)

    def _append(self, paths: list[Path]) -> None:
        exist = {j.src for j in self.jobs}
        added, rejected = [], []
        for p in paths:
            if p in exist:
                continue
            why = reject_reason(p)
            if why:
                rejected.append((p, why))
                continue
            self.jobs.append(Job(src=p, index=len(self.jobs)))
            exist.add(p)
            added.append(p)
        self._refresh_tree()
        if added:
            self._log('已添加 %d 个文件，队列共 %d 个。' % (len(added), len(self.jobs)))
            for p in added:
                self._probe_q.put(p)
        # 不能解析的文件在入口就拦掉，不要等到转换时才失败
        for p, why in rejected:
            self._log('已跳过 %s —— %s' % (p.name, why))
        if rejected:
            self.lbl_hint.config(
                text='已跳过 %d 个无法解析的文件（详见日志）' % len(rejected))

    def _selected_positions(self) -> list[int]:
        return sorted(self.tree.index(i) for i in self.tree.selection())

    def _remove_selected(self) -> None:
        for pos in reversed(self._selected_positions()):
            self.jobs.pop(pos)
        self._reindex()
        self._refresh_tree()

    def _move(self, delta: int) -> None:
        for pos in (self._selected_positions() if delta < 0 else reversed(self._selected_positions())):
            new = pos + delta
            if 0 <= new < len(self.jobs):
                self.jobs[pos], self.jobs[new] = self.jobs[new], self.jobs[pos]
        self._reindex()
        self._refresh_tree()

    def _clear(self) -> None:
        if self.jobs and not messagebox.askyesno('确认', '清空整个队列？'):
            return
        self.jobs.clear()
        self._refresh_tree()

    def _reindex(self) -> None:
        for i, j in enumerate(self.jobs):
            j.index = i

    @staticmethod
    def _row_values(j: Job, pos: int) -> tuple:
        return (
            pos + 1, j.name,
            j.pages if j.pages else '-',
            j.auto_mode if j.auto_mode else '…',
            STATUS_TEXT.get(j.status, j.status),
            ('%.0fs' % j.seconds) if j.seconds else '',
            j.message,
        )

    def _probe_worker(self) -> None:
        """后台线程：算页数 + 预测 auto 的 OCR 判定。"""
        while True:
            p = self._probe_q.get()
            if p is None:
                return
            try:
                pages = probe.page_count(p)
                mode = probe.classify_ocr_mode(p)
                self.events.put({'type': 'probe', 'path': str(p),
                                 'pages': pages, 'auto': mode or '-'})
            except Exception as e:
                self.events.put({'type': 'probe', 'path': str(p),
                                 'pages': None, 'auto': '-', 'error': str(e)[:60]})

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, j in enumerate(self.jobs):
            self.tree.insert('', 'end', iid=str(i),
                             values=self._row_values(j, i),
                             tags=(STATUS_TAG.get(j.status, ''),))
        self._update_queue_label()

    def _update_row(self, pos: int) -> None:
        if not self.tree.exists(str(pos)):
            return
        j = self.jobs[pos]
        self.tree.item(str(pos), values=self._row_values(j, pos),
                       tags=(STATUS_TAG.get(j.status, ''),))

    # ================================================== 运行

    def _start(self) -> None:
        if self.runner.running:
            return
        self._collect_settings()
        self.settings.save()
        errs = self.settings.validate()
        if errs:
            self.lbl_hint.config(text=errs[0])
            messagebox.showerror('无法开始', '\n'.join(errs))
            return
        if not self.jobs:
            messagebox.showinfo('提示', '队列是空的，先添加文件。')
            return
        self.lbl_hint.config(text='')
        Path(self.settings.output_dir).mkdir(parents=True, exist_ok=True)
        self._reindex()
        for j in self.jobs:                 # 重置状态
            j.status, j.progress, j.message, j.seconds, j.findings = 'pending', 0, '', 0.0, []
        self.active = {j.index: j for j in self.jobs}
        self._refresh_tree()
        self._t0 = time.time()
        self.pb['value'] = 0
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.lbl_stat.config(text='开始转换…')
        self._log('=' * 60)
        self._log('开始：共 %d 个文件，档位 %s，OCR %s，图像分析 %s'
                  % (len(self.jobs), self.settings.tier, self.settings.ocr_mode,
                     '禁用' if self.settings.disable_image_analysis else '开启'))
        self.runner.start(list(self.jobs))

    def _stop(self) -> None:
        if self.runner.running:
            self.runner.stop()
            self._log('已请求停止，等待当前文件收尾…')
            self.btn_stop.config(state='disabled')

    # ================================================== 事件循环

    def _pump(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                self._handle(ev)
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _handle(self, ev: dict) -> None:
        t = ev.get('type')
        if t == 'log':
            self._log(ev['text'])
        elif t == 'job':
            pos = ev['index']
            if pos < len(self.jobs):
                j = self.jobs[pos]
                j.status, j.message = ev['status'], ev['message']
                j.seconds, j.progress = ev['seconds'], ev['progress']
                self._update_row(pos)
                if ev['status'] == 'running':
                    self.lbl_stat.config(text='正在转换：%s' % j.name)
            self._update_overall()
        elif t == 'progress':
            pos = ev['index']
            if pos < len(self.jobs):
                self.jobs[pos].progress = ev['progress']
            self._update_overall()
        elif t == 'probe':
            for i, j in enumerate(self.jobs):
                if str(j.src) == ev['path']:
                    j.pages = ev.get('pages')
                    j.auto_mode = ev.get('auto') or '-'
                    self._update_row(i)
                    if j.auto_mode in ('txt', 'ocr'):
                        self._log('   %s  →  auto 判定用 %s 模式'
                                  % (j.name, '文字层(txt)' if j.auto_mode == 'txt'
                                     else 'OCR(ocr)'))
                    break
        elif t == 'all_done':
            self._finished(ev)

    def _update_overall(self) -> None:
        total = len(self.jobs) or 1
        done = sum(1 for j in self.jobs if j.status in ('done', 'failed', 'skipped'))
        cur = next((j for j in self.jobs if j.status == 'running'), None)
        frac = (cur.progress / 100.0) if cur else 0.0
        pct = (done + frac) / total * 100
        self.pb['value'] = pct
        remain = total - done
        if cur:
            text = '正在转换：%s（约 %d%%） · %d/%d 完成 · 剩余队列 %d' \
                   % (cur.name, cur.progress, done, total, remain)
        else:
            text = '%d/%d 完成 · 剩余队列 %d' % (done, total, remain)
        self.lbl_stat.config(text=text)
        self.lbl_queue.config(text='队列：等待 %d · 完成 %d · 跳过 %d · 失败 %d'
                              % (sum(1 for j in self.jobs if j.status == 'pending'),
                                 sum(1 for j in self.jobs if j.status == 'done'),
                                 sum(1 for j in self.jobs if j.status == 'skipped'),
                                 sum(1 for j in self.jobs if j.status == 'failed')))
        self._update_eta()

    def _update_eta(self) -> None:
        finished = [j for j in self.jobs if j.seconds > 0]
        remain = sum(1 for j in self.jobs if j.status in ('pending', 'running'))
        if finished and remain:
            avg = sum(j.seconds for j in finished) / len(finished)
            eta = avg * remain
            self.lbl_eta.config(text='已完成 %d 个，平均 %.0f 秒/个；预计剩余约 %s'
                                     % (len(finished), avg, _fmt(eta)))
        elif self.runner.running:
            self.lbl_eta.config(text='已完成 %d 个，正在估算剩余时间…' % len(finished))
        else:
            self.lbl_eta.config(text='')

    def _finished(self, ev: dict) -> None:
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.pb['value'] = 100 if ev['fail'] == 0 else self.pb['value']
        took = _fmt(time.time() - self._t0)
        self.lbl_stat.config(text='全部结束：成功 %d，跳过 %d，失败 %d，总耗时 %s'
                                  % (ev['ok'], ev['skip'], ev['fail'], took))
        self._log('=' * 60)
        self._log('全部结束：成功 %d，跳过 %d，失败 %d，总耗时 %s'
                  % (ev['ok'], ev['skip'], ev['fail'], took))
        bad = [j for j in self.jobs if j.status == 'failed']
        risky = [j for j in self.jobs
                 if any(f.level == 'error' for f in j.findings)]
        if bad:
            self._log('失败文件：%s' % '、'.join(j.name for j in bad))
        if risky:
            self._log('⚠ 体检有严重问题的文件（表格可能是编造的，请人工核对）：%s'
                      % '、'.join(j.name for j in risky))
        self._save_run_log()
        self._update_queue_label()

    def _save_run_log(self) -> None:
        """把本次运行的界面日志存到输出目录（带时间戳，不覆盖旧记录）。"""
        try:
            d = Path(self.settings.output_dir)
            d.mkdir(parents=True, exist_ok=True)
            name = time.strftime('_运行日志_%Y%m%d_%H%M%S.txt')
            (d / name).write_text(self.txt.get('1.0', 'end'), encoding='utf-8')
            self._log('本次运行日志已保存：%s' % name)
        except Exception as e:
            self._log('（运行日志保存失败：%s）' % str(e)[:60])

    def _update_queue_label(self) -> None:
        self.lbl_queue.config(text='队列共 %d 个文件' % len(self.jobs))

    # ================================================== 小工具

    def _pick_out(self) -> None:
        d = filedialog.askdirectory(title='选择 Markdown 输出文件夹')
        if d:
            self.var_out.set(d)

    def _open_out(self) -> None:
        d = self.var_out.get().strip()
        if d and Path(d).exists():
            os.startfile(d)
        else:
            messagebox.showinfo('提示', '输出文件夹还不存在。')

    def _open_selected_output(self) -> None:
        pos = self._selected_positions()
        if not pos:
            return
        j = self.jobs[pos[0]]
        if j.out and j.out.exists():
            os.startfile(str(j.out))
        elif j.src.exists():
            os.startfile(str(j.src))

    def _log(self, text: str) -> None:
        self.txt.configure(state='normal')
        self.txt.insert('end', text.rstrip() + '\n')
        self._log_lines += 1
        if self._log_lines > 4000:                     # 防止日志无限增长
            self.txt.delete('1.0', '500.0')
            self._log_lines -= 500
        self.txt.see('end')
        self.txt.configure(state='disabled')

    def _on_close(self) -> None:
        if self.runner.running:
            if not messagebox.askyesno('确认', '正在转换中，确定要退出吗？'):
                return
            self.runner.stop()
        self._collect_settings()
        self.settings.save()
        self.destroy()


def _fmt(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return '%d 秒' % sec
    if sec < 3600:
        return '%d 分 %d 秒' % (sec // 60, sec % 60)
    return '%d 小时 %d 分' % (sec // 3600, (sec % 3600) // 60)


def main() -> None:
    settings = Settings.load()
    App(settings).mainloop()
