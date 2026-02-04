#!/usr/bin/env python3
"""
SVG 图片嵌入工具
将 SVG 中引用的外部图片转换为 Base64 内嵌格式或直接内联 SVG 代码
"""

import os
import base64
import re
import sys
import argparse
import html
from pathlib import Path
from xml.etree import ElementTree as ET
from urllib.parse import unquote

# 导入项目工具
sys.path.insert(0, str(Path(__file__).parent))
try:
    from project_utils import get_svg_dimensions
except ImportError:

    def get_svg_dimensions(path):
        return (None, None)


def get_mime_type(filename):
    """根据文件扩展名返回 MIME 类型"""
    ext = filename.lower().split(".")[-1]
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "svg": "image/svg+xml",
    }
    return mime_map.get(ext, "application/octet-stream")


def get_file_size_str(size_bytes):
    """将字节数转换为可读的文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def embed_images_in_svg(svg_path, dry_run=False):
    """
    将 SVG 文件中的外部图片转换为 Base64 内嵌或内联 SVG
    """
    svg_path = Path(svg_path)
    svg_dir = svg_path.parent

    try:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        tree = ET.parse(str(svg_path))
        root = tree.getroot()
    except Exception as e:
        print(f"  [ERROR] Failed to parse {svg_path.name}: {e}")
        return (0, 0)

    ns = {"svg": "http://www.w3.org/2000/svg", "xlink": "http://www.w3.org/1999/xlink"}
    images_embedded = 0
    modified = False

    # 获取所有的 image 元素
    # 注意：ElementTree 处理命名空间比较麻烦，我们通过迭代寻找 tag 包含 image 的元素
    images_to_process = []
    for elem in root.iter():
        if elem.tag.endswith("image"):
            images_to_process.append(elem)

    for img_elem in images_to_process:
        href = img_elem.get("{http://www.w3.org/1999/xlink}href") or img_elem.get(
            "href"
        )
        if not href or href.startswith("data:"):
            continue

        img_path_decoded = unquote(html.unescape(href))
        full_path = (svg_dir / img_path_decoded).resolve()

        if not full_path.exists():
            print(f"  [WARN] Image not found: {href}")
            continue

        img_size = full_path.stat().st_size

        if dry_run:
            print(f"   [PREVIEW] {href} ({get_file_size_str(img_size)})")
            images_embedded += 1
            continue

        # 特殊处理 SVG：内联以提高 PPT 兼容性
        if full_path.suffix.lower() == ".svg":
            try:
                # 解析要嵌入的 SVG
                sub_tree = ET.parse(str(full_path))
                sub_root = sub_tree.getroot()

                # 获取目标位置和尺寸
                x = float(img_elem.get("x", 0))
                y = float(img_elem.get("y", 0))
                w = float(img_elem.get("width", 0))
                h = float(img_elem.get("height", 0))

                # 获取子 SVG 的原始尺寸
                sw, sh = get_svg_dimensions(full_path)
                if sw and sh:
                    sx, sy = w / sw, h / sh
                else:
                    sx, sy = 1.0, 1.0

                # 创建一个 <g> 容器来替代 <image>
                # 注意：保留原有的 id 等属性
                new_elem = ET.Element("{http://www.w3.org/2000/svg}g")
                for k, v in img_elem.attrib.items():
                    if k not in [
                        "x",
                        "y",
                        "width",
                        "height",
                        "href",
                        "{http://www.w3.org/1999/xlink}href",
                        "preserveAspectRatio",
                    ]:
                        new_elem.set(k, v)

                # 设置变换
                new_elem.set(
                    "transform", f"translate({x},{y}) scale({sx:.4f},{sy:.4f})"
                )

                # 将子 SVG 的内容复制到 <g> 中
                for child in sub_root:
                    new_elem.append(child)

                # 在 DOM 中替换
                # 由于 ET 没有直接的 replace，我们需要找到父节点
                # 这种方法比较慢，但在小规模 SVG 中可行
                parent_map = {c: p for p in root.iter() for c in p}
                parent = parent_map.get(img_elem)
                if parent is not None:
                    idx = list(parent).index(img_elem)
                    parent.insert(idx, new_elem)
                    parent.remove(img_elem)
                    images_embedded += 1
                    modified = True
                    print(f"   [OK] {href} (Inlined SVG)")
                continue
            except Exception as e:
                print(f"  [WARN] Failed to inline SVG {href}: {e}")
                # 失败则退回到 Base64 (虽然可能还是空白)

        # 常规图片：Base64 嵌入
        try:
            with open(full_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")

            mime_type = get_mime_type(full_path.name)
            new_href = f"data:{mime_type};base64,{b64_data}"

            if img_elem.get("{http://www.w3.org/1999/xlink}href"):
                img_elem.set("{http://www.w3.org/1999/xlink}href", new_href)
            else:
                img_elem.set("href", new_href)

            images_embedded += 1
            modified = True
            print(f"   [OK] {href} (Embedded Base64)")
        except Exception as e:
            print(f"  [ERROR] Failed to embed {href}: {e}")

    if modified and not dry_run:
        tree.write(str(svg_path), encoding="utf-8", xml_declaration=True)

    return (images_embedded, svg_path.stat().st_size)


def main():
    parser = argparse.ArgumentParser(
        description="将 SVG 中引用的外部图片转换为内联格式"
    )
    parser.add_argument("files", nargs="+", help="要处理的 SVG 文件")
    parser.add_argument("--dry-run", "-n", action="store_true", help="仅预览")

    args = parser.parse_args()

    total_images = 0
    total_files = 0

    for file_pattern in args.files:
        import glob

        for svg_file in glob.glob(file_pattern):
            if not os.path.isfile(svg_file):
                continue
            count, _ = embed_images_in_svg(svg_file, dry_run=args.dry_run)
            if count > 0:
                total_images += count
                total_files += 1

    print(f"\nDone! Processed {total_images} images in {total_files} files.")


if __name__ == "__main__":
    main()
