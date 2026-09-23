"""블렌디드랩 마스터 도장 비율 자체 점검 — `python backend/tests/test_stamp_aspect_ratio.py`.

블렌디드랩 마스터가 .xls→.xlsx 변환을 거치며 도장 그림의 <a:ext>(렌더 크기)가 실제 이미지
비율과 안 맞게 저장돼, editAs="oneCell"이라 크기가 고정된 채 옆으로 눌린 타원으로 나온
사고가 있었다(2026-09-23). 마스터를 다시 변환하거나 손대다 같은 사고가 재발하는지만 본다.
"""

import re
import struct
import sys
import zipfile
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "blendedlab.xlsx"
DRAWINGS = ["xl/drawings/drawing1.xml", "xl/drawings/drawing2.xml"]

# 도장이 완전한 원은 아니라 약간의 여유를 둔다.
_TOLERANCE = 0.05


def _png_size(png_bytes: bytes) -> tuple[int, int]:
    return struct.unpack(">II", png_bytes[16:24])


def test_blendedlab_stamp_keeps_its_image_aspect_ratio():
    with zipfile.ZipFile(TEMPLATE_PATH) as z:
        for drawing_name in DRAWINGS:
            xml = z.read(drawing_name).decode("utf-8")
            embed_id = re.search(r'r:embed="(rId\d+)"', xml).group(1)
            cx, cy = (int(v) for v in re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>', xml).groups())

            rels_name = f"xl/drawings/_rels/{Path(drawing_name).name}.rels"
            rels = z.read(rels_name).decode("utf-8")
            target = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))[embed_id]
            media_name = "xl/media/" + target.rsplit("/", 1)[-1]

            w, h = _png_size(z.read(media_name))
            image_ratio = w / h
            ext_ratio = cx / cy
            assert abs(image_ratio - ext_ratio) / image_ratio <= _TOLERANCE, (
                f"{drawing_name} {media_name} 이미지비율={image_ratio:.3f} "
                f"렌더비율={ext_ratio:.3f} — 도장이 찌그러져 나온다"
            )


if __name__ == "__main__":
    test_blendedlab_stamp_keeps_its_image_aspect_ratio()
    print("ok")
