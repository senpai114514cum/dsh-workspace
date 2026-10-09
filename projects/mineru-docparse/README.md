# MinerU 文档解析流水线（GUI + 实测报告）

把 PDF / Office / 图片批量转成 Markdown 的本地工具，带**幻觉检测**与**自动清理**，
以及配套的中英文实测报告。基于 [MinerU](https://github.com/opendatalab/MinerU) 4.0.11 +
`MinerU2.5-Pro-2605-1.2B`，在 Windows + NVIDIA 显卡上本地跑，不联网、不花钱。

```
mineru-docparse/
├── mineru-gui/         图形界面工具（tkinter）+ 回归测试
├── docs/               5 份实测报告（踩坑记录与结论）
└── setup/              部署脚本与独立体检工具
```

---

## 快速开始

前提：已按 `setup/deploy-mineru-gpu.ps1` 部署好 MinerU，或用环境变量指向现有部署。

```powershell
# 指定 MinerU 装在哪（默认 D:\MinerU-GPU）
$env:MINERU_ROOT = 'E:\AI\MinerU'

# 启动图形界面
cd mineru-gui
.\启动.bat
```

`启动.bat` 会自动从 venv 的 `pyvenv.cfg` 里找出基础 Python 的 `pythonw.exe` 来启动
（原因见 `mineru-gui/README.md`：uv 建的 venv 里那个 `pythonw.exe` 是个会拉起黑框的引导器）。

命令行也有几个入口：

```powershell
python run.py                      # 开图形界面
python run.py --uicheck            # 只构建界面然后退出（自检）
python run.py --selftest a.pdf     # 不开界面，跑完整流水线
python run.py --check a.pdf a.md   # 只体检已有产物
python run.py --probe a.pdf        # 只看页数与 auto OCR 判定
```

---

## 这个工具解决什么问题

MinerU 本身很强，但在实际批量使用时有三个坑，这个工具就是围着它们做的：

### 1. `advanced` 档会**编造表格**

实测：`mineru-kit parse --tier advanced` 会把曲线图"数字化"成假数据表，
报告里出现 133 个带 `~` 前缀的估算值（如 `~-0.068`），以及 7 个 `<details>` 图像解读块。

根因在 `mineru/backend/analysis/pdf/window.py:572` —— `image_analysis` 只在
`effort == "xhigh"`（即 `advanced` 档）时生效，`standard` 强制关闭。
**默认档位设为 `standard`**，并内置一批检测规则把这类产物揪出来。

### 2. 图片被内联成 base64，md 里出现一大段"乱码"

`--format markdown`（默认）会把每张图编码成 data URI 塞进 md。
实测 59 个产物里 34 个中招，合计 23.9 MB 是 base64；最极端的一个文件
852 KB 里 852 KB 全是 base64。

工具默认**把图片抽成独立文件**（`<名字>.assets/`），实测：

| 文件 | 处理前 | 处理后 |
|---|---|---|
| `pdf-15-cmyk.md` | 852.6 KB | **48 字节** + 624 KB jpg |
| `pdf-03-pdflatex-image.md` | 174.2 KB | **0.67 KB** + 127 KB jpg |

### 3. 有些 PDF 的**文字层本身是坏的**

实测 ResNet 论文（arXiv 1512.03385）的表格：

```
本应是：  3×3, 64
实际是：  33××33,, 6644          ← 每个字符原地重复了一遍
外加 U+F8EE 之类的私用区字形
```

`auto` 会把它判成 `txt`（因为字符数足够、看着不像乱码），于是沿用了坏文字层。
体检能识别出来并提示改用 `--ocr-mode ocr` 重跑 —— 实测强制 OCR 后
交错重复 8→0、私用区 48→0，还正确还原了堆叠单元格。

---

## 体检规则

`mineru-gui/mineru_gui/checker.py` 里每条规则就是一个
`(pdf, md, tables) -> Finding | None` 的函数，加新规则只要写个函数放进 `_RULES`：

| 规则 | 抓什么 | 级别 |
|---|---|---|
| `table_count` | 表格数与原文标题数比对（HTML 表也要数） | info/warn |
| `tilde_values` | 表格里的 `~` 估算值 = 曲线图被数字化的指纹 | **error** |
| `figure_blocks` | `<details>` / ` ```mermaid ` 图像解读产物 | warn |
| `garbled_text` | 文字层损坏：私用区字形 / 控制符 / 字符原地重复 | **error** |
| `prose_in_formula` | 正文段落被整段包进 `$$`（数学模式会吃掉空格） | warn |
| `formula_spacing` | 公式里数字被空格拆开（**仅影响源码可读性**） | info |

每条规则的阈值都是实测调出来的，报告里记录了**每一类误报的成因与修正**。

> ⚠️ 一个反复出现的教训：**看到报警先质疑检查器，再质疑模型。**
> 这个项目里出现的 5 类误报全部来自检查器本身（罗马数字标题、无编号表单、
> HTML 表格漏计、空格被当成字符重复、宽表被拆分），真正的 MinerU 问题只有一个
> —— 上面第 1 条的 `advanced` 编造。

---

## 实测报告（docs/）

按时间顺序，每份都记录了当时的原始数据与踩坑过程：

| 报告 | 内容 |
|---|---|
| [消幻觉手册](docs/MinerU-消幻觉手册.md) | 幻觉的根因定位与三种档位的对比实验 |
| [表格公式实测报告](docs/MinerU-表格公式实测报告.md) | 表格/公式还原精度，含数字空格缺陷的更正 |
| [鲁棒性实测报告](docs/MinerU-鲁棒性实测报告.md) | 47 个真实文件、16 种格式的批量验证 |
| [富公式富图表实测报告](docs/MinerU-富公式富图表实测报告.md) | 11 篇中英文论文，公式有效率 100% |
| [扫描件与模型横评报告](docs/MinerU-扫描件与模型横评报告.md) | 扫描件 OCR 实测 + 同类模型横评 |

几个关键结论：

* **公式**：490 个块公式 **100%** 可被 `ziamath` 真实解析；结论之一是
  **不建议为了 OCR 场景换模型** —— 同量级里 TeleOCR 总分更高（96.87 vs 95.75），
  但优势在表格重建，**公式指标反而更低**（96.36 vs 97.45），且其官方推理依赖 vLLM，
  没有 Windows 支持。
* **扫描件**：干净扫描件（含 150dpi JPEG 强压缩）OCR 与数字版几乎无差别
  （散文相似度 99%、公式零丢失）；**唯一明显退化是"倾斜+噪点"**，会丢 8~17% 的公式。
* **中文**：与中国科学系列论文的表现和英文相当，公式有效率同为 100%。

---

## 测试

```powershell
cd mineru-gui
python selftest_logic.py     # 纯逻辑单测（约 50 个用例）
python selftest_images.py    # 图片抽取 + 乱码检测
python selftest_tables.py    # 表格计数（含 9 个误报回归用例）
python run.py --uicheck      # 真实构建界面并模拟交互
python selftest_flow.py      # 端到端：驱动真实 App 跑完整流程
```

后三个脚本需要语料/产物，仓库里不含（几百 MB）。缺失时相关用例**自动跳过**，
所以裸跑也能通过。要用真实语料时用环境变量指过去：

```powershell
$env:MINERU_TESTDATA = 'D:\corpus\test'      # 原文 PDF/docx/...
$env:MINERU_OUTDIR   = 'D:\MinerU-输出'       # 已转换的产物
$env:MINERU_PAPERS   = 'D:\papers'           # 论文原文（部分用例用）
```

---

## 报告里的路径占位符

报告中的绝对路径已脱敏，对应关系：

| 占位符 | 含义 |
|---|---|
| `%MINERU_ROOT%` | MinerU 部署目录（默认 `D:\MinerU-GPU`） |
| `%WORKSPACE%` | 本项目所在工作区 |
| `%OUTDIR%` | 各次测试的输出目录 |
| `%PAPERS%` | 论文原文目录 |
| `%USERPROFILE%` | Windows 用户目录 |

---

## 环境

实测环境：Windows + RTX 3080 Ti 12GB / Python 3.13 / torch 2.11.0+cu128 /
`mineru 4.0.11` / `lmdeploy 0.17.0`。

Windows 上的两个坑：

1. **vLLM 没有 Windows wheel** —— 所以 MinerU 的 VLM 后端要用 LMDeploy TurboMind。
2. **LMDeploy 的 Windows wheel 是针对 CUDA 12.8 编译的** —— torch 必须同样用 cu128，
   否则 ABI 不匹配。部署脚本里锁了 `--torch-backend=cu128`。
