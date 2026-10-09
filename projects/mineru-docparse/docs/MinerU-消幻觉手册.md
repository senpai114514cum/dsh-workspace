# MinerU 消幻觉操作手册

基于本机实测（RTX 3080 Ti / MinerU 4.0.11 / torch 2.11.0+cu128 / LMDeploy 0.17.0 TurboMind）
测试样本：2 份英文期刊论文 + 2 份中文期刊论文，共 6 次解析对比

---

## 一、根因：幻觉只有一个来源

读 MinerU 4.0 源码可以看到两处关键定义：

**`mineru/parser/tier.py`** —— 档位映射为推理强度：

| 档位 | effort |
|---|---|
| `flash` | flash |
| `basic` | medium |
| `standard` | **high** |
| `advanced` | **xhigh** |

**`mineru/backend/analysis/pdf/window.py:572`** —— 图像分析只在 xhigh 生效：

```python
options = {"images": state.images_pil_list,
           "image_analysis": image_analysis if effort == "xhigh" else False}
```

**结论：`standard` 的图像分析是被代码强制关闭的；幻觉 100% 来自 `advanced` 开启的"逐图解读"。**

这解释了实测的全部现象——`advanced` 编造的表格、Mermaid 图、英文图注，全部是它在"解读插图"。

---

## 二、五道防线

### 防线 1：档位与开关（决定性，先做这个）

同一份 9 页英文论文（原文真实表格 **2** 个）：

| 命令 | 耗时 | 表格 | 块级公式 | 行内公式 | details | 幻觉 |
|---|---|---|---|---|---|---|
| `--tier flash --ocr-mode txt` | **6s** | 2 | **0** | **0** | 1 | 无（不跑模型） |
| `--tier standard` | 36s | **2** | 26 | 152 | 0 | 无 |
| `--tier advanced --disable-image-analysis` | 40s | **2** | **27** | **165** | 0 | 无 |
| `--tier advanced` | 45s | **7** | 27 | 165 | 7 | **编造 5 个表** |

中文论文（原文真实表格 2 个）同样：`advanced` 8 个表 → 加 `--disable-image-analysis` 后回到 **2 个**，公式 8/25 一个没少。

```powershell
# ① 默认首选
mineru-kit parse 'a.pdf' -o 'a.md' --tier standard

# ② 想要最大公式召回（比 standard 多 1 个块级公式 + 13 个行内公式，代价 4 秒）
mineru-kit parse 'a.pdf' -o 'a.md' --tier advanced --disable-image-analysis

# ③ 绝对零幻觉（完全不跑模型，但公式和结构全丢，只适合纯文字稿）
mineru-kit parse 'a.pdf' -o 'a.md' --tier flash --ocr-mode txt

# ④ 永远不要这样用
mineru-kit parse 'a.pdf' -o 'a.md' --tier advanced        # ← 幻觉重灾区
```

如果你确实需要图注/图表的文字描述，**也别用 ④**：`advanced` 的图注实测会编造（`Air-Haids-Sea Integration`、`流摇 Interfectogram` 这类不存在的词），而且会输出 BER = 10^-0.5 这种物理上不可能的数值。图已经作为图片文件导出，人工看图更可靠。

### 防线 2：OCR 模式

```powershell
--ocr-mode auto   # 默认，自动判断
--ocr-mode txt    # 强制只用 PDF 文字层，不跑 OCR
--ocr-mode ocr    # 强制 OCR
```

- **有文字层的 PDF**（排版型论文/公文）→ 用 `txt`：OCR 一次都不跑，**OCR 误识率归零**
- **扫描件/图片型 PDF** → 必须 `ocr`，否则抽不到文字
- 不确定 → 保持 `auto`

判断方法：用 pypdf 抽一下文字，能抽出成段文字就是有文字层。

### 防线 3：模型精度（本机已做，无需再动）

全精度 LMDeploy（cu128 + TurboMind）比基础包的 llama.cpp GGUF 量化模型幻觉更少。
`mineru[full]` 已装，`mineru-kit models show` 确认 `生效的 VLM 引擎: lmdeploy` 即可，不要退回量化方案。

### 防线 4：`llm_aided` 要慎用——它本身是新的幻觉源

配置在 `%MINERU_ROOT%\home\config.yaml`，两个开关默认 `false`：

| 开关 | 风险 | 建议 |
|---|---|---|
| `title_leveling` | 低（只调整标题层级 H2~H6，不改正文） | 需要标题层级时可以开 |
| `cross_page_table_cell_merge` | **中（会修改表格单元格内容）** | 除非跨页表格很关键，否则别开 |

两者都需要一个 OpenAI 兼容的 LLM 服务（云端或本地 Ollama）。**注意：开了就等于在管线里插入了第二个可能编造的模型**，而 `title_leveling` 只在整篇解析时生效（指定页码范围会被跳过）。

### 防线 5：输出体检（自动化兜底）

配了脚本 [check-mineru-output.py](check-mineru-output.py)，用 MinerU 环境自带的 python 跑：

```powershell
$py = '%MINERU_ROOT%\.venv\Scripts\python.exe'
& $py '%WORKSPACE%\check-mineru-output.py' '原文.pdf' '输出.md'          # 只体检
& $py '%WORKSPACE%\check-mineru-output.py' '原文.pdf' '输出.md' --fix    # 体检并清理
```

检查 4 项，退出码非 0 表示有问题：

| 检查项 | 判据 | 实测效果 |
|---|---|---|
| 表格数 vs 原文"表N/Table N"标题数 | 多出来的就是编造的 | advanced 输出：`7 个 vs 原文 2 个` → 报警 |
| `<details>` / ```` ```mermaid ```` 块 | 图像解读产物，幻觉载体 | 7 个 details → 报警 |
| 表格里带 `~` 前缀的数值 | VLM 估算图形坐标的指纹 | 找到 133 个 → 报警 |
| 公式里被空格拆开的数字 | **源码可读性**（实测不影响渲染，见下） | 5/27 → 提示 |

`--fix` 会：删除所有 `<details>` 和 ```` ```mermaid ```` 块、合并公式里被空格拆开的数字，输出 `*-fixed.md`。
**编造的表格不敢自动删**（脚本分不清哪个是假的），需要你按报警信息人工确认。

---

## 三、消不掉的已知缺陷（与档位无关）

1. **公式数字被空格拆开**，出现率 19%（仅 MathType 排版的那份英文论文，中文论文 0%）：
   ```
   1. 2 3 \mathrm{C}_{n}^{2} k^{7 / 6}     ← 源码不够整洁，但渲染没问题
   0 . 4 9 \sigma_{R}^{2}                  ← 同上
   ```
   > ⚠️ **2026-10-10 更正**：本手册初版把这条列为"消不掉的缺陷"，并说会渲染出可见空隙。
   > 实测（ziamath 渲染成 SVG 逐字节比对）证明 **LaTeX 数学模式忽略空格**，
   > `1. 2 3` 与 `1.23` 渲染结果完全相同。所以它**不是缺陷**，只是源码可读性问题。
   >
   > 体检项已降级为 `info`；自动整理会**跳过含 `\text{}` / `\mbox{}` 的公式**，
   > 因为那些命令里空格有意义（`\text{Fig 1 2}` ≠ `\text{Fig 12}`）。
   两个档位都出现。修法：只在 `$$...$$` 内部执行 `(?<=\d)\s+(?=[\d.])` → 删除。`--fix` 已包含。

2. **Word 域代码残留**：原文里的 `错误!未找到引用源` 被原样保留。这是源文档问题，不是识别错误。

3. **TurboMind 预热警告**（每次启动都有，不影响结果）：
   ```
   [TM][ERROR][turbomind.cc:467] Warm-up for 8320 tokens failed with status 6
   ```

---

## 四、推荐工作流

```powershell
$py   = '%MINERU_ROOT%\.venv\Scripts\python.exe'
$kit  = '%MINERU_ROOT%\.venv\Scripts\mineru-kit.exe'
$doc  = 'D:\待处理\论文.pdf'

# 1) 判断有没有文字层（有则用 txt 模式）
& $py -c "from pypdf import PdfReader; print('文字层:', len((PdfReader(r'$doc').pages[0].extract_text() or '')) > 200)"

# 2) 解析：有文字层
& $kit parse $doc -o 'D:\输出\论文.md' --tier standard --ocr-mode txt
#    扫描件改用
# & $kit parse $doc -o 'D:\输出\论文.md' --tier standard --ocr-mode ocr

# 3) 体检 + 清理
& $py '%WORKSPACE%\check-mineru-output.py' $doc 'D:\输出\论文.md' --fix

# 4) 看退出码，非 0 就按报警人工核对表格
```

**一句话记住**：`--tier standard` 是安全默认值；只有当你明确需要更激进的版面推断时才上 `advanced`，且**必须**同时加 `--disable-image-analysis`。
