"""任务队列与执行流水线。纯逻辑，不依赖界面，可单独测试。

流水线是可插拔的：`PIPELINE` 里放一串 Stage，按顺序对每个文件执行。
加新功能 = 写一个 Stage 子类加进 PIPELINE，不用动界面代码。
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import checker, images
from .config import LOG_DIR, Settings, effective_tier

ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
TQDM_PCT = re.compile(r'(\d{1,3})%\|')
PAGES_LINE = re.compile(r'pages=(\d+)')

# 这些行是进度条/下载噪声，只用来算进度，不进日志
NOISE = ('it/s]', 's/it]', 'Downloading:', 'Downloaded ', 'Prepared ', 'Installed ')

# 子进程不弹黑框
_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


# ---------------------------------------------------------------- 数据


@dataclass
class Job:
    src: Path
    index: int = 0
    status: str = 'pending'        # pending/running/done/failed/skipped
    out: Path | None = None
    seconds: float = 0.0
    message: str = ''
    progress: int = 0              # 0-100，当前文件（估算）
    findings: list = field(default_factory=list)
    pages: int | None = None
    auto_mode: str = ''            # ''=待探测, 'txt'/'ocr'=auto 会选它, '-'=不适用

    @property
    def name(self) -> str:
        return self.src.name


@dataclass
class Context:
    """传给 Stage 的上下文。"""
    job: Job
    settings: Settings
    log: Callable[[str], None]
    set_progress: Callable[[int], None]
    run_id: str = ''


class StopRequested(Exception):
    pass


# ---------------------------------------------------------------- 流水线阶段


class Stage:
    name = 'stage'

    def enabled(self, settings: Settings) -> bool:
        return True

    def run(self, ctx: Context) -> None:      # pragma: no cover - 抽象
        raise NotImplementedError


class ParseStage(Stage):
    """调用 mineru-kit parse 完成转换。"""

    name = 'parse'

    def run(self, ctx: Context) -> None:
        s = ctx.settings
        out = plan_output(ctx.job.src, s)
        if out is None:
            ctx.job.status = 'skipped'
            ctx.job.message = '输出已存在，已跳过'
            ctx.log('跳过（已存在同名输出）：%s' % ctx.job.src.name)
            return
        ctx.job.out = out
        out.parent.mkdir(parents=True, exist_ok=True)

        # 关键：flash-only 格式（Office/HTML/EPUB/CSV/ODT/OFD/RTF）只接受 flash，
        # 传其它档位 MinerU 会直接报错退出。这里按扩展名自动降档。
        tier = effective_tier(ctx.job.src, s.tier)
        if tier != s.tier:
            ctx.log('   %s 是 %s 格式，档位自动由 %s 降为 flash'
                    % (ctx.job.name, ctx.job.src.suffix.lstrip('.'), s.tier))

        cmd = [s.mineru_kit, 'parse', str(ctx.job.src), '-o', str(out),
               '--tier', tier, '--ocr-mode', s.ocr_mode]
        if s.disable_image_analysis:
            cmd.append('--disable-image-analysis')

        ctx.log('开始：%s  →  %s' % (ctx.job.name, out.name))
        ctx.log('命令：%s' % ' '.join(cmd[1:]))

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # 带批次时间戳，避免不同批次的同名文件互相覆盖日志
        logfile = LOG_DIR / ('%s_%03d_%s.log'
                             % (ctx.run_id or 'run', ctx.job.index, ctx.job.src.stem))
        started = time.time()

        with open(logfile, 'w', encoding='utf-8', errors='replace') as lf:
            proc = subprocess.Popen(
                cmd, stdout=lf, stderr=subprocess.STDOUT,
                env=s.build_env(), cwd=str(out.parent),
                creationflags=_NO_WINDOW)

            pos = 0
            timed_out = False
            while proc.poll() is None:
                if _STOP.is_set():
                    proc.terminate()
                    raise StopRequested()
                if time.time() - started > s.per_file_timeout_sec:
                    timed_out = True
                    proc.terminate()
                    break
                pos = _drain(logfile, pos, ctx)
                time.sleep(0.25)
            _drain(logfile, pos, ctx)

        ctx.job.seconds = time.time() - started

        if timed_out:
            ctx.job.status = 'failed'
            ctx.job.message = '超时（%d 秒）已终止' % s.per_file_timeout_sec
            return
        if proc.returncode != 0 or not out.exists():
            ctx.job.status = 'failed'
            ctx.job.message = '转换失败（退出码 %s）' % proc.returncode
            return
        ctx.job.status = 'done'
        ctx.job.progress = 100
        ctx.job.message = '完成 %.0f 秒' % ctx.job.seconds


class ExtractImagesStage(Stage):
    """把 md 里内联的 base64 图片抽成独立文件。

    实测默认的 markdown 格式会把每张图内联成 data URI，5 页文档就能产生
    1.8 MB 的"乱码"文本；抽出来之后 md 通常只剩几十 KB。
    """

    name = 'images'

    def enabled(self, settings: Settings) -> bool:
        return settings.extract_images

    def run(self, ctx: Context) -> None:
        if ctx.job.status != 'done' or not ctx.job.out:
            return
        r = images.extract_inline_images(ctx.job.out)
        if r['count']:
            ctx.log('   已抽出 %d 张内联图（去重后 %d 个文件）到 %s/；md 体积 %.2f MB → %.0f KB'
                    % (r['count'], r['unique'], Path(r['dir']).name,
                       r['before'] / 1048576, r['after'] / 1024))


class CheckStage(Stage):
    """对输出做消幻觉体检。"""

    name = 'check'

    def enabled(self, settings: Settings) -> bool:
        return settings.auto_check

    def run(self, ctx: Context) -> None:
        if ctx.job.status != 'done' or not ctx.job.out:
            return
        findings = checker.check(ctx.job.src, ctx.job.out)
        ctx.job.findings = findings
        ctx.log('%s：%s' % (ctx.job.name, checker.summarize(findings)))
        for f in findings:
            if f.level in ('error', 'warn'):
                ctx.log('   [%s] %s —— %s' % (f.level.upper(), f.title, f.detail))


class CleanStage(Stage):
    """按体检结果清理输出（原地）。"""

    name = 'clean'

    def enabled(self, settings: Settings) -> bool:
        return settings.auto_fix

    def run(self, ctx: Context) -> None:
        if ctx.job.status != 'done' or not ctx.job.out:
            return
        r = checker.clean(ctx.job.out)
        if r['changed']:
            bits = []
            if r['details_removed']:
                bits.append('删 details %d' % r['details_removed'])
            if r['mermaid_removed']:
                bits.append('删 mermaid %d' % r['mermaid_removed'])
            if r['prose_demoted']:
                bits.append('把 %d 个误包成公式的段落还原成正文' % r['prose_demoted'])
            if r['formulas_fixed']:
                bits.append('整理公式 %d 处' % r['formulas_fixed'])
            msg = '   已清理：' + '、'.join(bits or ['无改动'])
            if r['tables_removed']:
                msg += '；顺带清掉了 %d 个被编造在 <details> 里的假表格（剩 %d 个表）' \
                       % (r['tables_removed'], r['tables_left'])
            ctx.log(msg)
            ctx.job.findings = checker.check(ctx.job.src, ctx.job.out)


PIPELINE: list[Stage] = [ParseStage(), ExtractImagesStage(), CheckStage(), CleanStage()]


# ---------------------------------------------------------------- 工具


def plan_output(src: Path, s: Settings) -> Path | None:
    """决定输出路径；返回 None 表示跳过。绝不覆盖已有文件。"""
    out_dir = Path(s.output_dir)
    out = out_dir / ('%s.md' % src.stem)
    if not out.exists():
        return out
    if s.skip_existing:
        return None
    for i in range(2, 10000):
        cand = out_dir / ('%s (%d).md' % (src.stem, i))
        if not cand.exists():
            return cand
    return None


_STOP = threading.Event()


def _drain(logfile: Path, pos: int, ctx: Context) -> int:
    """读取日志新增内容：进度行只更新百分比，其余进日志。"""
    try:
        with open(logfile, 'r', encoding='utf-8', errors='replace') as f:
            f.seek(pos)
            chunk = f.read()
            newpos = f.tell()
    except Exception:
        return pos
    if not chunk:
        return newpos
    for raw in re.split(r'[\r\n]+', chunk):
        line = ANSI.sub('', raw).strip()
        if not line:
            continue
        m = TQDM_PCT.search(line)
        if m:
            pct = min(99, int(m.group(1)))
            if pct > ctx.job.progress:
                ctx.set_progress(pct)      # 进度条行不进日志，避免刷屏
            continue
        if any(n in line for n in NOISE):
            continue
        ctx.log('   ' + line)
    return newpos


# ---------------------------------------------------------------- 执行器


class Runner:
    """按给定顺序逐个执行任务；在后台线程里跑，通过 emit 回调上报。"""

    def __init__(self, settings: Settings, emit: Callable[[dict], None]):
        self.settings = settings
        self.emit = emit
        self._thread: threading.Thread | None = None

    # ---------- 对外 ----------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, jobs: list[Job]) -> None:
        if self.running:
            return
        _STOP.clear()
        self._thread = threading.Thread(
            target=self._run_all, args=(jobs,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        _STOP.set()

    def join(self, timeout: float | None = None) -> None:
        """等待当前批次结束（自检/退出时用）。"""
        if self._thread is not None:
            self._thread.join(timeout)

    # ---------- 内部 ----------

    def _run_all(self, jobs: list[Job]) -> None:
        ok = fail = skip = 0
        run_id = time.strftime('%m%d-%H%M%S')
        for job in jobs:
            if _STOP.is_set():
                break
            job.status = 'running'
            job.progress = 0
            self._emit_job(job)
            try:
                ctx = Context(
                    job=job, settings=self.settings, run_id=run_id,
                    log=lambda t, j=job: self.emit({'type': 'log', 'text': t}),
                    set_progress=lambda p, j=job: self._progress(j, p),
                )
                for stage in PIPELINE:
                    if not stage.enabled(self.settings):
                        continue
                    if _STOP.is_set():
                        raise StopRequested()
                    stage.run(ctx)
                if job.status == 'done':
                    ok += 1
                elif job.status == 'skipped':
                    skip += 1
                else:
                    fail += 1
            except StopRequested:
                job.status = 'pending'
                job.message = '已停止'
                self._emit_job(job)
                break
            except Exception as e:                      # 单个任务失败不拖垮整队
                job.status = 'failed'
                job.message = '异常：%s' % str(e)[:80]
                fail += 1
                self.emit({'type': 'log', 'text': '   [异常] %s' % job.message})
            self._emit_job(job)
        self.emit({'type': 'all_done', 'ok': ok, 'fail': fail, 'skip': skip})

    def _emit_job(self, job: Job) -> None:
        self.emit({
            'type': 'job', 'index': job.index, 'status': job.status,
            'message': job.message, 'seconds': job.seconds,
            'progress': job.progress, 'out': str(job.out) if job.out else '',
        })

    def _progress(self, job: Job, pct: int) -> None:
        job.progress = pct
        self.emit({'type': 'progress', 'index': job.index, 'progress': pct})
