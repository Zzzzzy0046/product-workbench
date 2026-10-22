"""Project-local competitor dossiers and explicit, traceable evidence selection.

Files and document identifiers remain unchanged: dossiers only add relations.
No document is guessed into a dossier from a filename or an application title.
"""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class CompetitorService(BoundService):
    MATERIAL_TYPES = {"store_info", "reviews", "store_screenshot", "device_screenshot", "module_flow", "note", "revenue", "attachment"}
    ROLES = {"", "primary", "feature", "monetization"}
    MIGRATION = "migration:competitor-dossiers-v1"

    @staticmethod
    def _json(value):
        try:
            result = json.loads(value or "{}")
            return result if isinstance(result, dict) else {}
        except (ValueError, TypeError):
            return {}

    @staticmethod
    def identity(payload):
        platform = str(payload.get("platform") or "").strip()
        app_id = str(payload.get("app_id") or "").strip()
        if platform not in {"google_play", "app_store"} or not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", app_id):
            raise ValueError("竞品平台或应用 ID 无效。")
        if platform == "app_store" and not app_id.isdigit():
            raise ValueError("App Store 应用 ID 必须为数字。")
        return platform, app_id

    @staticmethod
    def _text(payload, field, maximum):
        value = payload.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > maximum or "\x00" in value:
            raise ValueError(f"竞品 {field} 字段无效或过长。")
        return value.strip()

    def get(self, project_id, competitor_id, include_archived=False):
        self.project(project_id)
        rows = self.rows("SELECT * FROM competitors WHERE id=? AND project_id=?", (str(competitor_id or ""), project_id))
        if not rows or (rows[0]["archived"] and not include_archived):
            raise ValueError("竞品档案不存在、已归档或不属于当前项目。")
        return rows[0]

    def upsert(self, project_id, payload):
        self.project(project_id)
        if not isinstance(payload, dict):
            raise ValueError("竞品档案参数无效。")
        platform, app_id = self.identity(payload)
        title = self._text(payload, "title", 300) or app_id
        note = self._text(payload, "note", 5000)
        role = str(payload.get("role") or "")
        if role not in self.ROLES:
            raise ValueError("竞品参考用途无效。")
        # Store links are derived from validated identity, not arbitrary URLs.
        source_url = (f"https://play.google.com/store/apps/details?id={app_id}" if platform == "google_play"
                      else f"https://apps.apple.com/app/id{app_id}")
        identifier = hashlib.sha256(f"competitor:{project_id}:{platform}:{app_id}".encode()).hexdigest()[:32]
        stamp = now()
        with self.db() as db:
            db.execute("""INSERT INTO competitors(id,project_id,platform,app_id,title,source_url,role,note,archived,created,updated)
                          VALUES(?,?,?,?,?,?,?,?,0,?,?) ON CONFLICT(project_id,platform,app_id) DO NOTHING""",
                       (identifier, project_id, platform, app_id, title, source_url, role, note, stamp, stamp))
            row = dict(db.execute("SELECT * FROM competitors WHERE project_id=? AND platform=? AND app_id=?", (project_id, platform, app_id)).fetchone())
            # Re-collecting cannot overwrite a user's custom title, note, or role.
            if row["title"] == app_id and title != app_id:
                db.execute("UPDATE competitors SET title=?,updated=? WHERE id=?", (title, stamp, row["id"]))
                row.update(title=title, updated=stamp)
        return row

    def update(self, project_id, competitor_id, payload):
        row = self.get(project_id, competitor_id, include_archived=True)
        values = {}
        for field, maximum in (("title", 300), ("note", 5000)):
            if field in payload:
                values[field] = self._text(payload, field, maximum)
        if "title" in values and not values["title"]:
            raise ValueError("竞品名称不能为空。")
        if "role" in payload:
            if payload["role"] not in self.ROLES:
                raise ValueError("竞品参考用途无效。")
            values["role"] = payload["role"]
        if "archived" in payload:
            if not isinstance(payload["archived"], bool):
                raise ValueError("归档状态无效。")
            values["archived"] = int(payload["archived"])
        if values:
            values["updated"] = now()
            with self.db() as db:
                db.execute("UPDATE competitors SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=? AND project_id=?", (*values.values(), row["id"], project_id))
        return self.get(project_id, competitor_id, include_archived=True)

    @staticmethod
    def infer_type(document):
        name = str(document.get("name") or "")
        category = str(document.get("category") or "")
        if name.startswith("模块流程-"):
            return "module_flow"
        if name.startswith(("实机截图-", "实机走查索引-")):
            return "note" if name.startswith("实机走查索引-") else "device_screenshot"
        if category == "images":
            return "store_screenshot" if name.startswith("竞品截图-") else "attachment"
        if name.startswith("竞品收入-"):
            return "revenue"
        if name.startswith("竞品商店信息-"):
            return "store_info"
        if category == "reviews" or name.startswith("竞品评论-"):
            return "reviews"
        return "attachment"

    @staticmethod
    def _ids(values, label):
        if not isinstance(values, list) or len(values) > 2000 or any(not isinstance(value, str) or not value or len(value) > 120 for value in values):
            raise ValueError(f"{label}列表无效。")
        return list(dict.fromkeys(values))

    def attach_documents(self, project_id, competitor_id, document_ids, material_type="", source_type="manual", source_id="", captured_at="", metadata=None):
        self.get(project_id, competitor_id, include_archived=source_type == "migration")
        identifiers = self._ids(document_ids, "资料")
        if material_type and material_type not in self.MATERIAL_TYPES:
            raise ValueError("竞品资料类型无效。")
        docs = []
        for identifier in identifiers:
            rows = self.rows("SELECT id,name,kind,category,created FROM documents WHERE id=? AND project_id=?", (identifier, project_id))
            if not rows or rows[0]["kind"] != "upload":
                raise ValueError("只能关联当前项目的已入库原始资料，不能关联其他项目或生成草稿。")
            docs.append(rows[0])
        with self.db() as db:
            for document in docs:
                db.execute("""INSERT INTO competitor_documents(competitor_id,document_id,material_type,source_type,source_id,captured_at,metadata)
                              VALUES(?,?,?,?,?,?,?) ON CONFLICT(competitor_id,document_id) DO UPDATE SET
                              material_type=excluded.material_type,source_type=excluded.source_type,source_id=excluded.source_id,
                              captured_at=excluded.captured_at,metadata=excluded.metadata""",
                           (competitor_id, document["id"], material_type or self.infer_type(document), source_type, str(source_id),
                            str(captured_at or document["created"] or now()), json.dumps(metadata or {}, ensure_ascii=False)))
            if docs:
                db.execute("UPDATE competitors SET updated=? WHERE id=?", (now(), competitor_id))
        return {"competitor_id": competitor_id, "document_ids": identifiers}

    def unlink_documents(self, project_id, competitor_id, document_ids):
        self.get(project_id, competitor_id, include_archived=True)
        identifiers = self._ids(document_ids, "资料")
        with self.db() as db:
            for identifier in identifiers:
                db.execute("DELETE FROM competitor_documents WHERE competitor_id=? AND document_id=?", (competitor_id, identifier))
        return {"competitor_id": competitor_id, "document_ids": identifiers, "unlinked": True, "files_deleted": False}

    def document_links(self, project_id):
        self.project(project_id)
        return self.rows("""SELECT cd.* FROM competitor_documents cd JOIN competitors c ON c.id=cd.competitor_id
                            JOIN documents d ON d.id=cd.document_id WHERE c.project_id=? AND d.project_id=?""", (project_id, project_id))

    def _documents(self, project_id, competitor_id, version_id=None):
        if version_id is not None:
            self.version_service.resolve(project_id, version_id)
        rows = self.rows("""SELECT d.id,d.name,d.kind,d.category,d.subcategory,d.created,d.sha,length(d.text) AS characters,cd.*
                            FROM competitor_documents cd JOIN documents d ON d.id=cd.document_id
                            WHERE cd.competitor_id=? AND d.project_id=? AND d.kind='upload' ORDER BY cd.captured_at DESC,d.id""", (competitor_id, project_id))
        if version_id is None:
            return rows
        eligible = self._eligible_document_ids(project_id, version_id)
        return [row for row in rows if row["document_id"] in eligible]

    def _eligible_document_ids(self, project_id, version_id):
        self.version_service.resolve(project_id, version_id)
        rows = self.rows("""SELECT d.id FROM documents d WHERE d.project_id=? AND d.kind='upload' AND
                            (NOT EXISTS(SELECT 1 FROM version_documents vd WHERE vd.document_id=d.id)
                             OR EXISTS(SELECT 1 FROM version_documents vd WHERE vd.document_id=d.id AND vd.version_id=? AND vd.relation!='deliverable'))""", (project_id, version_id))
        return {row["id"] for row in rows}

    def _batches(self, project_id, competitor, version_id=None, details=False):
        rows = self.rows("SELECT * FROM scrapes WHERE project_id=? AND platform=? AND app_id=? ORDER BY created DESC", (project_id, competitor["platform"], competitor["app_id"]))
        if version_id is not None:
            rows = [row for row in rows if not row.get("version_id") or row.get("version_id") == version_id]
        return [self.review_scraper._with_collection_preview(row, include_listing=details) for row in rows]

    def _summary(self, row, version_id=None):
        documents = self._documents(row["project_id"], row["id"], version_id)
        batches = self._batches(row["project_id"], row, version_id)
        counts = {key: 0 for key in sorted(self.MATERIAL_TYPES)}
        for document in documents:
            counts[document["material_type"]] += 1
        counts["documents"] = len(documents)
        pending = [batch for batch in batches if batch["status"] in {"ready", "queued", "running"}]
        dates = [str(document.get("captured_at") or "") for document in documents] + [str(batch.get("updated") or "") for batch in batches if batch["status"] in {"completed", "ready"}]
        return {**row, "counts": counts, "document_count": len(documents), "pending_count": len(pending),
                "review_count": sum(int(batch.get("review_count") or 0) for batch in batches if batch["status"] == "completed"),
                "last_collected": max(dates, default=""), "status": "pending" if pending else "confirmed" if documents else "empty"}

    def list(self, project_id, version_id=None):
        self.project(project_id)
        if version_id is not None:
            self.version_service.resolve(project_id, version_id)
        rows = self.rows("SELECT * FROM competitors WHERE project_id=? ORDER BY archived,updated DESC,id", (project_id,))
        return {"competitors": [self._summary(row, version_id) for row in rows]}

    def detail(self, project_id, competitor_id, version_id=None):
        row = self.get(project_id, competitor_id, include_archived=True)
        captures = []
        if row["platform"] == "google_play":
            for directory, record in self.android_capture._records(project_id):
                if record.get("package") == row["app_id"] and (version_id is None or not record.get("version_id") or record.get("version_id") == version_id):
                    captures.append(self.android_capture._public(directory, record, details=False))
        return {**self._summary(row, version_id), "documents": self._documents(project_id, competitor_id, version_id),
                "scrapes": self._batches(project_id, row, version_id, details=True), "captures": captures}

    def resolve_inputs(self, project_id, version_id, competitor_ids, document_ids):
        """Validate an explicit input snapshot; choosing a competitor never adds files."""
        self.project(project_id)
        selected = self._ids(competitor_ids or [], "竞品")
        documents = self._ids(document_ids or [], "资料")
        for identifier in selected:
            self.get(project_id, identifier)
        eligible = self._eligible_document_ids(project_id, version_id or "")
        if any(identifier not in eligible for identifier in documents):
            raise ValueError("所选资料未确认入库、不属于当前项目或不在当前版本范围内。")
        associations = self.document_links(project_id)
        by_document = {}
        for link in associations:
            by_document.setdefault(link["document_id"], set()).add(link["competitor_id"])
        # Common/unassigned project evidence is allowed; competitor evidence must
        # belong to one of the expressly selected, non-archived dossiers.
        for identifier in documents:
            if identifier in by_document and not (by_document[identifier] & set(selected)):
                raise ValueError("所选竞品资料与勾选的竞品不一致，请同时勾选所属竞品。")
        sources = []
        for identifier in documents:
            document = self.rows("SELECT id,name,sha,created FROM documents WHERE id=? AND project_id=?", (identifier, project_id))[0]
            sources.append({**document, "competitor_ids": sorted(by_document.get(identifier, set()) & set(selected))})
        return {"document_ids": documents, "competitor_ids": selected, "sources": sources, "captured_at": now(), "source_selection_mode": "explicit"}

    def bind_scrape(self, scrape):
        request = self._json(scrape.get("request"))
        manifest = self.review_scraper._collection_manifest(scrape)
        listing = manifest.get("listing") if isinstance(manifest.get("listing"), dict) else {}
        selection = request.get("selection") if isinstance(request.get("selection"), dict) else {}
        competitor = self.upsert(scrape["project_id"], {"platform": scrape["platform"], "app_id": scrape["app_id"],
                                  "title": listing.get("title") or selection.get("title") or scrape["app_id"],
                                  "role": selection.get("role") or "", "note": selection.get("note") or ""})
        if scrape.get("status") == "completed":
            raw_ids = manifest.get("document_ids")
            raw_ids = raw_ids if isinstance(raw_ids, list) else []
            raw_ids += [scrape["result_doc_id"]] if scrape.get("result_doc_id") else []
            identifiers = list(dict.fromkeys(value for value in raw_ids if isinstance(value, str) and value and len(value) <= 120))
            for identifier in identifiers:
                if self.rows("SELECT id FROM documents WHERE id=? AND project_id=? AND kind='upload'", (identifier, scrape["project_id"])):
                    material_type = "store_info" if identifier == manifest.get("listing_document_id") else "reviews" if identifier == manifest.get("review_document_id") or identifier == scrape.get("result_doc_id") and not manifest else ""
                    self.attach_documents(scrape["project_id"], competitor["id"], [identifier], material_type, "scrape", scrape["id"], scrape.get("updated", ""), {"version_id": scrape.get("version_id", ""), "countries": request.get("countries", [])})
        return competitor

    def migrate(self):
        """One-time conservative migration from structured historical provenance."""
        for project in self.rows("SELECT id FROM projects"):
            self.migrate_project(project["id"])

    def migrate_project(self, project_id):
        self.project(project_id)
        marker = self.MIGRATION + ":" + project_id
        if self.rows("SELECT key FROM preferences WHERE key=?", (marker,)):
            return
        for scrape in self.rows("SELECT * FROM scrapes WHERE project_id=? ORDER BY created,id", (project_id,)):
            try:
                self.bind_scrape(scrape)
            except ValueError:
                continue
        for _, record in self.android_capture._records(project_id):
            try:
                competitor = self.upsert(project_id, {"platform": "google_play", "app_id": record.get("package"), "title": record.get("title") or record.get("package")})
                if record.get("status") == "confirmed":
                    for identifier in record.get("document_ids") or []:
                        if self.rows("SELECT id FROM documents WHERE id=? AND project_id=? AND kind='upload'", (identifier, project_id)):
                            self.attach_documents(project_id, competitor["id"], [identifier], "", "android_capture", record["id"], record.get("confirmed_at") or record.get("created"))
            except ValueError:
                continue
        reverse = {label: key for key, label in self.competitor_revenue.FIELDS.items()}
        for document in self.rows("SELECT id,text FROM documents WHERE project_id=? AND kind='upload' AND name LIKE '竞品收入-%'", (project_id,)):
            if not document["text"].startswith(self.competitor_revenue.HEADER):
                continue
            values = {}
            for line in document["text"].splitlines():
                if line.startswith("- ") and "：" in line:
                    label, value = line[2:].split("：", 1)
                    if label in reverse:
                        values[reverse[label]] = value
            try:
                competitor = self.upsert(project_id, values)
                self.attach_documents(project_id, competitor["id"], [document["id"]], "revenue", "revenue", document["id"])
            except ValueError:
                continue
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)", (marker, json.dumps({"completed": now()})))
