"""Deliverable exports and portable project package import/export."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class ExportService(BoundService):
    _CAPTURE_LOCAL_KEYS = frozenset({
        "adb", "adb_path", "python_path", "skill_root", "session_dir", "output_dir",
        "cache", "anim_original",
        "session_path", "root", "cwd", "codex_home", "cli", "cli_path",
        "cli_command", "mcp", "mcp_servers", "bridge", "bridge_url",
        "bridge_token", "connection", "connection_url", "connection_token",
        "endpoint", "authorization", "headers", "env", "token", "api_key",
        "access_token", "refresh_token", "secret", "password",
    })

    @classmethod
    def _portable_capture_metadata(cls, value):
        """Keep capture configuration and evidence identity, never local execution access."""
        if isinstance(value, dict):
            return {
                key: cls._portable_capture_metadata(item)
                for key, item in value.items()
                if str(key).lower() not in cls._CAPTURE_LOCAL_KEYS
                and not str(key).lower().startswith(("cli_", "mcp_", "codex_"))
                and not str(key).lower().endswith(("_token", "_secret", "_password"))
            }
        if isinstance(value, list):
            return [cls._portable_capture_metadata(item) for item in value]
        return value

    @staticmethod
    def _capture_private_file(relative):
        """Exclude model execution attempts without discarding capture timing evidence."""
        parts = Path(relative).parts
        name = parts[-1].lower() if parts else ""
        return (
            any(part.lower() == "attempts" for part in parts)
            or name in {"progress.jsonl", "events.jsonl", "stdout-events.jsonl", "model-events.jsonl", "model_events.jsonl", "codex-events.jsonl"}
            or name.endswith(".lock")
            or name.startswith(("prompt.", "prompt-", "codex-diagnostics", "model-output", "agent-output"))
        )

    def _import_capture_sessions(self, scrape_target, old_project_id, new_project_id, product_version_map, document_map, renamed, competitor_map=None):
        """Give imported captures isolated IDs and require a new device observation."""
        capture_map = {}
        for source in sorted(scrape_target.glob("android-*")):
            if not source.is_dir():
                continue
            if not source.resolve().is_relative_to(scrape_target):
                raise ValueError("项目包中的 Android 截图路径无效。")
            metadata = source / "session.json"
            if not metadata.is_file():
                continue
            try:
                session = json.loads(metadata.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                raise ValueError("项目包中的 Android 截图会话无法读取。") from exc
            if not isinstance(session, dict):
                raise ValueError("项目包中的 Android 截图会话格式无效。")
            old_id = str(session.get("id", ""))
            if not ID_PATTERN.fullmatch(old_id) or source.name != "android-" + old_id or session.get("project_id") != old_project_id:
                raise ValueError("项目包中的 Android 截图会话引用无效。")
            new_id = uid()
            capture_map[old_id] = new_id
            destination = (scrape_target / ("android-" + new_id)).resolve()
            if not destination.is_relative_to(scrape_target) or destination.exists():
                raise ValueError("项目包中的 Android 截图目录无效。")
            source.rename(destination)
            renamed.append((source, destination))
            session = self._portable_capture_metadata(session)
            session.update({
                "id": new_id,
                "project_id": new_project_id,
                "version_id": product_version_map.get(str(session.get("version_id", "")), ""),
                "document_ids": [document_map[value] for value in session.get("document_ids", []) if isinstance(value, str) and value in document_map],
                "competitor_id": (competitor_map or {}).get(str(session.get("competitor_id", "")), ""),
            })
            if session.get("status") in {"queued", "running", "prepared", "paused"}:
                session.update({
                    "status": "interrupted",
                    "pause_reason": "从项目包导入，需重新检测设备和当前页面后手动继续。",
                    "error": "导入时未继续执行截图走查。",
                })
            session["updated"] = now()
            (destination / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
            request_path = destination / "request.json"
            if request_path.is_file():
                try:
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, ValueError) as exc:
                    raise ValueError("项目包中的 Android 截图请求无法读取。") from exc
                if not isinstance(request, dict):
                    raise ValueError("项目包中的 Android 截图请求格式无效。")
                request = self._portable_capture_metadata(request)
                request.update({key: session[key] for key in ("id", "project_id", "version_id", "document_ids", "competitor_id")})
                if "capture_id" in request:
                    request["capture_id"] = new_id
                request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
            checkpoint_path = destination / "capture-session.json"
            if checkpoint_path.is_file():
                try:
                    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, ValueError) as exc:
                    raise ValueError("项目包中的 Android 截图观察检查点无法读取。") from exc
                if not isinstance(checkpoint, dict):
                    raise ValueError("项目包中的 Android 截图观察检查点格式无效。")
                checkpoint = {key: value for key, value in checkpoint.items() if str(key).lower() not in self._CAPTURE_LOCAL_KEYS}
                checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
            workspace_path = destination / "aw.json"
            if workspace_path.is_file():
                try:
                    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
                    if not isinstance(workspace, dict):
                        raise ValueError("invalid walkthrough workspace")
                except (OSError, UnicodeDecodeError, ValueError) as exc:
                    raise ValueError("项目包中的新版截图工作区配置无法读取。") from exc
                workspace_path.write_text(json.dumps(self._portable_capture_metadata(workspace), ensure_ascii=False, indent=2), encoding="utf-8")
        return capture_map

    @staticmethod
    def _safe_export_name(value):
        value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "-", str(value or "交付物"))
        return value.strip(" .")[:100] or "交付物"

    @staticmethod
    def _portable_sources(raw_sources):
        """Remove machine-bound image paths from a task source snapshot."""
        try:
            sources = json.loads(raw_sources or "[]") if isinstance(raw_sources, str) else list(raw_sources or [])
        except (TypeError, ValueError):
            return raw_sources or "[]"
        if not isinstance(sources, list):
            return "[]"
        for source in sources:
            if isinstance(source, dict):
                source.pop("image_path", None)
        return json.dumps(sources, ensure_ascii=False)

    @staticmethod
    def _portable_scrape_request(raw_request, competitor_map=None):
        """Keep scraper parameters while omitting the local tool directory."""
        try:
            request = json.loads(raw_request or "{}") if isinstance(raw_request, str) else dict(raw_request or {})
        except (TypeError, ValueError):
            return raw_request or "{}"
        if not isinstance(request, dict):
            return "{}"
        request.pop("root", None)
        if competitor_map is not None and "competitor_id" in request:
            request["competitor_id"] = competitor_map.get(str(request["competitor_id"]), "")
        return json.dumps(request, ensure_ascii=False)

    def export_job(self, job_id, fmt, version=None):
        """Render one job version to a requested file format."""
        job = self.job(job_id)
        if version is None:
            output = job["output"]
            version_number = job.get("current_version") or 1
        else:
            item = self.version(job_id, version)
            output = item["output"]
            version_number = item["version"]
        if not output.strip():
            raise ValueError("当前交付物还没有可导出的正文。")
        try:
            from workbench.exporters import render
        except ModuleNotFoundError:
            from exporters import render

        def resolver(document_id):
            return str(self.asset(job["project_id"], document_id)[0])

        content, extension, content_type = render(output, fmt, resolver)
        stamp = datetime.now().strftime("%Y%m%d")
        project_name = self.project(job["project_id"])["name"]
        stem = self._safe_export_name(f"{project_name}-{job['title']}-V{version_number:04d}-{stamp}")
        return content, content_type, f"{stem}.{extension}"

    @staticmethod
    def _safe_archive_member(name):
        name = str(name).replace("\\", "/")
        path = Path(name)
        if not name or name.startswith("/") or name.startswith("\\") or ".." in path.parts:
            raise ValueError("项目包包含不安全的文件路径。")
        if len(name) > 500 or any(ord(char) < 32 for char in name):
            raise ValueError("项目包文件名无效。")
        return name

    def export_project(self, project_id):
        """Export all recoverable project state and files as a portable ZIP."""
        project = self.project(project_id)
        job_ids = [item["id"] for item in self.rows("SELECT id FROM jobs WHERE project_id=?", (project_id,))]
        jobs = self.rows("SELECT * FROM jobs WHERE project_id=?", (project_id,))
        for item in jobs:
            item["sources"] = self._portable_sources(item.get("sources", "[]"))
        snapshot = {
            "schema_version": 3,
            "exported_at": now(),
            "project": project,
            "product_versions": self.rows("SELECT * FROM product_versions WHERE project_id=? ORDER BY created", (project_id,)),
            "context": self.rows("SELECT * FROM contexts WHERE project_id=?", (project_id,)),
            "conditions": self.rows("SELECT * FROM conditions WHERE project_id=?", (project_id,)),
            "documents": self.rows("SELECT * FROM documents WHERE project_id=?", (project_id,)),
            "jobs": jobs,
            "reviews": self.rows("SELECT r.* FROM reviews r JOIN jobs j ON j.id=r.job_id WHERE j.project_id=?", (project_id,)),
            "job_versions": self.rows("SELECT v.* FROM job_versions v JOIN jobs j ON j.id=v.job_id WHERE j.project_id=? ORDER BY v.job_id,v.version", (project_id,)),
            "document_comments": self.rows("SELECT c.* FROM document_comments c JOIN jobs j ON j.id=c.job_id WHERE j.project_id=? ORDER BY c.job_id,c.version,c.created", (project_id,)),
            "scrapes": self.rows("SELECT * FROM scrapes WHERE project_id=? ORDER BY created", (project_id,)),
            "competitors": self.rows("SELECT * FROM competitors WHERE project_id=? ORDER BY created", (project_id,)),
            "competitor_documents": self.rows("SELECT d.* FROM competitor_documents d JOIN competitors c ON c.id=d.competitor_id WHERE c.project_id=?", (project_id,)),
            "version_documents": self.rows(
                """SELECT d.* FROM version_documents d
                   JOIN product_versions v ON v.id=d.version_id
                   WHERE v.project_id=? ORDER BY d.created""",
                (project_id,),
            ),
        }
        files: dict[str, bytes] = {
            "data.json": json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8"),
        }
        roots = [(self.data / "uploads" / project_id, f"uploads/{project_id}")]
        roots.extend((self.data / "runs" / job_id, f"runs/{job_id}") for job_id in job_ids)
        roots.append((self.data / "scrapes" / project_id, f"scrapes/{project_id}"))
        for root, prefix in roots:
            root = root.resolve()
            if not root.is_dir():
                continue
            if not root.is_relative_to(self.data.resolve()):
                raise ValueError("项目文件路径校验失败。")
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if not path.resolve().is_relative_to(root):
                    raise ValueError("项目文件路径校验失败。")
                if prefix.startswith("runs/") and (
                    path.name.startswith("codex-diagnostics") and path.suffix == ".log"
                    or path.name.startswith("model-output") and path.suffix == ".md"
                ):
                    # Connection diagnostics and raw CLI attempts are local
                    # troubleshooting files, not portable product deliverables.
                    continue
                relative = path.relative_to(root).as_posix()
                capture_parts = Path(relative).parts
                is_capture = prefix.startswith("scrapes/") and bool(capture_parts) and capture_parts[0].startswith("android-")
                if is_capture and self._capture_private_file(Path(*capture_parts[1:])):
                    continue
                member = self._safe_archive_member(f"{prefix}/{relative}")
                file_content = path.read_bytes()
                # Run records are useful for handoff, but their image paths
                # and scraper root are local-machine details. Keep the record
                # while stripping those details from the exported copy.
                if path.name == "执行记录.json":
                    try:
                        record = json.loads(file_content.decode("utf-8"))
                        if isinstance(record, dict):
                            sources = record.get("sources")
                            if isinstance(sources, list):
                                for source in sources:
                                    if isinstance(source, dict):
                                        source.pop("image_path", None)
                            file_content = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
                    except (UnicodeDecodeError, ValueError, TypeError):
                        pass
                elif is_capture and path.name in {"session.json", "request.json", "capture-session.json", "aw.json"}:
                    try:
                        record = json.loads(file_content.decode("utf-8"))
                        if not isinstance(record, dict):
                            raise ValueError("invalid capture metadata")
                        # A checkpoint's pending action is original evidence;
                        # sanitize only optional execution fields at its root.
                        if path.name == "capture-session.json":
                            record = {key: value for key, value in record.items() if str(key).lower() not in self._CAPTURE_LOCAL_KEYS}
                        else:
                            record = self._portable_capture_metadata(record)
                        file_content = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
                    except (UnicodeDecodeError, ValueError, TypeError) as exc:
                        raise ValueError("Android 截图会话元数据无法安全导出。") from exc
                elif path.name == "request.json" and prefix.startswith("scrapes/"):
                    try:
                        request = json.loads(file_content.decode("utf-8"))
                        request.pop("root", None)
                        request.pop("output_dir", None)
                        file_content = json.dumps(request, ensure_ascii=False, indent=2).encode("utf-8")
                    except (UnicodeDecodeError, ValueError, TypeError):
                        pass
                files[member] = file_content
        manifest = {
            "package": "workbench-project-v1",
            "project_id": project_id,
            "project_name": project["name"],
            "created_at": now(),
            "files": [
                {"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                for name, content in sorted(files.items())
            ],
        }
        files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(files.items()):
                archive.writestr(name, content)
        return result.getvalue(), f"{self._safe_export_name(project['name'])}-项目包.zip"

    def _remap_sources(self, raw_sources, project_id, document_map, job_map):
        try:
            sources = json.loads(raw_sources or "[]") if isinstance(raw_sources, str) else list(raw_sources or [])
        except (TypeError, ValueError):
            sources = []
        for source in sources:
            old_id = str(source.get("source_id", ""))
            new_id = document_map.get(old_id) or job_map.get(old_id)
            if new_id:
                source["source_id"] = new_id
                source.pop("image_path", None)
                if source.get("kind") == "upload" and Path(source.get("name", "")).suffix.lower() in IMAGE_SUFFIXES:
                    try:
                        source["image_path"] = str(self.asset(project_id, new_id)[0])
                    except ValueError:
                        pass
            source["text"] = self._remap_asset_refs(source.get("text", ""), document_map)
        return json.dumps(sources, ensure_ascii=False)

    @staticmethod
    def _remap_asset_refs(text, document_map):
        return re.sub(
            r"asset://([a-f0-9]{16,64})",
            lambda match: f"asset://{document_map.get(match.group(1), match.group(1))}",
            str(text or ""),
        )

    def import_project(self, content):
        """Import a project package as a new isolated project copy."""
        if not isinstance(content, (bytes, bytearray)) or not content:
            raise ValueError("项目包为空。")
        if len(content) > MAX_PACKAGE:
            raise ValueError("项目包超过 200 MB。")
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValueError("项目包不是有效的 ZIP 文件。") from exc
        members = {}
        total = 0
        for info in archive.infolist():
            name = self._safe_archive_member(info.filename)
            if info.is_dir():
                continue
            if name in members:
                raise ValueError("项目包包含重复文件。")
            total += info.file_size
            if info.file_size > MAX_PACKAGE or total > MAX_PACKAGE:
                raise ValueError("项目包解压后超过 200 MB。")
            members[name] = archive.read(info)
        if "manifest.json" not in members or "data.json" not in members:
            raise ValueError("项目包缺少 manifest.json 或 data.json。")
        try:
            manifest = json.loads(members["manifest.json"].decode("utf-8"))
            snapshot = json.loads(members["data.json"].decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            raise ValueError("项目包元数据无法读取。") from exc
        if not isinstance(manifest, dict) or not isinstance(snapshot, dict):
            raise ValueError("项目包元数据结构无效。")
        if manifest.get("package") != "workbench-project-v1" or int(snapshot.get("schema_version", 0)) not in {1, 2, 3}:
            raise ValueError("项目包版本不受支持。")
        project = snapshot.get("project") or {}
        if not isinstance(project, dict):
            raise ValueError("项目包中的项目记录无效。")
        old_project_id = str(project.get("id", ""))
        workflow_mode = str(project.get("workflow_mode", "fast")).strip() or "fast"
        platform = str(project.get("platform", "")).strip()
        if (
            not ID_PATTERN.fullmatch(old_project_id)
            or not str(project.get("name", "")).strip()
            or len(str(project.get("name", "")).strip()) > 100
            or workflow_mode not in WORKFLOW_MODES
            or len(platform) > 80
        ):
            raise ValueError("项目包中的项目记录无效。")
        if str(manifest.get("project_id", "")) != old_project_id:
            raise ValueError("项目包的项目 ID 与清单不一致。")
        collections = {}
        collection_labels = {
            "context": "上下文",
            "product_versions": "产品版本",
            "conditions": "条件",
            "documents": "资料",
            "jobs": "任务",
            "reviews": "评审",
            "job_versions": "版本",
            "document_comments": "批注",
            "scrapes": "评论采集记录",
            "version_documents": "版本资料关系",
            "competitors": "竞品档案",
            "competitor_documents": "竞品资料归属",
        }
        for key, label in collection_labels.items():
            value = snapshot.get(key, [])
            if value is None:
                value = []
            if not isinstance(value, list):
                raise ValueError(f"项目包中的{label}记录格式无效。")
            collections[key] = value
        raw_manifest_files = manifest.get("files", [])
        if not isinstance(raw_manifest_files, list):
            raise ValueError("项目包文件清单格式无效。")
        expected = {}
        for item in raw_manifest_files:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ValueError("项目包文件清单格式无效。")
            name = self._safe_archive_member(item["path"])
            if name == "manifest.json" or name in expected:
                raise ValueError("项目包文件清单包含重复或非法路径。")
            try:
                size = int(item.get("size"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"项目包文件大小无效：{name}") from exc
            digest = str(item.get("sha256", ""))
            if size < 0 or size > MAX_PACKAGE or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError(f"项目包文件校验信息无效：{name}")
            expected[name] = {"size": size, "sha256": digest}
        for name, item in expected.items():
            if name not in members or hashlib.sha256(members[name]).hexdigest() != item["sha256"] or len(members[name]) != item["size"]:
                raise ValueError(f"项目包文件校验失败：{name}")
        unexpected = set(members) - set(expected) - {"manifest.json"}
        if unexpected:
            raise ValueError(f"项目包包含未登记文件：{sorted(unexpected)[0]}")

        new_project_id = uid()
        for key, label in (("product_versions", "产品版本"), ("jobs", "任务"), ("documents", "资料"), ("conditions", "条件"), ("job_versions", "任务文档版本"), ("document_comments", "批注"), ("scrapes", "评论采集记录"), ("competitors", "竞品档案")):
            collection = collections[key]
            seen_ids = set()
            for item in collection:
                if not isinstance(item, dict):
                    raise ValueError(f"项目包中的{label}记录格式无效。")
                identifier = str(item.get("id", ""))
                if identifier and not ID_PATTERN.fullmatch(identifier):
                    raise ValueError(f"项目包中的{label} ID 无效。")
                if identifier in seen_ids:
                    raise ValueError(f"项目包中的{label} ID 重复。")
                if identifier:
                    seen_ids.add(identifier)
        job_map = {str(item.get("id")): uid() for item in collections["jobs"] if item.get("id")}
        # Generated deliverables intentionally use the job ID as their
        # document ID.  Keep that relationship intact when remapping a copy.
        document_map = {
            str(item.get("id")): (job_map.get(str(item.get("id"))) or uid() if item.get("kind") in {"accepted", "deliverable"} else uid())
            for item in collections["documents"]
            if item.get("id")
        }
        condition_map = {str(item.get("id")): uid() for item in collections["conditions"] if item.get("id")}
        product_version_map = {str(item.get("id")): uid() for item in collections["product_versions"] if item.get("id")}
        version_map = {str(item.get("id")): uid() for item in collections["job_versions"] if item.get("id")}
        comment_map = {str(item.get("id")): uid() for item in collections["document_comments"] if item.get("id")}
        scrape_map = {str(item.get("id")): uid() for item in collections["scrapes"] if item.get("id")}
        competitor_map = {str(item.get("id")): uid() for item in collections["competitors"] if item.get("id")}
        identities = set()
        for item in collections["competitors"]:
            identity = (str(item.get("platform", "")), str(item.get("app_id", "")))
            if (str(item.get("id", "")) not in competitor_map or item.get("project_id") != old_project_id
                    or identity[0] not in {"google_play", "app_store"} or not identity[1]
                    or len(identity[1]) > 200 or not re.fullmatch(r"[A-Za-z0-9_.-]+", identity[1])
                    or identity[0] == "app_store" and not identity[1].isdigit()
                    or identity in identities or not isinstance(item.get("title"), str)):
                raise ValueError("项目包中的竞品档案身份无效或重复。")
            identities.add(identity)
        link_keys = set()
        for item in collections["competitor_documents"]:
            if not isinstance(item, dict):
                raise ValueError("项目包中的竞品资料归属无效。")
            pair = (str(item.get("competitor_id", "")), str(item.get("document_id", "")))
            if pair[0] not in competitor_map or pair[1] not in document_map or pair in link_keys:
                raise ValueError("项目包中的竞品资料归属引用无效或重复。")
            if item.get("material_type") not in {"store_info", "reviews", "store_screenshot", "device_screenshot", "module_flow", "note", "revenue", "attachment"}:
                raise ValueError("项目包中的竞品资料类型无效。")
            link_keys.add(pair)
        known_jobs = set(job_map)
        review_jobs = set()
        version_keys = set()
        for key, label in (("reviews", "评审"), ("job_versions", "版本"), ("document_comments", "批注")):
            for item in collections[key]:
                if not isinstance(item, dict):
                    raise ValueError(f"项目包中的{label}记录格式无效。")
                job_reference = str(item.get("job_id", ""))
                if job_reference not in known_jobs:
                    raise ValueError(f"项目包中的{label}引用了不存在的任务。")
                if key == "reviews":
                    if job_reference in review_jobs:
                        raise ValueError("项目包中同一任务存在重复评审记录。")
                    review_jobs.add(job_reference)
                elif key == "job_versions":
                    version_key = (job_reference, int(item.get("version", 1) or 1))
                    if version_key in version_keys:
                        raise ValueError("项目包中存在重复的任务版本。")
                    version_keys.add(version_key)
        known_documents = set(document_map)
        known_product_versions = set(product_version_map)
        version_names = set()
        for item in collections["product_versions"]:
            name = str(item.get("name", "")).strip()
            version_type = str(item.get("version_type", "feature")).strip() or "feature"
            status = str(item.get("status", "planning")).strip() or "planning"
            if not name or len(name) > 80 or name in version_names:
                raise ValueError("项目包中的产品版本名无效或重复。")
            if version_type not in PRODUCT_VERSION_TYPES or status not in PRODUCT_VERSION_STATUSES:
                raise ValueError("项目包中的产品版本类型或状态无效。")
            version_names.add(name)
        for item in collections["jobs"] + collections["scrapes"]:
            version_reference = str(item.get("version_id", ""))
            if version_reference and version_reference not in known_product_versions:
                raise ValueError("项目包中的任务或采集记录引用了不存在的产品版本。")
        for item in collections["scrapes"]:
            result_reference = str(item.get("result_doc_id", ""))
            if result_reference and result_reference not in known_documents:
                raise ValueError("项目包中的评论采集记录引用了不存在的资料。")
        version_document_keys = set()
        for item in collections["version_documents"]:
            if not isinstance(item, dict):
                raise ValueError("项目包中的版本资料关系格式无效。")
            key = (str(item.get("version_id", "")), str(item.get("document_id", "")))
            if key[0] not in known_product_versions or key[1] not in known_documents:
                raise ValueError("项目包中的版本资料关系引用无效。")
            if key in version_document_keys:
                raise ValueError("项目包中存在重复的版本资料关系。")
            version_document_keys.add(key)
        import_id = uid()
        staging = (self.data / "imports" / import_id).resolve()
        staging_root = (self.data / "imports").resolve()
        staging.mkdir(parents=True, exist_ok=False)
        moved: list[tuple[Path, Path]] = []
        renamed: list[tuple[Path, Path]] = []
        try:
            # Extract only project data files; metadata remains in memory.
            for name, data in members.items():
                if name in {"manifest.json", "data.json"}:
                    continue
                destination = (staging / name).resolve()
                if not destination.is_relative_to(staging):
                    raise ValueError("项目包文件路径校验失败。")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            # Move files to new UUID namespaces before inserting rows.
            for old_dir, new_dir in (
                (staging / "uploads" / old_project_id, self.data / "uploads" / new_project_id),
                (staging / "scrapes" / old_project_id, self.data / "scrapes" / new_project_id),
            ):
                if old_dir.is_dir():
                    new_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old_dir), str(new_dir))
                    moved.append((old_dir, new_dir))
            # Uploaded binaries are named with their original document UUID.
            # Rename them into the remapped namespace before the DB rows point
            # at the new IDs; otherwise imported inline images would be broken.
            upload_target = self.data / "uploads" / new_project_id
            if upload_target.is_dir():
                for old_id, new_id in document_map.items():
                    for source in upload_target.glob(old_id + ".*"):
                        destination = upload_target / (new_id + source.suffix.lower())
                        if destination.exists():
                            raise ValueError("项目包包含重复的图片文件。")
                        source.rename(destination)
                        renamed.append((source, destination))
            # Collection rows receive new IDs too. Keep their staged evidence
            # and manifest references in that namespace so imported previews
            # and subsequent evidence shortcuts can still resolve documents.
            scrape_target = (self.data / "scrapes" / new_project_id).resolve()
            capture_map = {}
            if scrape_target.is_dir():
                for old_id, new_id in scrape_map.items():
                    source = (scrape_target / old_id).resolve()
                    destination = (scrape_target / new_id).resolve()
                    if not source.is_relative_to(scrape_target) or not destination.is_relative_to(scrape_target):
                        raise ValueError("项目包中的采集路径无效。")
                    if not source.is_dir():
                        continue
                    if destination.exists():
                        raise ValueError("项目包包含重复的采集目录。")
                    source.rename(destination)
                    renamed.append((source, destination))
                    manifest_path = destination / "manifest.json"
                    if manifest_path.is_file():
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        if not isinstance(manifest, dict):
                            raise ValueError("项目包中的竞品资料清单格式无效。")
                        manifest.update({
                            "project_id": new_project_id,
                            "scrape_id": new_id,
                            "version_id": product_version_map.get(str(manifest.get("version_id", "")), ""),
                            "document_ids": [document_map[value] for value in manifest.get("document_ids", []) if isinstance(value, str) and value in document_map],
                            "listing_document_id": document_map.get(str(manifest.get("listing_document_id", "")), ""),
                            "review_document_id": document_map.get(str(manifest.get("review_document_id", "")), ""),
                            "competitor_id": competitor_map.get(str(manifest.get("competitor_id", "")), ""),
                        })
                        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    request_path = destination / "request.json"
                    if request_path.is_file():
                        request = json.loads(self._portable_scrape_request(request_path.read_text(encoding="utf-8"), competitor_map))
                        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
                capture_map = self._import_capture_sessions(scrape_target, old_project_id, new_project_id, product_version_map, document_map, renamed, competitor_map)
            for old_job_id, new_job_id in job_map.items():
                old_dir, new_dir = staging / "runs" / old_job_id, self.data / "runs" / new_job_id
                if old_dir.is_dir():
                    new_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old_dir), str(new_dir))
                    moved.append((old_dir, new_dir))
            with self.db() as db:
                db.execute(
                    "INSERT INTO projects(id,name,brief,created,workflow_mode,platform,team,timebox) VALUES(?,?,?,?,?,?,?,?)",
                    (new_project_id, str(project.get("name", "导入项目"))[:100], str(project.get("brief", ""))[:12000], project.get("created", now()), workflow_mode, platform, "", ""),
                )
                for item in collections["product_versions"]:
                    old_id = str(item.get("id", ""))
                    db.execute(
                        """INSERT INTO product_versions(id,project_id,name,version_type,status,goal,target_date,created,updated)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (product_version_map[old_id], new_project_id, str(item.get("name", ""))[:80], item.get("version_type", "feature"), item.get("status", "planning"), str(item.get("goal", ""))[:2000], str(item.get("target_date", ""))[:40], item.get("created", now()), item.get("updated", now())),
                    )
                for item in collections["context"][:1]:
                    db.execute("INSERT OR REPLACE INTO contexts(project_id,foundation,working) VALUES(?,?,?)", (new_project_id, str(item.get("foundation", ""))[:12000], str(item.get("working", ""))[:12000]))
                for item in collections["conditions"]:
                    db.execute(
                        "INSERT INTO conditions(id,project_id,title,owner,due,status,evidence,block_level,review_date,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (condition_map.get(str(item.get("id")), uid()), new_project_id, item.get("title", ""), item.get("owner", ""), item.get("due", ""), item.get("status", "open"), item.get("evidence", ""), item.get("block_level", "internal-test"), item.get("review_date", item.get("due", "")), item.get("created", now()), item.get("updated", now())),
                    )
                for item in collections["documents"]:
                    new_id = document_map.get(str(item.get("id")), uid())
                    db.execute(
                        "INSERT INTO documents(id,project_id,name,text,sha,created,kind,category,subcategory) VALUES(?,?,?,?,?,?,?,?,?)",
                        (new_id, new_project_id, item.get("name", "资料"), self._remap_asset_refs(item.get("text", ""), document_map), item.get("sha", ""), item.get("created", now()), item.get("kind", "upload"), item.get("category") or infer_material_category(item.get("name", "资料"), item.get("kind", "upload")), item.get("subcategory") or infer_image_subcategory(item.get("name", "资料"), item.get("category") or infer_material_category(item.get("name", "资料"), item.get("kind", "upload")))),
                    )
                for item in collections["competitors"]:
                    store_url = (f"https://play.google.com/store/apps/details?id={item['app_id']}" if item["platform"] == "google_play" else f"https://apps.apple.com/app/id{item['app_id']}")
                    db.execute("INSERT INTO competitors(id,project_id,platform,app_id,title,source_url,role,note,archived,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                        competitor_map[item["id"]], new_project_id, item["platform"], item["app_id"], item["title"][:300], store_url,
                        str(item.get("role", ""))[:40], str(item.get("note", ""))[:4000], int(bool(item.get("archived", 0))), item.get("created", now()), item.get("updated", now())))
                for item in collections["competitor_documents"]:
                    metadata = item.get("metadata", "{}")
                    try:
                        metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
                        if not isinstance(metadata, dict):
                            raise ValueError()
                    except (ValueError, TypeError):
                        raise ValueError("项目包中的竞品资料元数据无效。") from None
                    for field, remapping in (("version_id", product_version_map), ("document_id", document_map), ("competitor_id", competitor_map)):
                        if field in metadata:
                            metadata[field] = remapping.get(str(metadata[field]), "")
                    source_id = str(item.get("source_id", ""))
                    source_id = scrape_map.get(source_id, capture_map.get(source_id, document_map.get(source_id, source_id)))
                    db.execute("INSERT INTO competitor_documents(competitor_id,document_id,material_type,source_type,source_id,captured_at,metadata) VALUES(?,?,?,?,?,?,?)", (
                        competitor_map[item["competitor_id"]], document_map[item["document_id"]], item["material_type"], str(item.get("source_type", "manual"))[:80], source_id,
                        str(item.get("captured_at", ""))[:80], json.dumps(metadata, ensure_ascii=False)))
                for item in collections["jobs"]:
                    old_id = str(item.get("id", ""))
                    status = item.get("status", "prepared")
                    if status in {"queued", "running"}:
                        status = "interrupted"
                    db.execute(
                        """INSERT INTO jobs(id,project_id,task_id,title,status,created,updated,prompt,sources,output,error,workflow_mode,parent_job_id,revision_number,revision_reason,source_version,archived,version_id)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (job_map.get(old_id, uid()), new_project_id, item.get("task_id", ""), item.get("title", ""), status, item.get("created", now()), item.get("updated", now()), item.get("prompt", ""), self._remap_sources(item.get("sources", "[]"), new_project_id, document_map, job_map), self._remap_asset_refs(item.get("output", ""), document_map), "导入时任务未继续执行。" if status == "interrupted" else item.get("error", ""), item.get("workflow_mode", project.get("workflow_mode", "fast")), job_map.get(str(item.get("parent_job_id", "")), ""), int(item.get("revision_number", 1) or 1), item.get("revision_reason", ""), int(item.get("source_version", 0) or 0), int(item.get("archived", 0) or 0), product_version_map.get(str(item.get("version_id", "")), "")),
                    )
                for item in collections["reviews"]:
                    db.execute("INSERT INTO reviews(job_id,decision,note,created) VALUES(?,?,?,?)", (job_map[str(item["job_id"])], item.get("decision", ""), item.get("note", ""), item.get("created", now())))
                for item in collections["job_versions"]:
                    db.execute("INSERT INTO job_versions(id,job_id,version,output,source,note,created) VALUES(?,?,?,?,?,?,?)", (version_map.get(str(item.get("id", "")), uid()), job_map[str(item["job_id"])], int(item.get("version", 1) or 1), self._remap_asset_refs(item.get("output", ""), document_map), item.get("source", "legacy"), item.get("note", ""), item.get("created", now())))
                for item in collections["document_comments"]:
                    db.execute("INSERT INTO document_comments(id,job_id,version,block_id,block_type,block_label,quote,action,note,status,author,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (comment_map.get(str(item.get("id", "")), uid()), job_map[str(item["job_id"])], int(item.get("version", 1) or 1), item.get("block_id", ""), item.get("block_type", "paragraph"), item.get("block_label", ""), item.get("quote", ""), item.get("action", "modify"), item.get("note", ""), item.get("status", "open"), item.get("author", "本地评审人"), item.get("created", now()), item.get("updated", now())))
                for item in collections["scrapes"]:
                    scrape_status = item.get("status", "completed")
                    if scrape_status in {"queued", "running", "ready"}:
                        scrape_status = "failed"
                    scrape_error = item.get("error", "")
                    if item.get("status") in {"queued", "running", "ready"}:
                        scrape_error = "导入时未携带可继续确认的采集状态，请重新采集。"
                    db.execute("INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,review_count,warning_count,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (scrape_map.get(str(item.get("id", "")), uid()), new_project_id, item.get("platform", ""), item.get("app_id", ""), self._portable_scrape_request(item.get("request", "{}"), competitor_map), scrape_status, document_map.get(str(item.get("result_doc_id", "")), ""), item.get("created", now()), item.get("updated", now()), scrape_error, int(item.get("review_count", 0) or 0), int(item.get("warning_count", 0) or 0), product_version_map.get(str(item.get("version_id", "")), "")))
                for item in collections["version_documents"]:
                    db.execute(
                        "INSERT INTO version_documents(version_id,document_id,relation,created) VALUES(?,?,?,?)",
                        (product_version_map[str(item["version_id"])], document_map[str(item["document_id"])], item.get("relation", "evidence"), item.get("created", now())),
                    )
        except Exception:
            for source, destination in reversed(renamed):
                if destination.exists() and not source.exists():
                    destination.rename(source)
            for source, destination in reversed(moved):
                if destination.exists() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination), str(source))
            raise
        finally:
            if staging.exists() and staging.is_relative_to(staging_root):
                shutil.rmtree(staging, ignore_errors=True)
        if int(snapshot.get("schema_version", 0)) < 3:
            self.competitor_service.migrate_project(new_project_id)
        else:
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)", (self.competitor_service.MIGRATION + ":" + new_project_id, json.dumps({"completed": now()})))
        return self.project(new_project_id)
