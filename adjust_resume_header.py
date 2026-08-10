from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


SOURCE = Path(r"D:\workspace\demo_project\multi-agent-hot-copy-generator\中文简历模板-调整版.docx")
OUTPUT = Path(r"D:\workspace\demo_project\multi-agent-hot-copy-generator\中文简历模板-标题图片位置已调整.docx")


def set_attr(element, name, value):
    element.set(qn(f"w:{name}"), str(value))


doc = Document(SOURCE)
title, contact, photo = doc.paragraphs[:3]

# Keep the text block clear of the photo area and align it to a stable left edge.
for paragraph in (title, contact):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.right_indent = Pt(108)

title.paragraph_format.space_after = Pt(3)
contact.paragraph_format.space_after = Pt(9)

# Turn the existing photo instruction into a compact floating placeholder at top right.
photo.text = "证件照\n建议圆形"
photo.alignment = WD_ALIGN_PARAGRAPH.CENTER
photo.paragraph_format.space_before = Pt(0)
photo.paragraph_format.space_after = Pt(0)
photo.paragraph_format.line_spacing = 1

for run in photo.runs:
    run.font.name = "微软雅黑"
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "微软雅黑")
    run.font.size = Pt(8)
    run.font.color.rgb = None

p_pr = photo._p.get_or_add_pPr()

frame = OxmlElement("w:framePr")
for name, value in {
    "w": 1450,
    "h": 1700,
    "hRule": "exact",
    "hAnchor": "margin",
    "vAnchor": "margin",
    "xAlign": "right",
    "y": 0,
    "hSpace": 120,
    "vSpace": 0,
    "wrap": "around",
}.items():
    set_attr(frame, name, value)
p_pr.insert(0, frame)

shading = OxmlElement("w:shd")
set_attr(shading, "val", "clear")
set_attr(shading, "color", "auto")
set_attr(shading, "fill", "F3F4F6")
p_pr.append(shading)

borders = OxmlElement("w:pBdr")
for edge in ("top", "left", "bottom", "right"):
    border = OxmlElement(f"w:{edge}")
    set_attr(border, "val", "single")
    set_attr(border, "sz", 6)
    set_attr(border, "space", 3)
    set_attr(border, "color", "C7CBD1")
    borders.append(border)
p_pr.append(borders)

doc.save(OUTPUT)
print(OUTPUT)
