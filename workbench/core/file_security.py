"""Validated extraction for supported project material formats."""

import csv
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from workbench.core.constants import IMAGE_SUFFIXES, MAX_TEXT

def extract(name, content):
    suffix = Path(name).suffix.lower()
    if suffix in {".md", ".txt", ".csv", ".json"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("无法识别文本编码，请转为 UTF-8。") from exc
        if suffix == ".csv":
            rows = csv.reader(io.StringIO(text))
            text = "\n".join(" | ".join(row) for row in rows)
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("暂不支持加密 PDF，请先解密。")
        parts = []
        total = 0
        for i, page in enumerate(reader.pages):
            part = page.extract_text() or ""
            total += len(part)
            if total > MAX_TEXT:
                raise ValueError("文档文字过多，请拆分后上传。")
            parts.append(f"[第 {i+1} 页]\n{part}")
        if not any((page.extract_text() or "").strip() for page in reader.pages):
            raise ValueError("PDF 没有可读取文字，请先 OCR 后再导入。")
        text = "\n\n".join(parts)
    elif suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_TEXT * 8:
                raise ValueError("DOCX 解压后过大，请拆分。")
            root = ElementTree.fromstring(archive.read(info))
            ns = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text = "\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
    elif suffix in IMAGE_SUFFIXES:
        from PIL import Image
        with Image.open(io.BytesIO(content)) as picture:
            width, height = picture.size
            image_format = picture.format or suffix.lstrip(".").upper()
            if width < 1 or height < 1 or width * height > 40_000_000:
                raise ValueError("截图尺寸无效或过大，请压缩后上传。")
            picture.verify()
        text = f"截图附件：{name}\n格式：{image_format}\n尺寸：{width} × {height}\n图片内容将在生成任务时作为视觉输入读取。"
    else:
        raise ValueError("支持 MD、TXT、CSV、JSON、PDF、DOCX、PNG、JPG、JPEG、WEBP。")
    if not text.strip():
        raise ValueError("文档没有可读取的文字。")
    if len(text) > MAX_TEXT:
        raise ValueError("文档文字过多，请拆分后上传。")
    return text.replace("\x00", "")
