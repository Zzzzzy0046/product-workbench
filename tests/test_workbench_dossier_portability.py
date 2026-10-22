"""Dossier relations survive portable copies and recoverable project removal."""

import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from workbench import app


@pytest.fixture
def bench(tmp_path):
    instance = app.Workbench(tmp_path, runner=lambda _: "unused")
    instance.retrieval_mode = "keyword"
    yield instance
    instance.close()


def make_dossier(bench, project_id, platform, app_id):
    return bench.competitor_service.upsert(project_id, {
        "platform": platform, "app_id": app_id, "title": "Same App Name", "role": "primary",
        "note": "保留人工备注",
    })


def seed_dossiers(bench):
    project = bench.create_project("档案迁移", "竞品资料不按名称误合并")
    version = bench.create_product_version(project["id"], {"name": "V1"})
    android = make_dossier(bench, project["id"], "google_play", "com.example.same")
    ios = make_dossier(bench, project["id"], "app_store", "123456789")
    document = bench.add_document(project["id"], "共享研究.md", "两个平台共用的原始研究资料。".encode(), version["id"])
    for competitor in (android, ios):
        bench.competitor_service.attach_documents(project["id"], competitor["id"], [document["id"]],
            material_type="attachment", source_type="manual", source_id=document["id"],
            metadata={"version_id": version["id"], "countries": ["us"], "note": "来源说明"})
    return project, version, android, ios, document


def package_snapshot(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return json.loads(archive.read("data.json"))


def rewrite_package_with_valid_manifest(content, mutate):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    snapshot = json.loads(members["data.json"])
    mutate(snapshot)
    members["data.json"] = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    manifest = json.loads(members["manifest.json"])
    for item in manifest["files"]:
        payload = members[item["path"]]
        item.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    members["manifest.json"] = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return result.getvalue()


def test_dossier_package_roundtrip_remaps_ids_and_shared_relations(bench):
    project, version, android, ios, document = seed_dossiers(bench)
    package, _ = bench.export_project(project["id"])
    snapshot = package_snapshot(package)
    assert snapshot["schema_version"] == 3
    assert len(snapshot["competitors"]) == 2
    assert len(snapshot["competitor_documents"]) == 2
    copied = bench.import_project(package)
    assert copied["id"] != project["id"]
    competitors = bench.rows("SELECT * FROM competitors WHERE project_id=?", (copied["id"],))
    assert len(competitors) == 2
    assert {row["platform"] for row in competitors} == {"google_play", "app_store"}
    assert {row["title"] for row in competitors} == {"Same App Name"}
    assert {row["note"] for row in competitors} == {"保留人工备注"}
    assert not {row["id"] for row in competitors} & {android["id"], ios["id"]}
    copied_doc = bench.rows("SELECT * FROM documents WHERE project_id=?", (copied["id"],))[0]
    copied_version = bench.rows("SELECT * FROM product_versions WHERE project_id=?", (copied["id"],))[0]
    assert copied_doc["id"] != document["id"]
    assert copied_version["id"] != version["id"]
    links = bench.competitor_service.document_links(copied["id"])
    assert len(links) == 2
    assert {link["competitor_id"] for link in links} == {row["id"] for row in competitors}
    assert {link["document_id"] for link in links} == {copied_doc["id"]}
    assert {link["source_id"] for link in links} == {copied_doc["id"]}
    assert {json.loads(link["metadata"])["version_id"] for link in links} == {copied_version["id"]}
    assert {tuple(json.loads(link["metadata"])["countries"]) for link in links} == {("us",)}
    assert bench.document_file(copied_doc["id"])[0] == bench.document_file(document["id"])[0]
    # Copying does not mutate the original project or its two shared relations.
    assert len(bench.competitor_service.document_links(project["id"])) == 2


def test_dossier_archive_and_unlink_do_not_delete_original_files(bench):
    project, _, android, ios, document = seed_dossiers(bench)
    original, _ = bench.document_file(document["id"])
    bench.competitor_service.update(project["id"], android["id"], {"archived": True})
    assert bench.competitor_service.get(project["id"], android["id"], include_archived=True)["archived"] == 1
    assert len(bench.competitor_service.document_links(project["id"])) == 2
    assert bench.document_file(document["id"])[0] == original
    result = bench.competitor_service.unlink_documents(project["id"], android["id"], [document["id"]])
    assert result["files_deleted"] is False
    links = bench.competitor_service.document_links(project["id"])
    assert [(link["competitor_id"], link["document_id"]) for link in links] == [(ios["id"], document["id"])]
    assert bench.document_file(document["id"])[0] == original


def test_project_trash_restore_preserves_dossier_ids_and_links(bench):
    project, _, android, _, document = seed_dossiers(bench)
    bench.competitor_service.update(project["id"], android["id"], {"archived": True})
    competitors_before = bench.rows("SELECT * FROM competitors WHERE project_id=? ORDER BY id", (project["id"],))
    links_before = sorted(bench.competitor_service.document_links(project["id"]), key=lambda row: row["competitor_id"])
    original = bench.document_file(document["id"])[0]
    deleted = bench.delete_project(project["id"], project["name"])
    assert not bench.rows("SELECT id FROM competitors WHERE project_id=?", (project["id"],))
    assert not bench.rows("SELECT * FROM competitor_documents")
    restored = bench.restore_project(Path(deleted["backup"]).name)
    assert restored["id"] == project["id"]
    assert bench.rows("SELECT * FROM competitors WHERE project_id=? ORDER BY id", (project["id"],)) == competitors_before
    assert sorted(bench.competitor_service.document_links(project["id"]), key=lambda row: row["competitor_id"]) == links_before
    assert bench.document_file(document["id"])[0] == original


@pytest.mark.parametrize("invalid", ["missing-document", "missing-competitor", "duplicate-link", "wrong-project", "duplicate-identity", "metadata"])
def test_malformed_dossier_package_rolls_back_without_creating_partial_project(bench, invalid):
    project, _, _, _, _ = seed_dossiers(bench)
    package, _ = bench.export_project(project["id"])

    def mutate(snapshot):
        if invalid == "missing-document":
            snapshot["competitor_documents"][0]["document_id"] = "f" * 32
        elif invalid == "missing-competitor":
            snapshot["competitor_documents"][0]["competitor_id"] = "f" * 32
        elif invalid == "duplicate-link":
            snapshot["competitor_documents"].append(dict(snapshot["competitor_documents"][0]))
        elif invalid == "wrong-project":
            snapshot["competitors"][0]["project_id"] = "f" * 32
        elif invalid == "duplicate-identity":
            snapshot["competitors"][1]["platform"] = snapshot["competitors"][0]["platform"]
            snapshot["competitors"][1]["app_id"] = snapshot["competitors"][0]["app_id"]
        else:
            snapshot["competitor_documents"][0]["metadata"] = "[1, 2, 3]"

    tables = ("projects", "product_versions", "documents", "competitors", "competitor_documents")
    before = {table: bench.rows(f"SELECT * FROM {table}") for table in tables}
    roots = (bench.data / "uploads", bench.data / "runs", bench.data / "scrapes")
    files_before = {str(path.relative_to(bench.data)) for root in roots if root.exists() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(ValueError):
        bench.import_project(rewrite_package_with_valid_manifest(package, mutate))
    assert {table: bench.rows(f"SELECT * FROM {table}") for table in tables} == before
    files_after = {str(path.relative_to(bench.data)) for root in roots if root.exists() for path in root.rglob("*") if path.is_file()}
    assert files_after == files_before
