#!/usr/bin/env python3
"""
SVG 图片宽高比修复工具

修复 SVG 中 <image> 元素的尺寸，使其与图片原始宽高比一致。
这样在 PowerPoint 将 SVG 转换为形状时，图片不会被拉伸变形。
"""

import os
import re
import sys
import base64
import argparse
from pathlib import Path
from xml.etree import ElementTree as ET

# 尝试导入 PIL，用于获取图片尺寸
try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# 导入项目工具模块
sys.path.insert(0, str(Path(__file__).parent))
try:
    from project_utils import get_svg_dimensions
except ImportError:

    def get_svg_dimensions(path):
        return (None, None)


def get_image_dimensions_pil(image_path):
    """使用 PIL 获取图片尺寸"""
    try:
        with Image.open(image_path) as img:
            return float(img.width), float(img.height)
    except Exception:
        return None, None


def get_image_dimensions_basic(image_path):
    """基本方法获取图片尺寸（不依赖 PIL）"""
    try:
        with open(image_path, "rb") as f:
            data = f.read(64)

        # PNG
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w = int.from_bytes(data[16:20], "big")
            h = int.from_bytes(data[20:24], "big")
            return float(w), float(h)

        # JPEG
        if data[:2] == b"\xff\xd8":
            with open(image_path, "rb") as f:
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if not marker or len(marker) < 2:
                        break
                    if marker[0] != 0xFF:
                        break
                    m = marker[1]
                    if m in (0xC0, 0xC2):
                        f.read(3)
                        h = int.from_bytes(f.read(2), "big")
                        w = int.from_bytes(f.read(2), "big")
                        return float(w), float(h)
                    elif m == 0xD9:
                        break
                    elif m == 0xD8:
                        continue
                    elif 0xD0 <= m <= 0xD7:
                        continue
                    else:
                        length = int.from_bytes(f.read(2), "big")
                        f.seek(length - 2, 1)
        return None, None
    except Exception:
        return None, None


def get_image_dimensions_from_base64(data_uri):
    """从 Base64 数据 URI 获取图片尺寸"""
    import io

    try:
        match = re.match(r"data:image/(\w+);base64,(.+)", data_uri)
        if not match:
            return None, None

        b64_data = match.group(2)
        img_bytes = base64.b64decode(b64_data)

        if HAS_PIL:
            with Image.open(io.BytesIO(img_bytes)) as img:
                return float(img.width), float(img.height)
        else:
            if img_bytes[:8] == b"\x89PNG\r\n\x1a\n":
                w = int.from_bytes(img_bytes[16:20], "big")
                h = int.from_bytes(img_bytes[20:24], "big")
                return float(w), float(h)
        return None, None
    except Exception:
        return None, None


def get_image_dimensions(href, svg_dir):
    """获取图片尺寸"""
    if href.startswith("data:"):
        # 如果已经是 base64 SVG，尝试正则解析
        if "image/svg+xml" in href:
            try:
                b64_data = href.split(",")[1]
                svg_content = base64.b64decode(b64_data).decode("utf-8")
                vb_match = re.search(
                    r'viewBox\s*=\s*["\']\d+\s+\d+\s+(\d+\.?\d*)\s+(\d+\.?\d*)["\']',
                    svg_content[:2048],
                )
                if vb_match:
                    return float(vb_match.group(1)), float(vb_match.group(2))
            except:
                pass
        return get_image_dimensions_from_base64(href)

    if not os.path.isabs(href):
        full_path = (Path(svg_dir) / href).resolve()
    else:
        full_path = Path(href)

    if not full_path.exists():
        return None, None

    if full_path.suffix.lower() == ".svg":
        return get_svg_dimensions(full_path)

    if HAS_PIL:
        return get_image_dimensions_pil(str(full_path))
    else:
        return get_image_dimensions_basic(str(full_path))


def calculate_fitted_dimensions(
    img_width, img_height, box_width, box_height, mode="meet"
):
    """计算图片在框内的适合尺寸"""
    img_ratio = img_width / img_height
    box_ratio = box_width / box_height

    if mode == "meet":
        if img_ratio > box_ratio:
            new_width = box_width
            new_height = box_width / img_ratio
        else:
            new_height = box_height
            new_width = box_height * img_ratio
    else:  # slice
        if img_ratio > box_ratio:
            new_height = box_height
            new_width = box_height * img_ratio
        else:
            new_width = box_width
            new_height = box_width / img_ratio

    offset_x = (box_width - new_width) / 2
    offset_y = (box_height - new_height) / 2
    return new_width, new_height, offset_x, offset_y


def fix_image_aspect_in_svg(svg_path, dry_run=False, verbose=True):
    """修复 SVG 中图片的宽高比"""
    svg_path = Path(svg_path)
    svg_dir = svg_path.parent

    try:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        tree = ET.parse(str(svg_path))
        root = tree.getroot()
    except Exception as e:
        print(f"  [ERROR] Cannot parse SVG: {e}")
        return 0

    fixed_count = 0
    # 查找所有 image 元素
    for image_elem in root.iter():
        if not image_elem.tag.endswith("image"):
            continue

        href = image_elem.get("{http://www.w3.org/1999/xlink}href") or image_elem.get(
            "href"
        )
        if href is None:
            continue

        try:
            x = float(image_elem.get("x", 0))
            y = float(image_elem.get("y", 0))
            width = float(image_elem.get("width", 0))
            height = float(image_elem.get("height", 0))
        except (ValueError, TypeError):
            continue

        if width <= 0 or height <= 0:
            continue

        par = image_elem.get("preserveAspectRatio", "xMidYMid meet")
        if "none" in par:
            continue

        img_width, img_height = get_image_dimensions(href, svg_dir)
        if img_width is None or img_height is None:
            continue

        mode = "slice" if "slice" in par else "meet"
        new_width, new_height, offset_x, offset_y = calculate_fitted_dimensions(
            img_width, img_height, width, height, mode
        )

        if abs(new_width - width) < 0.5 and abs(new_height - height) < 0.5:
            continue

        if verbose:
            print(
                f"  [FIX] {svg_path.name}: {width}x{height} -> {new_width:.1f}x{new_height:.1f}"
            )

        if not dry_run:
            image_elem.set("x", f"{x + offset_x:.1f}")
            image_elem.set("y", f"{y + offset_y:.1f}")
            image_elem.set("width", f"{new_width:.1f}")
            image_elem.set("height", f"{new_height:.1f}")
            if "preserveAspectRatio" in image_elem.attrib:
                del image_elem.attrib["preserveAspectRatio"]
        fixed_count += 1

    if not dry_run and fixed_count > 0:
        tree.write(str(svg_path), encoding="utf-8", xml_declaration=True)
    return fixed_count


def main():
    parser = argparse.ArgumentParser(description="修复 SVG 中图片的宽高比")
    parser.add_argument("files", nargs="+", help="SVG 文件")
    parser.add_argument("--dry-run", "-n", action="store_true")
    args = parser.parse_args()

    for f in args.files:
        fix_image_aspect_in_svg(f, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
