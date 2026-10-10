# MinerU 批量转换器

按 [推荐工作流](../MinerU-消幻觉手册.md) 做的图形界面：选文件 → 排队 → 逐个转 md → 自动体检清理。

## 快速开始

**桌面上已有快捷方式「MinerU 批量转换器」，双击即可。**

也可以用工程自带的 **`启动.bat`**（等效）；出错时用 `调试启动.bat`，会保留控制台显示报错。

界面分四块：

| 区域 | 说明 |
|---|---|
| **输出** | 选择 Markdown 落到哪个文件夹，`打开` 按钮直接开资源管理器 |
| **解析设置** | 档位、OCR 模式、禁用图像分析、自动体检、自动清理、跳过已存在 |
| **转换队列** | 按列表顺序**逐个**处理；可添加文件/文件夹、移除、上移下移、清空、双击打开输出 |
| **进度 / 日志** | 总进度条、`已完成/剩余队列`、平均耗时与预计剩余时间、实时日志 |

默认设置已经是消幻觉推荐值：`standard` + `禁用图像分析` + `自动体检` + `自动清理`。

**队列顺序就是处理顺序**，上移/下移可以调整。

## 拖放添加文件 / 文件夹

**把文件或文件夹直接从资源管理器拖进窗口就能添加**，可以一次拖多个、文件和文件夹混着拖。

* 文件夹会**递归**扫描，只收支持的格式（大小写不敏感，`.PNG` 也认）
* 同一个文件重复拖入会自动去重
* 格式不支持的项目会在日志里逐个说明，不会静默吞掉
* 队列顶部那条提示会回显结果（`✓ 已从拖放添加 N 个文件`），5 秒后恢复成常驻说明
* 转换进行中拖入会被忽略，并在日志里提示

实现见 `mineru_gui/dnd.py`：**用的是 Win32 原生 `WM_DROPFILES`，零依赖**。

> 为什么不用 `tkinterdnd2`：它要加载 tkdnd 这个 Tcl 扩展包，而本机 Python 3.13 的
> Tcl 运行库路径本来就没被正确编入（`run.py` 的 `fix_tcl()` 得手工补 `TCL_LIBRARY`
> 才能建窗口），再叠一层 Tcl 包加载容易出问题。直接用 `DragAcceptFiles` +
> `SetWindowLongPtr` 子类化窗口过程，和 Tk 的交互只有"给窗口挂一个回调"这一处，
> 失败时能整体降级成"拖放不可用"，不影响任何其它功能。
>
> 仅 Windows 可用；其它平台提示条会显示"本平台不支持拖放"，按钮照常工作。

## 安全约定

**绝不覆盖已有文件。** 输出重名时：
* 勾选「跳过已存在的输出」→ 跳过该文件
* 不勾选 → 自动改名为 `名字 (2).md`

## 输出 md 里那一大段"乱码"是什么

有**两种**完全不同的成因，处理方式也不同。

### 成因 1：内联的 base64 图片（绝大多数情况）

`mineru-kit parse --format markdown`（默认）会把**每一张图**编码成 data URI 内联进 md：

```markdown
![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...几十万个字符...)
```

在编辑器里它就是一大段随机字符。实测（59 个产物）：

| 文件 | md 总字节 | 其中 base64 | 占比 |
|---|---|---|---|
| `pdf-15-cmyk.md` | 852,596 | 852,568 | **99.99%** |
| `p2-standard.md` | 1,913,539 | 1,862,108 | 97% |
| `研究背景.md` | 742,239 | 735,280 | 99% |

**34 / 59 个文件含内联图，合计 23.9 MB 是 base64。**

**处理**：勾选「图片抽成独立文件」（默认开）。程序把每张图解出来写到
`<名字>.assets/img_001_<哈希>.<ext>`，md 里改成相对路径引用；内容相同的图只存一份。
实测效果：

| 文件 | 处理前 | 处理后 |
|---|---|---|
| `pdf-15-cmyk.md` | 852.6 KB | **0.05 KB** + 624 KB jpg |
| `pdf-03-pdflatex-image.md` | 174.2 KB | **0.67 KB** + 127 KB jpg |
| `docx-01-with-images.md` | 41.6 KB | **0.29 KB** + 3 张图 |

> 另一条路是 `--format zip`：MinerU 本来就会输出 `images/` 目录 + 相对路径引用的
> md。但要解压 + 改写路径 + 处理多文档同名冲突，程序里选的是直接在 md 上做。

### 成因 2：PDF 文字层本身损坏（少见，但会毁掉内容）

实测 arXiv ResNet（1512.03385）的表格：

```
本应是：  3×3, 64
实际是：  33××33,, 6644          ← 每个字符原地重复了一遍
外加 U+F8EE 之类的私用区字形（symbol 字体缺 ToUnicode 映射）
```

体检会报「疑似文字层损坏（私用区 48 / 控制符 16 / 交错重复 8 处）」。

**处理**：把该文件的 OCR 模式改成 `ocr` 强制重跑。实测对比：

| | auto/txt（沿用坏文字层） | 强制 ocr |
|---|---|---|
| 单元格内容 | `33××33,, 6644×²` | `$\left[\begin{array}{c}3×3,64\\3×3,64\end{array}\right]×2$` |
| 交错重复 | 8 处 | **0 处** |
| 私用区 / 控制符 | 48 / 16 | **0 / 0** |

强制 OCR 读的是渲染后的像素，完全绕过坏文字层，还正确还原了堆叠单元格。

⚠️ **`auto` 在这类文档上会误判成 `txt`** —— 它的判定规则只检查"有没有文字、像不像乱码"
（字符数、Unicode 映射错误率、私用区比例等），不检查字符是否被重复交错。
所以这类损坏只能靠体检告警发现，不能指望 `auto` 自己躲开。

## 格式支持矩阵（照 `mineru/filetypes.py` 抄的，别凭印象改）

| 类型 | 扩展名 | 可用档位 | 备注 |
|---|---|---|---|
| PDF | `pdf` | flash / basic / standard / advanced | 唯一支持 `--pages` 的格式 |
| 图片 | `png` `jpg` `jpeg` `webp` `gif` `bmp` **`tiff`** `jp2` | 同上 | 内部会被包成单页 PDF |
| Office / ODF / RTF | `doc` `docx` `ppt` `pptx` `xls` `xlsx` `rtf` `odt` `ods` `odp` | **只能 flash** | 传别的档位直接报错退出 |
| 网页 / 电子书 | `html` `htm` `shtml` `mhtml` `mht` `epub` | **只能 flash** | |
| 表格 / 版式文档 | `csv` `tsv` `ofd` | **只能 flash** | |
| 纯文本 | `txt` `md` `rst` `tex` … | ✗ 不支持 | 只有文档库能读，命令行解析不支持 |

**三个容易踩的点**（都是实测踩出来的）：

1. **`flash-only` 格式必须用 `--tier flash`。** 传 `standard` 会立刻失败：
   ```
   错误: 解析 xxx.docx 失败: Tier 'standard' is only supported for PDF and
   image files; 'docx' files use tier 'flash'.
   ```
   本程序会按扩展名**自动降档**并在日志里说明（`config.effective_tier()`，
   等价于 MinerU 自己的 `batch_effective_parse_tier()`）。
2. **`.tiff` 支持，`.tif` 不支持** —— `IMAGE_EXTENSIONS` 里只有 `tiff`。
   同内容的 `.tif` 和 `.tiff` 实测一个失败一个成功。
3. **`.txt` / `.md` 不能被解析** —— 它们属于 `INGESTIBLE` 但不属于 `PARSEABLE`。
   这类文件在**添加时就被拦掉**并给出原因，不会等到转换才失败。

## OCR 模式：`auto` 是怎么判断的

`auto` 调用的就是 MinerU 内部用的那个函数（docvortex 的 `PDFDocument.classify()`），
在**原始 PDF 字节**上判定，**与档位无关**，结果只有 `txt` 或 `ocr`。

**抽样**：最多 10 页；总页数 ≤10 就用全部，否则均匀抽取（首尾都能取到）。

**判定顺序**——命中任意一条即判 `ocr`，全都不命中才判 `txt`：

| # | 条件 | 阈值 |
|---|---|---|
| 1 | 页数为 0 | — |
| 2 | 抽样页长宽比异常 | > 10:1 |
| 3 | **平均每页有效字符数太少**（≈ 没有文字层） | < 50 |
| 4 | PDFium Unicode 映射失败率 | ≥ 4% |
| 5 | 用了缺 ToUnicode 的 Identity CID 字体 | ≥30 字且 ≥1% |
| 6 | Latin CharSet 字体被解码成 CJK | ≥30 字、≥1%、CJK 占比 ≥80% |
| 7 | 异常字符比（NUL / U+FFFD / 控制符 / 私用区） | ≥3%（总字符 ≥300 时） |
| 8 | 可疑 U+7280–U+72DF 字符 | ≥30 个且占 CJK ≥2.6% |
| 9 | 跨脚本污染（希腊/西里尔/阿拉伯等混入） | 混入 ≥120 字、占比 ≥18%、≥3 个脚本块 |
| 10 | ASCII 标点密集（连续 ≥4 个标点、≥2 种） | 标点占比 ≥25%、连续段占比 ≥10% |
| 11 | 文字实际由图片承载 | 任一抽样页命中 |
| 12 | 判定过程抛异常 | 兜底判 `ocr` |

第 3 条是绝大多数扫描件被识别的路径；第 4~10 条针对的是**有文字层但抽出来是乱码**的情形
（中文 PDF 内嵌子集字体却缺 `/ToUnicode` 是最常见的）。

**两个容易踩的点**：

* **图片输入**会被包成单页 PDF 再走同一套判定（`mineru_parser.py:169`
  `PDFDocument.from_image(...)`）→ 必然没有文字层 → **必然判 `ocr`**。
* **Office / HTML / MHTML / CSV / EPUB / OFD** 是 flash-only 原生解析，
  **完全不接收 `--ocr-mode`**，设什么都被忽略。

界面上每个文件的判定结果显示在队列的 **「auto 判定」** 列（后台线程探测，不卡界面）。

## 命令行入口（同一套逻辑，可脚本化）

```powershell
$py = '%MINERU_ROOT%\.venv\Scripts\python.exe'

# 体检一个已有输出（返回 1 表示有严重问题，可接 CI）
& $py run.py --check 原文.pdf 输出.md
& $py run.py --check 原文.pdf 输出.md --clean     # 体检并清理

# 预测 auto 会选 txt 还是 ocr（不真的转换）
& $py run.py --probe 论文.pdf 扫描件.png 表格.xlsx

# 不开界面跑一遍真实流水线（自检 / 排查环境）
& $py run.py --selftest 某个.pdf

# 只构建界面然后退出
& $py run.py --uicheck

# 逻辑单元自检（不跑 MinerU）
& $py selftest_logic.py
```

## 目录结构

```
mineru-gui/
├─ 启动.bat / 调试启动.bat     启动器（纯 ASCII，避免代码页问题）
├─ run.py                      入口：TCL 修复 + venv 包挂载 + 分流到 GUI / 命令行
├─ selftest_logic.py           逻辑自检（约 50 项）
├─ selftest_images.py          图片抽取 + 乱码检测自检
├─ selftest_tables.py          表格计数自检（含误报回归用例）
├─ selftest_dnd.py             拖放自检（含真实 WM_DROPFILES 消息投递）
├─ selftest_flow.py            端到端：驱动真实 App 跑完整流程
├─ settings.json               设置持久化（自动生成）
├─ logs/                       每个文件的完整 MinerU 日志（自动生成）
├─ assets/
│   └─ icon.ico / icon.png     快捷方式图标（由 tools/make_icon.py 生成）
├─ tools/
│   ├─ make_icon.py            重新生成图标
│   └─ make_shortcut.ps1       重建桌面快捷方式（路径变了就重跑）
└─ mineru_gui/
   ├─ config.py    设置项、路径自动探测、环境变量注入
   ├─ checker.py   体检规则 + 清理（消幻觉）
   ├─ images.py    把内联 base64 图片抽成独立文件
   ├─ dnd.py       Windows 原生拖放（ctypes，零依赖）
   ├─ probe.py     页数与 auto OCR 判定探测
   ├─ runner.py    队列、流水线 Stage、子进程执行、进度解析
   └─ ui.py        tkinter 界面
```

## 怎么加新功能

三处扩展点，都不用动别的文件：

**1. 加一个流水线阶段**（比如"输出转 docx"、"上传到知识库"）

```python
# runner.py
class UploadStage(Stage):
    name = 'upload'
    def enabled(self, settings): return settings.extra.get('upload', False)
    def run(self, ctx):
        if ctx.job.status == 'done':
            ...                     # ctx.job.out / ctx.log / ctx.set_progress 都能用

PIPELINE = [ParseStage(), CheckStage(), CleanStage(), UploadStage()]
```

**2. 加一条体检规则**（比如"检查图片是否全部导出"）

```python
# checker.py
def _rule_images(pdf, md, tbs) -> Finding | None:
    ...
    return Finding('images', 'warn', '标题', '详情')

_RULES = [_rule_table_count, _rule_figure_blocks, _rule_tilde,
          _rule_formula_spacing, _rule_images]
```

**3. 加一个设置项**

在 `Settings` 里加字段 → 在 `ui.py` 的 `_build_settings_row` 附近加控件 →
在 `_collect_settings` 里读回来。懒得改界面就塞 `settings.extra`，Stage 里直接读。

## 环境说明

* 默认用 `%MINERU_ROOT%\.venv\Scripts\python.exe` 运行；路径可在 `settings.json` 里改。
* `MINERU_HOME` 自动探测（环境变量 → `%MINERU_ROOT%\home` → `~/.mineru`）。
* **TCL 修复**：本机 Python 3.13 的 Tcl 库路径没编进解释器，直接 `tkinter.Tk()` 会报
  `Can't find a usable init.tcl`。`run.py` 的 `fix_tcl()` 按 `sys.base_prefix`
  自动补 `TCL_LIBRARY` / `TK_LIBRARY`，无需手工设置。
* 子进程输出重定向到**日志文件**而不是管道，既避免了管道缓冲问题，也留下了可追溯的完整日志。

* **为什么快捷方式指向「基础 Python」的 pythonw.exe**（重要）：
  uv 建的 venv 里，`Scripts\pythonw.exe` 是**引导器**（247KB），它实际启动的是**控制台版
  `python.exe`**，所以双击会多出一个黑框。实测证据：该控制台上只挂着自己一个进程
  （`GetConsoleProcessList` 返回 1 个 PID），说明是新建的独立控制台，不是继承来的。
  基础 Python 的 `pythonw.exe` 才是真正的无控制台解释器（实测 `GetConsoleWindow = 0`）。
  因此快捷方式指向基础 `pythonw.exe`，由 `run.py` 的 `ensure_venv_packages()`
  把 venv 的 `site-packages` 追加进 `sys.path`（用 append，标准库优先），pypdf 等照常可用。

* **重建 / 修复快捷方式**（MinerU 环境或本工程挪了位置时）：
  ```powershell
  powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1
  ```
  脚本会从 `venv\pyvenv.cfg` 的 `home` 自动找基础 Python；找不到才退回 venv 自带的那个
  （会提示"多一个黑框"）。

* **换图标**：改 `tools/make_icon.py` 后重跑 `python tools\make_icon.py`，快捷方式无需重建
  （图标是路径引用，不是内嵌）。

## 已知限制

1. **超时**：单文件默认 1800 秒，可在 `settings.json` 里改 `per_file_timeout_sec`。
2. **停止**是"当前文件收尾后停"，不强杀子进程（避免留下半截输出）。
3. **页数**在添加文件时用 pypdf 读取，超大 PDF 可能有轻微卡顿。
4. **体检的表格数核对**需要 pypdf 能读出原文的表标题；非 PDF 输入会自动跳过这一项。
