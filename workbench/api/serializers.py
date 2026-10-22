"""Response encoding helpers for JSON and downloadable files."""

import json
import re
from pathlib import Path
from urllib.parse import quote


def encode_body(data, content_type):
    # Downloads can already be encoded JSON files rather than Python objects.
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if content_type.startswith("application/json"):
        return json.dumps(data, ensure_ascii=False).encode()
    return data


def attachment_header(filename):
    suffix = Path(str(filename)).suffix
    fallback = "workbench-document" + (suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix or "") else "")
    return f"attachment; filename={fallback}; filename*=UTF-8''{quote(str(filename), safe='')}"
