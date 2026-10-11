"""图片与 markdown 之间的两个方向：

* `extract_inline_images` —— 把 md 里内联的 base64 抽成独立文件（md 变小、可编辑）
* `inline_images`         —— 把独立文件重新内联回 base64（md 自包含、单文件可移植）

两者互为逆操作，都**原地替换、不改变图片的先后位置**：

    提取前：![](data:image/png;base64,iVBOR...)
    提取后：![](论文.assets/img_001_ab12cd34ef56.png)
    内联后：![](data:image/png;base64,iVBOR...)      ← 回到原样

背景（实测）：
    `mineru-kit parse --format markdown`（默认）会把**每一张图**编码成
    data URI 内联进 md。一篇 5 页文档就能产生 1.8 MB 的这种文本，
    在编辑器里它就是一大段"乱码"，所以默认抽成文件。

    但抽完之后 md 就不再自包含了 —— 要发出去、塞进知识库、单独归档时
    还得带上旁边那个 .assets 目录。这时就用 `inline_images` 合回单文件。

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
from urllib.parse import unquote

# MinerU 有时会把 base64 折行，所以允许匹配内部空白
DATA_URI = re.compile(r'data:image/([a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)')

# markdown 图片引用：![alt](目标) 或 ![alt](目标 "标题")
IMG_REF = re.compile(r'!\[([^\]]*)\]\(([^)]*)\)')

EXT_BY_SUBTYPE = {
    'png': '.png', 'jpeg': '.jpg', 'jpg': '.jpg', 'webp': '.webp',
    'gif': '.gif', 'bmp': '.bmp', 'tiff': '.tiff', 'jp2': '.jp2',
    'svg+xml': '.svg', 'x-emf': '.emf', 'x-wmf': '.wmf',
}

MIME_BY_EXT = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp',
    '.tiff': 'image/tiff', '.tif': 'image/tiff', '.jp2': 'image/jp2',
    '.svg': 'image/svg+xml', '.emf': 'image/emf', '.wmf': 'image/wmf',
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


# ---------------------------------------------------------------- 反向：内联

def _split_target(target: str) -> tuple[str, str]:
    """把 markdown 链接目标拆成 (路径, 标题后缀)。

    `![a](x.png "标题")` 的目标部分是 `x.png "标题"`，要保住标题不丢。
    """
    t = target.strip()
    m = re.match(r'^(<[^>]*>|\S+)(\s+["\'(].*)?$', t, re.S)
    if not m:
        return t, ''
    path = m.group(1)
    if path.startswith('<') and path.endswith('>'):
        path = path[1:-1]
    return path, (m.group(2) or '')


def _looks_external(path: str) -> bool:
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', path))    # http: data: file: ...


def inline_images(md_path: Path, base_dir: Path | None = None) -> dict:
    """原地把 md 里引用的本地图片文件转成 base64 内联，让 md 自包含。

    返回 {'count', 'missing', 'external', 'changed', 'before', 'after', 'files'}

    * 位置不变：只替换链接目标，`![](...)` 仍在原处
    * 跳过 `data:` / `http(s):` 等非本地引用
    * 找不到的文件**原样保留**并计入 missing，不会把 md 改坏
    * `%20` 这类转义会先解码再读文件
    * 同一个文件被引用多次会各自内联（markdown 里本来就是两处引用）
    """
    result = {'count': 0, 'missing': 0, 'external': 0, 'changed': False,
              'before': 0, 'after': 0, 'files': []}
    try:
        md = md_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return result

    result['before'] = len(md.encode('utf-8'))
    result['after'] = result['before']
    base = base_dir or md_path.parent

    parts, last, count, missing, external = [], 0, 0, 0, 0
    inlined = {}
    for m in IMG_REF.finditer(md):
        target = m.group(2)
        if not target.strip():
            continue
        path, title = _split_target(target)
        if not path:
            continue
        if path.startswith('data:'):
            continue                                  # 已经是内联的
        if _looks_external(path):
            external += 1
            continue

        local = Path(unquote(path))
        if not local.is_absolute():
            local = base / local
        try:
            data = local.read_bytes()
        except Exception:
            missing += 1
            continue

        key = str(local)
        uri = inlined.get(key)
        if uri is None:
            mime = MIME_BY_EXT.get(local.suffix.lower())
            if mime is None:
                mime = 'image/' + local.suffix.lstrip('.').lower() or 'image/png'
            uri = 'data:%s;base64,%s' % (
                mime, base64.b64encode(data).decode('ascii'))
            inlined[key] = uri
            result['files'].append(local.name)

        parts.append(md[last:m.start()])
        parts.append('![%s](%s%s)' % (m.group(1), uri, title))
        count += 1
        last = m.end()

    if count:
        parts.append(md[last:])
        new = ''.join(parts)
        result['after'] = len(new.encode('utf-8'))
        if new != md:
            md_path.write_text(new, encoding='utf-8')
            result['changed'] = True

    result['count'] = count
    result['missing'] = missing
    result['external'] = external
    return result


def describe_inline(r: dict) -> str:
    """给日志用的一句话。"""
    if not r['count']:
        bits = []
        if r['external']:
            bits.append('%d 个外链' % r['external'])
        if r['missing']:
            bits.append('%d 个文件缺失' % r['missing'])
        return '没有可内联的本地图片' + ('（%s）' % '、'.join(bits) if bits else '')
    msg = '已把 %d 张图内联回 md（%d 个文件），体积 %.0f KB → %.1f MB' % (
        r['count'], len(r['files']), r['before'] / 1024, r['after'] / 1048576)
    if r['missing']:
        msg += '；%d 个引用的文件不存在，已原样保留' % r['missing']
    if r['external']:
        msg += '；跳过 %d 个外链' % r['external']
    return msg
