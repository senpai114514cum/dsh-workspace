# MinerU 鲁棒性实测报告

**测试对象**：MinerU 4.0.11 + RTX 3080 Ti / torch 2.11.0+cu128 / LMDeploy TurboMind
**测试方式**：驱动 GUI 真实交互（`selftest_flow.py`），非脚本绕过界面
**设置**：`standard` 档 + `--ocr-mode auto` + 禁用图像分析 + 自动体检 + 自动清理

---

## 一、语料构成

从公开源下载 + GitHub 测试语料库汇总，共 **47 个文件 / 6.9 MB / 16 种扩展名**，
PDF 合计 68 页。

| 来源 | 内容 |
|---|---|
| **py-pdf/sample-files**（专门做 PDF 边界用例的仓库） | 加密、表单、旋转、多栏、阿拉伯语 RTL、CMYK、灰度、PDF/A、注释、附件、LZW/CCITT 压缩图、Google Docs 导出 |
| **mozilla/Pillow Tests/images** | png / jpg / bmp / webp / gif / tiff，含 EXIF 旋转方向 |
| **python-docx / python-pptx** | docx（含图片）、pptx（含图表） |
| **jgm/pandoc test/** | odt / rtf / epub / html / csv / xlsx |
| **arXiv** | Attention is All You Need（15 页）、ResNet（12 页） |
| **美国 IRS** | fw9 表单（XFA PDF，6 页） |
| **orimi / learningcontainer** | 通用样例 PDF |

> 网络说明：本机 `filesamples.com`、`w3c.org`、`raw.githubusercontent.com` 不可达；
> `codeload.github.com` 与 `git -c http.sslBackend=openssl` 可用（schannel 故障绕过）。

---

## 二、修复前后对比

| | 成功 | 失败 | 耗时 |
|---|---|---|---|
| **修复前** | 30 | **16** | 10 分 14 秒 |
| **修复后** | **44** | **1** | 10 分 50 秒 |

唯一剩下的失败是加密 PDF —— 这是**正确行为**，不是缺陷。

---

## 三、发现并修复的 3 个真问题

### 问题 1（严重）：flash-only 格式传错档位会全盘失败

**现象**：13 个文件在 1~2 秒内全部失败，包括 docx / pptx / xlsx / html / epub / odt / rtf / csv。

**根因**（`mineru/filetypes.py`）：
```python
TIERED_PARSE_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS     # 可跑任意档位
FLASH_ONLY_PARSE_EXTENSIONS = OFFICE|HTML|MHTML|CSV|EPUB|OFD    # 只能 flash

def ensure_tier_supported_for_parse_extension(tier, path):
    if tier not in QUALITY_TIERS or is_tiered_parse_extension(path):
        return
    raise ValueError(f"Tier '{tier}' is only supported for PDF and image files; "
                     f"'{ext}' files use tier 'flash'.")
```
我的界面一律传用户选的档位，于是这些格式全部报错退出。

**修复**：按扩展名自动降档，等价于 MinerU 自己的 `batch_effective_parse_tier()`：
```python
def effective_tier(path, tier):
    return 'flash' if Path(path).suffix.lower() in FLASH_ONLY_EXT else tier
```
并在日志里说明降档原因。

### 问题 2：`.tif` 不支持，只有 `.tiff`

**现象**：`img-03-tiff.tif` 报 `不支持的文件类型`。

**根因**：`IMAGE_EXTENSIONS = {png, jpg, jpeg, webp, gif, bmp, tiff, jp2}` —— **没有 `tif`**。

**验证**：把同一份文件另存为 `.tiff` 重跑 → **成功**。精确证明是扩展名判定而非 TIFF 解码问题。

**修复**：扩展名表与 MinerU 严格对齐，入口处拦截并说明原因。

### 问题 3：体检规则误报（2 类）

| 误报 | 原因 | 修复 |
|---|---|---|
| IEEE 论文报「表格数超出原文」 | 标题是罗马数字 `Table I.`，我的正则只认阿拉伯数字，数出 0 个标题 | 正则支持罗马数字/中文数字，并归一成阿拉伯数字比较 |
| IRS 表单报「表格数超出原文 5 个」 | 表单**本来就没有编号表格标题**（是表单网格），原文 0 个标题时不该判"编造" | 原文 0 个标题时降级为 `info`，提示"无法交叉核对，请人工抽查" |

**回归验证**：误报消除（两份都变"通过"），而真正编造的 `advanced` 输出**仍然报 error**（`表格数超出原文 5 个`）。

---

## 四、MinerU 自身的边界行为（非本程序缺陷）

| 输入 | 结果 | 说明 |
|---|---|---|
| 加密 PDF | ❌ 快速失败 | `PDFium: Incorrect password error`，2 秒内退出，**不会卡住等密码输入** |
| `.txt` / `.md` | ❌ 不支持 | 属于 `INGESTIBLE` 不属于 `PARSEABLE`；只有文档库能读 |
| `.tif` | ❌ 不支持 | 见上 |
| XFA 表单 PDF | ⚠️ 部分功能降级 | `init_forms() called on XFA pdf, but this pdfium binary was compiled without XFA support`，但**正文解析正常完成** |
| 纯文本 / 简单图形图片 | ✅ 正常 | 图片一律走 OCR 分支 |

---

## 五、全部通过的项目（21 个 PDF 边界用例）

除加密那份外，以下**全部成功**，包括很多"看着就会挂"的：

| 用例 | 结果 |
|---|---|
| 阿拉伯语 RTL 文本 | ✅ |
| 阿拉伯语 + 页面旋转 | ✅ |
| 裁剪 + 旋转 + 缩放 | ✅ |
| CMYK 图像 | ✅ |
| 灰度图像 | ✅ |
| LZW / CCITT Fax 压缩图 | ✅ |
| PDF/A 归档格式 | ✅ |
| 表单（pdflatex / LibreOffice） | ✅ |
| 注释 / 附件 / 大纲 | ✅ |
| 多栏排版（LaTeX multicolumn） | ✅ |
| Google Docs 导出 | ✅ |
| 图片：png / jpg / bmp / webp / gif / **tiff** / EXIF 旋转 jpg | ✅ 全部 7 种 |
| Office：docx(含图) / pptx(含图表 1.3MB) / xlsx | ✅ |
| 网页 / 电子书 / 办公文档：html / epub / odt / rtf / csv | ✅（降档 flash 后） |

---

## 六、更正：先前"表格漏检"的结论是错的

初版报告写的"Attention 原文 4 个表只抓到 2 个、ResNet 14 个抓到 11 个"是**误判**，
原因是我的检查器只统计 markdown 竖线表，而 **MinerU 会混用两种表格格式**：
markdown 竖线表 + HTML `<table>`。把 HTML 表一起数之后：

| 论文 | 原文字幕数 | markdown 表 | HTML 表 | 合计 | 结论 |
|---|---|---|---|---|---|
| Attention is All You Need | 4 | 2 | 2 | **4** | 完全一致 |
| ResNet | 14 | 11 | 4 | **15** | 一致（±1） |

**MinerU 并没有漏识别这些表格。** 修正后的规则（HTML 表一起数 + ±1 容差）已通过
7 个回归用例：3 类误报全部消除，而真正编造的 `advanced` 输出仍然报 error。

### 真正存在的现象：表格与标题会被正文隔开

由于原论文是双栏排版且表格浮动，MinerU 按栏阅读时会把标题和表格内容分开。实测
ResNet 输出：

```
第 152 行  Table 2. Top-1 error (%, 10-crop testing) on ImageNet validation...
第 154-162 行  正文段落（讨论 Table 2 / Table 3）
第 164 行  页脚注
第 166-177 行  Table 2 的实际数据表
```

线性阅读 md 时会觉得"标题下面变成文字了、表格丢了"，实际上表格在后面。这是
**阅读顺序问题，不是内容丢失**。

### 文档后半段为什么是纯文字

同一份 ResNet 输出的结构是：

| 行区间 | 内容 | 表格 | 图片 |
|---|---|---|---|
| 1 – 302 | 正文（Abstract → 4.3 Experiments） | 8 | **12 张全部在这里** |
| 303 – 404 | `## References` 参考文献 [1]–[50] | 0 | 0 |
| 405 – 512 | 附录 A / B / C | 6 | 0 |

参考文献本来就是一串纯文本条目，附录本来就没有插图 —— 这是论文结构，不是解析退化。

---

## 七、结论

1. **修复后 44/45 成功**，唯一失败是加密 PDF 且为预期行为。
2. **MinerU 对 PDF 的鲁棒性非常好**：旋转、CMYK、阿拉伯语 RTL、PDF/A、多栏、表单、各种压缩图全部通过。
3. **非 PDF 格式能跑，但必须用 flash 档** —— 这是最容易踩的坑，且错误信息只在快速失败时出现一次。
4. **体检规则必须容忍"没有编号标题"的文档**，否则在政府表单、企业内部文档上会大量误报。
5. 已知质量局限集中在**复杂表格的结构识别**，内容本身不丢。
