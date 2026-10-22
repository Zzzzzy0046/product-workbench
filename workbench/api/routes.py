"""HTTP path-to-service mappings kept separate from request lifecycle code."""

from workbench.core.runtime import *


def dispatch_get(self, parsed, query):
    if parsed.path == '/api/integrations/codex':
        return self.respond(self.app.codex_connection.snapshot())
    if parsed.path.startswith('/api/android-capture/'):
        service = self.app.android_capture
        path = parsed.path.rstrip('/')
        if path == '/api/android-capture/settings':
            return self.respond(service.settings())
        if path == '/api/android-capture/devices':
            return self.respond(service.devices())
        if path == '/api/android-capture/sessions':
            return self.respond(service.sessions(query.get('project_id', [''])[0], query.get('version_id', [''])[0]))
        parts = path.strip('/').split('/')
        if len(parts) >= 4 and parts[2] == 'sessions':
            session_id = parts[3]
            if len(parts) == 4:
                return self.respond(service.get(session_id))
            if len(parts) == 5 and parts[4] == 'file':
                file = service.file(session_id, query.get('path', [''])[0])
                mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.json': 'application/json; charset=utf-8', '.xml': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.jsonl': 'text/plain; charset=utf-8'}[file.suffix.lower()]
                return self.respond(file.read_bytes(), content_type=mime)
            if len(parts) == 5 and parts[4] == 'export':
                content, filename = service.export(session_id)
                return self.respond(content, content_type='application/zip', filename=filename)
        return self.respond({'error': '未找到实机走查接口。'}, 404)
    if parsed.path == "/api/competitors/revenue":
        values = {key: value[0] for key, value in query.items() if value}
        return self.respond(self.app.competitor_revenue.records(values.get("project_id", ""), values))
    if parsed.path == "/api/competitors":
        scope = query.get("version_id", [""])[0] if "version_id=" in parsed.query else None
        return self.respond(self.app.competitor_service.list(query.get("project_id", [""])[0], scope))
    if parsed.path.startswith("/api/competitors/"):
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3:
            scope = query.get("version_id", [""])[0] if "version_id=" in parsed.query else None
            return self.respond(self.app.competitor_service.detail(query.get("project_id", [""])[0], parts[2], scope))
    if parsed.path == "/api/state":
        return self.respond(self.app.state(query.get("project",[None])[0]))
    if parsed.path == "/api/search":
        return self.respond(self.app.search(query.get("project",[""])[0],query.get("q",[""])[0][:4000]))
    if parsed.path.startswith("/api/assets/"):
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 4:
            raise ValueError("图片地址无效。")
        path, name = self.app.asset(parts[2], parts[3])
        mime = {".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".webp":"image/webp"}.get(Path(name).suffix.lower(), "application/octet-stream")
        return self.respond(path.read_bytes(), content_type=mime)
    if parsed.path.startswith("/api/projects/"):
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 4 and parts[2] and parts[3] == "export":
            content, filename = self.app.export_project(parts[2])
            return self.respond(content, content_type="application/zip", filename=filename)
    if parsed.path.startswith("/api/reviews/scrape/"):
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 4:
            return self.respond(self.app.scrape(parts[3]))
    if parsed.path.startswith("/api/jobs/"):
        parts = parsed.path.strip("/").split("/")
        job = self.app.job(parts[2])
        if len(parts) == 4 and parts[3] == "versions":
            return self.respond(self.app.versions(parts[2]))
        if len(parts) == 5 and parts[3] == "versions":
            return self.respond(self.app.version(parts[2],parts[4]))
        if len(parts) == 4 and parts[3] == "quality":
            return self.respond(job["quality"])
        if len(parts) == 4 and parts[3] == "export":
            version = query.get("version", [None])[0]
            content, content_type, filename = self.app.export_job(parts[2], query.get("format", [""])[0], version)
            return self.respond(content, content_type=content_type, filename=filename)
        if len(parts) == 4 and parts[3] in {"prompt","download"}:
            key = "prompt" if parts[3] == "prompt" else "output"
            label = "任务包" if key == "prompt" else job["title"]
            return self.respond(job[key].encode(),content_type="text/markdown; charset=utf-8",filename=f'{label}-{job["id"][:8]}.md')
        return self.respond(job)
    if parsed.path.startswith("/api/documents/"):
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 4 and parts[3] == "download":
            content, name = self.app.document_file(parts[2])
            content_type = "text/csv; charset=utf-8" if Path(name).suffix.lower() == ".csv" else "application/octet-stream"
            return self.respond(content, content_type=content_type, filename=name)
        if len(parts) == 3:
            return self.respond(self.app.document(parts[2]))
        raise ValueError("资料地址无效。")
    static_request = (
        parsed.path in {"/", "/app.js", "/style.css"}
        or parsed.path.startswith(("/modules/", "/render/", "/features/"))
    )
    if static_request:
        static_root = (HERE / "static").resolve()
        relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        candidate = (static_root / relative).resolve()
        suffix = candidate.suffix.lower()
        if not candidate.is_relative_to(static_root) or suffix not in {".html", ".js", ".css"} or not candidate.is_file():
            return self.respond({"error":"未找到。"},404)
        mime = {".html":"text/html; charset=utf-8", ".js":"text/javascript; charset=utf-8", ".css":"text/css; charset=utf-8"}[suffix]
        return self.respond(candidate.read_bytes(),content_type=mime)
    return self.respond({"error":"未找到。"},404)


def dispatch_post(self, path, payload):
    if (path == '/api/integrations/codex' or path.startswith('/api/integrations/codex/')) and not isinstance(payload, dict):
        raise ValueError('Codex 连接请求必须是 JSON 对象。')
    if path == '/api/integrations/codex':
        return self.respond(self.app.codex_connection.configure(payload))
    if path.startswith('/api/integrations/codex/'):
        action = path.removeprefix('/api/integrations/codex/')
        if action in {'check', 'login', 'test'}:
            return self.respond(self.app.codex_connection.start(action, payload), 202)
        if action == 'cancel':
            return self.respond(self.app.codex_connection.cancel(payload.get('operation_id', '')))
        return self.respond({'error': '未找到 Codex 连接接口。'}, 404)
    if path == '/api/android-capture/settings':
        return self.respond(self.app.android_capture.save_settings(payload))
    if path == '/api/android-capture/sessions':
        return self.respond(self.app.android_capture.create(payload), 201)
    if path.startswith('/api/android-capture/sessions/'):
        parts = path.strip('/').split('/')
        if len(parts) == 5:
            session_id, action = parts[3:]
            service = self.app.android_capture
            if action in {'start', 'resume'}:
                return self.respond(service.start(session_id, resume=action == 'resume'), 202)
            if action == 'cancel':
                return self.respond(service.cancel(session_id))
            if action == 'confirm':
                return self.respond(service.confirm(session_id))
        return self.respond({'error': '未找到实机走查操作。'}, 404)
    if path == "/api/projects":
        return self.respond(self.app.create_project(payload.get("name",""),payload.get("brief",""),payload.get("workflow_mode","fast"),payload.get("platform",""),payload.get("team",""),payload.get("timebox","")),201)
    if path == "/api/project/update":
        return self.respond(self.app.update_project(payload["id"],payload.get("brief",""),payload.get("workflow_mode"),payload.get("platform"),payload.get("team"),payload.get("timebox")))
    if path == "/api/project/delete":
        return self.respond(self.app.delete_project(payload["id"],payload.get("confirmation","")))
    if path == "/api/trash/restore":
        return self.respond(self.app.restore_project(payload["id"]))
    if path == "/api/trash/delete":
        return self.respond(self.app.permanently_delete_trash(payload["id"],payload.get("confirmation","")))
    if path == "/api/conditions":
        return self.respond(self.app.save_condition(payload["project_id"],payload),201)
    if path == "/api/product-versions":
        return self.respond(self.app.create_product_version(payload["project_id"],payload),201)
    if path.startswith("/api/product-versions/"):
        parts = path.strip("/").split("/")
        if len(parts) == 3:
            return self.respond(self.app.update_product_version(payload["project_id"],parts[2],payload))
    if path == "/api/context":
        self.app.project(payload['project_id'])
        foundation, working = str(payload.get('foundation','')),str(payload.get('working',''))
        if len(foundation)>12000 or len(working)>12000:
            raise ValueError("每层上下文不超过 12000 字。")
        with self.app.db() as db:
            db.execute("INSERT OR REPLACE INTO contexts VALUES(?,?,?)", (payload['project_id'],foundation,working))
        return self.respond({"ok":True})
    if path == "/api/documents":
        return self.respond(self.app.add_document(payload["project_id"],payload["name"],base64.b64decode(payload["content"],validate=True),payload.get("version_id",""),"evidence",payload.get("category",""),payload.get("subcategory",""),competitor_id=payload.get("competitor_id",""),material_type=payload.get("material_type","")),201)
    if path.startswith("/api/documents/"):
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[3] == "category":
            return self.respond(self.app.set_document_category(payload["project_id"],parts[2],payload.get("category","")))
        if len(parts) == 4 and parts[3] == "subcategory":
            return self.respond(self.app.set_document_subcategory(payload["project_id"],parts[2],payload.get("subcategory","")))
        if len(parts) == 4 and parts[3] == "delete":
            return self.respond(self.app.delete_image(payload["project_id"], parts[2]))
        if len(parts) == 4 and parts[3] == "translate":
            return self.respond(self.app.translate_review_document(parts[2]))
    if path == "/api/projects/import":
        return self.respond(self.app.import_project(base64.b64decode(payload.get("content", ""), validate=True)), 201)
    if path == "/api/lanhu/snapshot":
        return self.respond(self.app.add_lanhu_snapshot(payload["project_id"],payload.get("url",""),payload.get("pages",[]),payload.get("version_id","")),201)
    if path == "/api/prepare":
        return self.respond(self.app.prepare(payload["project_id"],payload["task"],payload.get("instruction",""),payload.get("document_ids",[]),payload.get("version_id",""),source_selection_mode=payload.get("source_selection_mode","auto"),competitor_ids=payload.get("competitor_ids",[])),201)
    if path == "/api/assemble":
        return self.respond(self.app.assemble_sections(payload["project_id"],payload.get("task","fast/new-product-analysis"),payload.get("version_id","")),201)
    if path == "/api/packs":
        if payload["id"] not in {p["id"] for p in self.app.registry()} or not isinstance(payload["enabled"],bool):
            raise ValueError("能力配置无效。")
        with self.app.db() as db:
            db.execute("INSERT OR REPLACE INTO preferences VALUES(?,?)", ("pack:"+payload["id"],json.dumps(payload["enabled"])))
        return self.respond({"ok":True})
    if path == "/api/integrations/lanhu":
        return self.respond(self.app.save_lanhu_settings(payload))
    if path == "/api/integrations/review-scraper":
        return self.respond(self.app.save_review_scraper_settings(payload))
    if path == "/api/reviews/scrape":
        return self.respond(self.app.start_review_scrape(payload["project_id"], payload), 202)
    if path == "/api/competitors/collect":
        return self.respond(self.app.start_competitor_collection(payload["project_id"], payload), 202)
    if path == "/api/competitors":
        return self.respond(self.app.competitor_service.upsert(payload["project_id"], payload), 201)
    if path == "/api/competitors/inputs":
        return self.respond(self.app.competitor_service.resolve_inputs(payload["project_id"], payload.get("version_id", ""), payload.get("competitor_ids", []), payload.get("document_ids", [])))
    if path.startswith("/api/competitors/"):
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[3] in {"update", "documents", "unlink"}:
            service = self.app.competitor_service
            if parts[3] == "update":
                return self.respond(service.update(payload["project_id"], parts[2], payload))
            if parts[3] == "documents":
                return self.respond(service.attach_documents(payload["project_id"], parts[2], payload.get("document_ids", []), payload.get("material_type", "")))
            return self.respond(service.unlink_documents(payload["project_id"], parts[2], payload.get("document_ids", [])))
    if path == "/api/competitors/revenue":
        return self.respond(self.app.competitor_revenue.save(payload["project_id"], payload), 201)
    if path == "/api/competitors/search":
        return self.respond(self.app.search_competitors(payload["project_id"], payload))
    if path == "/api/competitors/detail":
        return self.respond(self.app.competitor_detail(payload["project_id"], payload))
    if path.startswith("/api/reviews/scrape/"):
        parts = path.strip("/").split("/")
        if len(parts) == 5 and parts[4] == "cancel":
            return self.respond(self.app.cancel_scrape(parts[3]))
        if len(parts) == 5 and parts[4] == "confirm":
            return self.respond(self.app.confirm_competitor_collection(parts[3]))
        if len(parts) == 5 and parts[4] == "retry":
            return self.respond(self.app.retry_scrape(parts[3]), 202)
    if path.startswith("/api/jobs/"):
        parts = path.strip("/").split("/")
        job_id, action = parts[2], parts[3]
        if action == "comments" and len(parts) == 4:
            return self.respond(self.app.add_comment(job_id,payload),201)
        if action == "comments" and len(parts) == 5:
            return self.respond(self.app.update_comment(job_id,parts[4],payload.get("status","")))
        if action == "start":
            return self.respond(self.app.start(job_id))
        if action == "cancel":
            return self.respond(self.app.cancel(job_id))
        if action == "restore-cancelled":
            return self.respond(self.app.restore_cancelled(job_id))
        if action == "restore":
            return self.respond(self.app.restore_job(job_id))
        if action == "archive":
            return self.respond(self.app.archive_job(job_id,payload.get("archived",True)))
        if action == "review":
            return self.respond(self.app.review(job_id,payload['decision'],payload.get('note','')))
        if action == "revise":
            return self.respond(self.app.revise(job_id))
        if action == "revise-comments":
            return self.respond(self.app.revise_from_comments(job_id))
        if action == "edit":
            return self.respond(self.app.edit_output(job_id,payload.get("output",""),payload.get("note","")))
        if action == "versions" and len(parts) == 5:
            return self.respond(self.app.restore_version(job_id,parts[4]))
        if action == "import":
            with self.app.lock:
                if self.app.job(job_id)["status"] != "prepared":
                    raise ValueError("仅待执行任务允许导入外部完成的交付物。")
                self.app.complete(job_id,payload["output"],"imported")
            return self.respond(self.app.job(job_id))
    return self.respond({"error":"未找到。"},404)
