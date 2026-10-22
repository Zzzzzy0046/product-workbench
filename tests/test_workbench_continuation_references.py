"""Chapter continuation reuses the user's explicit picks, not every retrieved upload."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_continuation_prefers_explicit_selection():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend helper checks")
    script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const ctx={console,document:{querySelector:()=>null,getElementById:()=>null,addEventListener(){}}};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('workbench/static/features/outputs.js','utf8'),ctx);
const sources=[{kind:'upload',source_id:'listing'},{kind:'upload',source_id:'reviews'},{kind:'upload',source_id:'stray-image'},{kind:'accepted',source_id:'f1-1'}];
assert.deepEqual([...ctx.continuationReferenceIds({sources,selected_document_ids:['listing','reviews']})],['listing','reviews']);
assert.deepEqual([...ctx.continuationReferenceIds({sources,selected_document_ids:[]})],['listing','reviews','stray-image']);
assert.deepEqual([...ctx.continuationReferenceIds({sources})],['listing','reviews','stray-image']);
console.log(JSON.stringify({checks:'PASS'}));
"""
    result = subprocess.run([node, "-e", script], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["checks"] == "PASS"
