"""Project lifecycle, context, trash and workflow-condition operations."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class ProjectService(BoundService):
    def __init__(self, workbench):
        super().__init__(workbench)
        # Trash metadata keyed by directory; invalidated by export mtime/size.
        object.__setattr__(self, "_trash_cache", {})

    def project(self, project_id):
        rows = self.rows("SELECT * FROM projects WHERE id=?", (project_id,))
        if not rows:
            raise ValueError("项目不存在。")
        return rows[0]

    def context(self, project_id):
        result = self.rows("SELECT foundation,working FROM contexts WHERE project_id=?", (project_id,))
        return result[0] if result else {"foundation":"", "working":""}

    def create_project(self, name, brief, workflow_mode="fast", platform="", team="", timebox=""):
        name, brief = str(name).strip(), str(brief).strip()
        workflow_mode = str(workflow_mode).strip() or "fast"
        platform, team, timebox = str(platform).strip(), str(team).strip(), str(timebox).strip()
        if not name or len(name) > 100 or len(brief) > 12000:
            raise ValueError("项目名称必填且不超过 100 字，背景不超过 12000 字。")
        if workflow_mode not in WORKFLOW_MODES:
            raise ValueError("工作流模式无效。")
        if len(platform) > 80 or len(team) > 1000 or len(timebox) > 80:
            raise ValueError("平台、团队或验证周期内容过长。")
        project_id = uid()
        with self.db() as db:
            db.execute(
                "INSERT INTO projects(id,name,brief,created,workflow_mode,platform,team,timebox) VALUES(?,?,?,?,?,?,?,?)",
                (project_id,name,brief,now(),workflow_mode,platform,team,timebox),
            )
            db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)", (
                "migration:competitor-dossiers-v1:" + project_id, json.dumps({"completed": now()})))
        return self.project(project_id)

    def update_project(self, project_id, brief, workflow_mode=None, platform=None, team=None, timebox=None):
        project = self.project(project_id)
        values = {
            "brief": str(brief),
            "workflow_mode": str(workflow_mode if workflow_mode is not None else project["workflow_mode"]).strip(),
            "platform": str(platform if platform is not None else project["platform"]).strip(),
            "team": str(team if team is not None else project["team"]).strip(),
            "timebox": str(timebox if timebox is not None else project["timebox"]).strip(),
        }
        if len(values["brief"]) > 12000 or values["workflow_mode"] not in WORKFLOW_MODES:
            raise ValueError("项目背景或工作流模式无效。")
        if len(values["platform"]) > 80 or len(values["team"]) > 1000 or len(values["timebox"]) > 80:
            raise ValueError("平台、团队或验证周期内容过长。")
        with self.db() as db:
            db.execute(
                "UPDATE projects SET brief=?,workflow_mode=?,platform=?,team=?,timebox=? WHERE id=?",
                (values["brief"],values["workflow_mode"],values["platform"],values["team"],values["timebox"],project_id),
            )
        return self.project(project_id)

    def delete_project(self, project_id, confirmation):
        with self.lock:
            project = self.project(project_id)
            if not isinstance(confirmation,str) or confirmation.strip() != project["name"]:
                raise ValueError("项目名称不匹配，未执行删除。")
            active = self.rows(
                "SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running')",
                (project_id,),
            )
            if active:
                raise ValueError("项目仍有生成任务运行中，请先停止任务再删除。")
            if self.rows("SELECT id FROM scrapes WHERE project_id=? AND status IN ('queued','running')", (project_id,)):
                raise ValueError("项目仍有评论采集任务运行中，请先停止采集再删除。")
            capture_service = getattr(self._workbench, "android_capture", None)
            has_active_capture = getattr(capture_service, "has_active", None)
            if callable(has_active_capture) and has_active_capture(project_id):
                raise ValueError("项目仍有 Android 截图走查运行中，请先暂停走查再删除。")
            job_ids = [row["id"] for row in self.rows("SELECT id FROM jobs WHERE project_id=?", (project_id,))]
            snapshot = {
                "schema_version": 5,
                "deleted_at": now(),
                "project": project,
                "product_versions": self.rows("SELECT * FROM product_versions WHERE project_id=?", (project_id,)),
                "context": self.rows("SELECT * FROM contexts WHERE project_id=?", (project_id,)),
                "conditions": self.rows("SELECT * FROM conditions WHERE project_id=?", (project_id,)),
                "documents": self.rows("SELECT * FROM documents WHERE project_id=?", (project_id,)),
                "competitors": self.rows("SELECT * FROM competitors WHERE project_id=?", (project_id,)),
                "competitor_documents": self.rows("SELECT d.* FROM competitor_documents d JOIN competitors c ON c.id=d.competitor_id WHERE c.project_id=?", (project_id,)),
                "jobs": self.rows("SELECT * FROM jobs WHERE project_id=?", (project_id,)),
                "reviews": self.rows(
                    "SELECT r.* FROM reviews r JOIN jobs j ON j.id=r.job_id WHERE j.project_id=?",
                    (project_id,),
                ),
                "job_versions": self.rows(
                    "SELECT v.* FROM job_versions v JOIN jobs j ON j.id=v.job_id WHERE j.project_id=? ORDER BY v.job_id,v.version",
                    (project_id,),
                ),
                "document_comments": self.rows(
                    "SELECT c.* FROM document_comments c JOIN jobs j ON j.id=c.job_id WHERE j.project_id=? ORDER BY c.job_id,c.version,c.created",
                    (project_id,),
                ),
                "scrapes": self.rows("SELECT * FROM scrapes WHERE project_id=?", (project_id,)),
                "version_documents": self.rows(
                    """SELECT d.* FROM version_documents d
                       JOIN product_versions v ON v.id=d.version_id WHERE v.project_id=?""",
                    (project_id,),
                ),
            }
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            trash_root = (self.data / "trash").resolve()
            trash_root.mkdir(parents=True,exist_ok=True)
            trash = (trash_root / f"{stamp}-{project_id}").resolve()
            if not trash.is_relative_to(trash_root) or trash.exists():
                raise ValueError("无法创建安全的项目回收目录。")
            trash.mkdir()
            (trash / "project-export.json").write_text(
                json.dumps(snapshot,ensure_ascii=False,indent=2),encoding="utf-8"
            )
            moved = []
            sources = [
                (self.data/"uploads"/project_id,trash/"uploads"),
                (self.data/"scrapes"/project_id,trash/"scrapes"),
            ]
            sources.extend((self.data/"runs"/job_id,trash/"runs"/job_id) for job_id in job_ids)
            try:
                for source, destination in sources:
                    source = source.resolve()
                    destination = destination.resolve()
                    if not source.exists():
                        continue
                    if not source.is_relative_to(self.data) or not destination.is_relative_to(trash):
                        raise ValueError("项目文件路径校验失败，未执行删除。")
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.move(str(source),str(destination))
                    moved.append((source,destination))
                with self.db() as db:
                    db.execute("DELETE FROM reviews WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)", (project_id,))
                    db.execute("DELETE FROM document_comments WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)", (project_id,))
                    db.execute("DELETE FROM job_versions WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)", (project_id,))
                    db.execute("DELETE FROM scrapes WHERE project_id=?", (project_id,))
                    db.execute("DELETE FROM version_documents WHERE version_id IN (SELECT id FROM product_versions WHERE project_id=?)", (project_id,))
                    db.execute("DELETE FROM competitor_documents WHERE competitor_id IN (SELECT id FROM competitors WHERE project_id=?)", (project_id,))
                    db.execute("DELETE FROM competitors WHERE project_id=?", (project_id,))
                    db.execute("DELETE FROM documents WHERE project_id=?", (project_id,))
                    db.execute("DELETE FROM conditions WHERE project_id=?", (project_id,))
                    db.execute("DELETE FROM contexts WHERE project_id=?", (project_id,))
                    db.execute("DELETE FROM jobs WHERE project_id=?", (project_id,))
                    db.execute("DELETE FROM product_versions WHERE project_id=?", (project_id,))
                    db.execute("DELETE FROM projects WHERE id=?", (project_id,))
                self._remove_project_index(project_id)
            except Exception:
                for source, destination in reversed(moved):
                    if destination.exists() and not source.exists():
                        source.parent.mkdir(parents=True,exist_ok=True)
                        shutil.move(str(destination),str(source))
                raise
        return {"deleted":True,"project_id":project_id,"project_name":project["name"],"backup":str(trash)}

    def trash_items(self):
        trash_root = (self.data / "trash").resolve()
        if not trash_root.is_dir():
            return []
        items, cache, seen = [], self._trash_cache, set()
        for directory in sorted(trash_root.iterdir(),reverse=True):
            if not directory.is_dir() or not directory.resolve().is_relative_to(trash_root):
                continue
            export = directory / "project-export.json"
            if not export.is_file():
                continue
            try:
                stat = export.stat()
            except OSError:
                continue
            # /api/state polls this list; full exports can be megabytes, so
            # only re-read one when the file itself changed.
            signature = (stat.st_mtime_ns, stat.st_size)
            seen.add(directory.name)
            cached = cache.get(directory.name)
            if cached and cached[0] == signature:
                metadata = cached[1]
            else:
                try:
                    snapshot = json.loads(export.read_text(encoding="utf-8"))
                    project = snapshot["project"]
                    metadata = {
                        "id": directory.name,
                        "project_id": project.get("id", ""),
                        "name": project.get("name", "未命名项目"),
                        "deleted_at": snapshot.get("deleted_at", ""),
                        "document_count": len(snapshot.get("documents", [])),
                        "job_count": len(snapshot.get("jobs", [])),
                        "version_count": len(snapshot.get("product_versions", [])),
                    }
                except (OSError,ValueError,KeyError,TypeError,AttributeError):
                    cache.pop(directory.name, None)
                    continue
                cache[directory.name] = (signature, metadata)
            items.append({**metadata, "restored": (directory / "restored.json").is_file()})
        for stale in set(cache) - seen:
            cache.pop(stale, None)
        return items

    def _trash_directory(self, trash_id):
        trash_id = str(trash_id).strip()
        if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-f0-9]{32}", trash_id):
            raise ValueError("回收记录无效。")
        trash_root = (self.data / "trash").resolve()
        directory = (trash_root / trash_id).resolve()
        if not directory.is_relative_to(trash_root) or directory.parent != trash_root or not directory.is_dir():
            raise ValueError("回收记录不存在。")
        return directory

    def restore_project(self, trash_id):
        with self.lock:
            directory = self._trash_directory(trash_id)
            export = directory / "project-export.json"
            try:
                snapshot = json.loads(export.read_text(encoding="utf-8"))
                project = snapshot["project"]
                project_id = project["id"]
            except (OSError,ValueError,KeyError,TypeError) as exc:
                raise ValueError("回收记录损坏，无法自动恢复。") from exc
            if (directory / "restored.json").exists():
                raise ValueError("这个项目已经恢复。")
            if self.rows("SELECT id FROM projects WHERE id=?", (project_id,)):
                raise ValueError("同一项目已经存在，不能重复恢复。")
            table_ids = {
                "competitors": [item.get("id", "") for item in snapshot.get("competitors", [])],
                "product_versions": [item.get("id", "") for item in snapshot.get("product_versions", [])],
                "scrapes": [item.get("id", "") for item in snapshot.get("scrapes", [])],
                "documents": [item.get("id", "") for item in snapshot.get("documents", [])],
                "jobs": [item.get("id", "") for item in snapshot.get("jobs", [])],
                "conditions": [item.get("id", "") for item in snapshot.get("conditions", [])],
            }
            for table, identifiers in table_ids.items():
                identifiers = [item for item in identifiers if item]
                if not identifiers:
                    continue
                placeholders = ",".join("?" for _ in identifiers)
                if self.rows(f"SELECT id FROM {table} WHERE id IN ({placeholders})", identifiers):
                    raise ValueError("回收记录与当前数据冲突，未执行恢复。")
            job_ids = [item.get("id", "") for item in snapshot.get("jobs", []) if item.get("id")]
            file_moves = []
            restored_marker = directory / "restored.json"
            sources = [
                (directory / "uploads",self.data / "uploads" / project_id),
                (directory / "scrapes",self.data / "scrapes" / project_id),
            ]
            sources.extend((directory / "runs" / job_id,self.data / "runs" / job_id) for job_id in job_ids)
            for source, destination in sources:
                if not source.exists():
                    continue
                if destination.exists():
                    raise ValueError("恢复目标文件已经存在，未执行恢复。")
            try:
                for source, destination in sources:
                    if not source.exists():
                        continue
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.move(str(source),str(destination))
                    file_moves.append((source,destination))
                with self.db() as db:
                    db.execute(
                        "INSERT INTO projects(id,name,brief,created,workflow_mode,platform,team,timebox) VALUES(?,?,?,?,?,?,?,?)",
                        (project_id,project.get("name",""),project.get("brief",""),project.get("created",now()),project.get("workflow_mode","fast"),project.get("platform","Android-first"),project.get("team",""),project.get("timebox","1–2 周")),
                    )
                    for item in snapshot.get("product_versions", []):
                        db.execute(
                            """INSERT INTO product_versions(id,project_id,name,version_type,status,goal,target_date,created,updated)
                               VALUES(?,?,?,?,?,?,?,?,?)""",
                            (item["id"],project_id,item.get("name",""),item.get("version_type","feature"),item.get("status","planning"),item.get("goal",""),item.get("target_date",""),item.get("created",now()),item.get("updated",now())),
                        )
                    for item in snapshot.get("context", []):
                        db.execute("INSERT INTO contexts(project_id,foundation,working) VALUES(?,?,?)", (project_id,item.get("foundation",""),item.get("working","")))
                    for item in snapshot.get("conditions", []):
                        db.execute(
                            "INSERT INTO conditions(id,project_id,title,owner,due,status,evidence,block_level,review_date,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (item["id"],project_id,item.get("title",""),item.get("owner",""),item.get("due",""),item.get("status","open"),item.get("evidence",""),item.get("block_level","internal-test"),item.get("review_date",item.get("due","")),item.get("created",now()),item.get("updated",now())),
                        )
                    for item in snapshot.get("documents", []):
                        db.execute(
                            "INSERT INTO documents(id,project_id,name,text,sha,created,kind,category,subcategory) VALUES(?,?,?,?,?,?,?,?,?)",
                            (item["id"],project_id,item.get("name",""),item.get("text",""),item.get("sha",""),item.get("created",now()),item.get("kind","upload"),item.get("category") or infer_material_category(item.get("name",""),item.get("kind","upload")),item.get("subcategory") or infer_image_subcategory(item.get("name",""),item.get("category") or infer_material_category(item.get("name",""),item.get("kind","upload")))),
                        )
                    for item in snapshot.get("competitors", []):
                        db.execute("INSERT INTO competitors(id,project_id,platform,app_id,title,source_url,role,note,archived,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                            item["id"],project_id,item["platform"],item["app_id"],item.get("title",item["app_id"]),item.get("source_url",""),item.get("role",""),item.get("note",""),int(bool(item.get("archived",0))),item.get("created",now()),item.get("updated",now())))
                    restored_documents = {item["id"] for item in snapshot.get("documents", [])}
                    restored_competitors = {item["id"] for item in snapshot.get("competitors", [])}
                    for item in snapshot.get("competitor_documents", []):
                        if item.get("competitor_id") not in restored_competitors or item.get("document_id") not in restored_documents:
                            raise ValueError("回收记录中的竞品资料归属无效，未执行恢复。")
                        db.execute("INSERT INTO competitor_documents(competitor_id,document_id,material_type,source_type,source_id,captured_at,metadata) VALUES(?,?,?,?,?,?,?)", (
                            item["competitor_id"],item["document_id"],item.get("material_type","attachment"),item.get("source_type","manual"),item.get("source_id",""),item.get("captured_at",""),item.get("metadata","{}")))
                    for item in snapshot.get("jobs", []):
                        db.execute(
                            """INSERT INTO jobs(id,project_id,task_id,title,status,created,updated,prompt,sources,output,error,workflow_mode,parent_job_id,revision_number,revision_reason,source_version,archived,version_id)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (item["id"],project_id,item.get("task_id",""),item.get("title",""),item.get("status","prepared"),item.get("created",now()),item.get("updated",now()),item.get("prompt",""),item.get("sources","[]"),item.get("output",""),item.get("error",""),item.get("workflow_mode",project.get("workflow_mode","fast")),item.get("parent_job_id",""),int(item.get("revision_number",1) or 1),item.get("revision_reason",""),int(item.get("source_version",0) or 0),int(item.get("archived",0) or 0),item.get("version_id","")),
                        )
                    for item in snapshot.get("reviews", []):
                        db.execute("INSERT INTO reviews(job_id,decision,note,created) VALUES(?,?,?,?)", (item["job_id"],item.get("decision",""),item.get("note",""),item.get("created",now())))
                    for item in snapshot.get("job_versions", []):
                        db.execute("INSERT INTO job_versions(id,job_id,version,output,source,note,created) VALUES(?,?,?,?,?,?,?)", (item["id"],item["job_id"],item.get("version",1),item.get("output",""),item.get("source","legacy"),item.get("note",""),item.get("created",now())))
                    for item in snapshot.get("document_comments", []):
                        db.execute(
                            "INSERT INTO document_comments(id,job_id,version,block_id,block_type,block_label,quote,action,note,status,author,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (item["id"],item["job_id"],item.get("version",1),item.get("block_id",""),item.get("block_type","paragraph"),item.get("block_label",""),item.get("quote",""),item.get("action","modify"),item.get("note",""),item.get("status","open"),item.get("author","本地评审人"),item.get("created",now()),item.get("updated",now())),
                        )
                    for item in snapshot.get("version_documents", []):
                        db.execute(
                            "INSERT INTO version_documents(version_id,document_id,relation,created) VALUES(?,?,?,?)",
                            (item.get("version_id",""),item.get("document_id",""),item.get("relation","evidence"),item.get("created",now())),
                        )
                    for item in snapshot.get("scrapes", []):
                        status = item.get("status", "completed")
                        if status in {"queued", "running"}:
                            status = "failed"
                        error = "恢复后请重新采集。" if item.get("status") in {"queued", "running"} else item.get("error", "")
                        db.execute(
                            """INSERT INTO scrapes(id,project_id,platform,app_id,request,status,result_doc_id,created,updated,error,review_count,warning_count,version_id)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (item["id"],project_id,item.get("platform",""),item.get("app_id",""),item.get("request","{}"),status,item.get("result_doc_id",""),item.get("created",now()),item.get("updated",now()),error,int(item.get("review_count",0) or 0),int(item.get("warning_count",0) or 0),item.get("version_id","")),
                        )
                    restored_marker.write_text(json.dumps({"restored_at":now(),"project_id":project_id},ensure_ascii=False,indent=2),encoding="utf-8")
            except Exception:
                restored_marker.unlink(missing_ok=True)
                for source, destination in reversed(file_moves):
                    if destination.exists() and not source.exists():
                        source.parent.mkdir(parents=True,exist_ok=True)
                        shutil.move(str(destination),str(source))
                raise
        if "competitors" not in snapshot:
            self.competitor_service.migrate_project(project_id)
        else:
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)", (self.competitor_service.MIGRATION + ":" + project_id, json.dumps({"completed": now()})))
        return self.project(project_id)

    def permanently_delete_trash(self, trash_id, confirmation):
        directory = self._trash_directory(trash_id)
        try:
            snapshot = json.loads((directory / "project-export.json").read_text(encoding="utf-8"))
            project_name = str(snapshot["project"]["name"])
            project_id = str(snapshot["project"]["id"])
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise ValueError("回收记录损坏，不能安全删除。") from exc
        if not isinstance(confirmation,str) or confirmation.strip() != project_name:
            raise ValueError("项目名称不匹配，未永久删除。")
        self._remove_project_index(project_id)
        shutil.rmtree(directory)
        return {"deleted":True,"trash_id":trash_id,"project_name":project_name}

    def conditions(self, project_id):
        self.project(project_id)
        return self.rows("SELECT * FROM conditions WHERE project_id=? ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1 WHEN 'waiting_evidence' THEN 2 ELSE 3 END,updated DESC", (project_id,))

    def save_condition(self, project_id, payload):
        self.project(project_id)
        condition_id = str(payload.get("id", "")).strip() or uid()
        title = str(payload.get("title", "")).strip()
        owner = str(payload.get("owner", "")).strip()
        due = str(payload.get("due", "")).strip()
        status = str(payload.get("status", "open")).strip()
        evidence = str(payload.get("evidence", "")).strip()
        block_level = str(payload.get("block_level", "internal-test")).strip()
        review_date = str(payload.get("review_date", due)).strip()
        if not title or len(title) > 300 or not owner or len(owner) > 120 or not due or len(due) > 80:
            raise ValueError("条件、Owner 和截止时间必填，且内容不能过长。")
        if status not in CONDITION_STATUSES or block_level not in BLOCK_LEVELS or len(evidence) > 4000 or len(review_date) > 80:
            raise ValueError("条件状态、阻塞范围或证据无效。")
        if status in {"closed", "waived"} and not evidence:
            raise ValueError("关闭或豁免条件时必须填写证据或决策记录。")
        existing = self.rows("SELECT created,project_id FROM conditions WHERE id=?", (condition_id,))
        if existing and existing[0]["project_id"] != project_id:
            raise ValueError("条件不属于当前项目。")
        created = existing[0]["created"] if existing else now()
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO conditions(id,project_id,title,owner,due,status,evidence,block_level,review_date,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (condition_id,project_id,title,owner,due,status,evidence,block_level,review_date or due,created,now()),
            )
        return self.rows("SELECT * FROM conditions WHERE id=?", (condition_id,))[0]
