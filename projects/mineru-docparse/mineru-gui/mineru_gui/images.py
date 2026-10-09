"""把 markdown 里内联的 base64 图片抽成独立文件。

背景（实测）：
    `mineru-kit parse --format markdown`（默认）会把**每一张图**编码成
    data URI 内联进 md：

        ![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...共几十万字符...)

    一篇 5 页文档就能产生 1.8 MB 的这种文本。在编辑器里它就是一大段
    "乱码"，而且 md 文件大到没法正常打开。

对照：
    `--format zip` 本来就会输出 `images/` 目录 + 相对路径引用的 md，
    但需要解压 + 改写路径 + 处理多文档同名冲突。这里直接在 md 上做，
    流程更简单，也和现有输出路径逻辑不冲突。

产物布局：
    输出目录/
      论文.md
      论文.assets/img_001_3f2a1b....png
      论文.assets/img_002_9c8d7e....jpg
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

# MinerU 有时会把 base64 折行，所以允许匹配内部空白
DATA_URI = re.compile(r'data:image/([a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)')

EXT_BY_SUBTYPE = {
    'png': '.png', 'jpeg': '.jpg', 'jpg': '.jpg', 'webp': '.webp',
    'gif': '.gif', 'bmp': '.bmp', 'tiff': '.tiff', 'jp2': '.jp2',
    'svg+xml': '.svg', 'x-emf': '.emf', 'x-wmf': '.wmf',
}


def has_inline_images(md_path: Path) -> bool:
    try:
        return 'data:image/' in md_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return False


def extract_inline_images(md_path: Path, assets_dir: Path | None = None) -> dict:
    """原地把 data URI 图片落盘，引用改为相对路径。

    返回 {'count', 'unique', 'changed', 'before', 'after', 'dir'}
    内容相同的图（哈希一致）只写一份，多处引用共用。
    """
    result = {'count': 0, 'unique': 0, 'changed': False,
              'before': 0, 'after': 0, 'dir': ''}
    try:
        md = md_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return result

    result['before'] = len(md.encode('utf-8'))
    result['after'] = result['before']
    matches = list(DATA_URI.finditer(md))
    if not matches:
        return result

    assets = assets_dir or (md_path.parent / (md_path.stem + '.assets'))

    parts, seen, last, count = [], {}, 0, 0
    for m in matches:
        parts.append(md[last:m.start()])
        subtype = m.group(1).lower()
        raw = re.sub(r'\s+', '', m.group(2))
        try:
            data = base64.b64decode(raw, validate=True)
        except Exception:
            parts.append(m.group(0))        # 解不开就原样保留，不破坏文件
            last = m.end()
            continue

        digest = hashlib.sha1(data).hexdigest()[:12]
        name = seen.get(digest)
        if name is None:
            ext = EXT_BY_SUBTYPE.get(subtype, '.' + subtype.replace('/', '_'))
            name = 'img_%03d_%s%s' % (len(seen) + 1, digest, ext)
            assets.mkdir(parents=True, exist_ok=True)
            (assets / name).write_bytes(data)
            seen[digest] = name

        # 相对 md 所在目录的路径；空格必须转义，否则 markdown 链接会断
        rel = '%s/%s' % (assets.name, name)
        parts.append(rel.replace(' ', '%20'))
        count += 1
        last = m.end()
    parts.append(md[last:])

    new = ''.join(parts)
    result['after'] = len(new.encode('utf-8'))
    result['count'] = count
    result['unique'] = len(seen)
    result['dir'] = str(assets)
    if new != md:
        md_path.write_text(new, encoding='utf-8')
        result['changed'] = True
    return result
