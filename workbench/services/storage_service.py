"""SQLite schema initialization and compatibility migrations."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class StorageService(BoundService):
    def initialize(self):
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT,brief TEXT,created TEXT);
                CREATE TABLE IF NOT EXISTS product_versions(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,name TEXT NOT NULL,version_type TEXT NOT NULL,status TEXT NOT NULL,goal TEXT NOT NULL DEFAULT '',target_date TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL,UNIQUE(project_id,name));
                CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,project_id TEXT,name TEXT,text TEXT,sha TEXT,created TEXT,kind TEXT,category TEXT NOT NULL DEFAULT '',subcategory TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS version_documents(version_id TEXT NOT NULL,document_id TEXT NOT NULL,relation TEXT NOT NULL DEFAULT 'evidence',created TEXT NOT NULL,PRIMARY KEY(version_id,document_id));
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT,task_id TEXT,title TEXT,status TEXT,created TEXT,updated TEXT,prompt TEXT,sources TEXT,output TEXT,error TEXT);
                CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE IF NOT EXISTS contexts(project_id TEXT PRIMARY KEY,foundation TEXT,working TEXT);
                CREATE TABLE IF NOT EXISTS reviews(job_id TEXT PRIMARY KEY,decision TEXT,note TEXT,created TEXT);
                CREATE TABLE IF NOT EXISTS job_versions(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,version INTEGER NOT NULL,output TEXT NOT NULL,source TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,UNIQUE(job_id,version));
                CREATE TABLE IF NOT EXISTS document_comments(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,version INTEGER NOT NULL,block_id TEXT NOT NULL,block_type TEXT NOT NULL,block_label TEXT NOT NULL,quote TEXT NOT NULL,action TEXT NOT NULL,note TEXT NOT NULL,status TEXT NOT NULL,author TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conditions(id TEXT PRIMARY KEY,project_id TEXT,title TEXT,owner TEXT,due TEXT,status TEXT,evidence TEXT,block_level TEXT,review_date TEXT,created TEXT,updated TEXT);
                CREATE TABLE IF NOT EXISTS scrapes(id TEXT PRIMARY KEY,project_id TEXT,platform TEXT,app_id TEXT,request TEXT,status TEXT,result_doc_id TEXT,created TEXT,updated TEXT,error TEXT,review_count INTEGER NOT NULL DEFAULT 0,warning_count INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS documents_project ON documents(project_id);
                CREATE INDEX IF NOT EXISTS product_versions_project ON product_versions(project_id,updated);
                CREATE INDEX IF NOT EXISTS version_documents_document ON version_documents(document_id);
                CREATE INDEX IF NOT EXISTS jobs_project ON jobs(project_id);
                CREATE INDEX IF NOT EXISTS scrapes_project ON scrapes(project_id,created);
                CREATE INDEX IF NOT EXISTS job_versions_job ON job_versions(job_id,version);
                CREATE INDEX IF NOT EXISTS document_comments_job ON document_comments(job_id,version,status);
                CREATE INDEX IF NOT EXISTS conditions_project ON conditions(project_id);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
            for column, declaration in {
                "workflow_mode": "TEXT NOT NULL DEFAULT 'fast'",
                "platform": "TEXT NOT NULL DEFAULT 'Android-first'",
                "team": "TEXT NOT NULL DEFAULT ''",
                "timebox": "TEXT NOT NULL DEFAULT '1–2 周'",
            }.items():
                if column not in columns:
                    db.execute(f"ALTER TABLE projects ADD COLUMN {column} {declaration}")
            condition_columns = {row[1] for row in db.execute("PRAGMA table_info(conditions)")}
            if "review_date" not in condition_columns:
                db.execute("ALTER TABLE conditions ADD COLUMN review_date TEXT NOT NULL DEFAULT ''")
            document_columns = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
            if "category" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN category TEXT NOT NULL DEFAULT ''")
            if "subcategory" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN subcategory TEXT NOT NULL DEFAULT ''")
            uncategorized_documents = db.execute(
                "SELECT id,name,kind FROM documents WHERE category='' OR category IS NULL"
            ).fetchall()
            for document in uncategorized_documents:
                db.execute(
                    "UPDATE documents SET category=? WHERE id=?",
                    (infer_material_category(document["name"], document["kind"]), document["id"]),
                )
            image_documents = db.execute(
                "SELECT id,name,category FROM documents WHERE category='images' AND (subcategory='' OR subcategory IS NULL)"
            ).fetchall()
            for document in image_documents:
                db.execute(
                    "UPDATE documents SET subcategory=? WHERE id=?",
                    (infer_image_subcategory(document["name"], document["category"]), document["id"]),
                )
            scrape_columns = {row[1] for row in db.execute("PRAGMA table_info(scrapes)")}
            if "review_count" not in scrape_columns:
                db.execute("ALTER TABLE scrapes ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0")
            if "warning_count" not in scrape_columns:
                db.execute("ALTER TABLE scrapes ADD COLUMN warning_count INTEGER NOT NULL DEFAULT 0")
            if "version_id" not in scrape_columns:
                db.execute("ALTER TABLE scrapes ADD COLUMN version_id TEXT NOT NULL DEFAULT ''")
            job_columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            for column, declaration in {
                "workflow_mode": "TEXT NOT NULL DEFAULT 'full'",
                "parent_job_id": "TEXT NOT NULL DEFAULT ''",
                "revision_number": "INTEGER NOT NULL DEFAULT 1",
                "revision_reason": "TEXT NOT NULL DEFAULT ''",
                "source_version": "INTEGER NOT NULL DEFAULT 0",
                "archived": "INTEGER NOT NULL DEFAULT 0",
                "version_id": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if column not in job_columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {column} {declaration}")
            db.execute("UPDATE jobs SET workflow_mode='fast' WHERE task_id LIKE 'fast/%'")
            db.execute("UPDATE scrapes SET status='failed',error='服务重启导致采集任务中断，请重新采集。',updated=? WHERE status IN ('running','queued')", (now(),))
            legacy_jobs = db.execute("""
                SELECT j.id,j.output,j.updated FROM jobs j
                WHERE j.status='completed' AND length(j.output)>0
                AND NOT EXISTS(SELECT 1 FROM job_versions v WHERE v.job_id=j.id)
            """).fetchall()
            for legacy in legacy_jobs:
                db.execute(
                    "INSERT INTO job_versions(id,job_id,version,output,source,note,created) VALUES(?,?,?,?,?,?,?)",
                    (uid(),legacy["id"],1,legacy["output"],"legacy","升级工作台时保留的现有交付物",legacy["updated"] or now()),
                )
            # Older generated files embedded review status in the Markdown body.
            # Preserve the original version, then migrate the current body once.
            managed_outputs = db.execute("SELECT id,output FROM jobs WHERE status='completed' AND output LIKE '---%'").fetchall()
            for item in managed_outputs:
                cleaned = normalize_deliverable(item["output"])
                if cleaned == item["output"]:
                    continue
                version = int(db.execute("SELECT COALESCE(MAX(version),0)+1 FROM job_versions WHERE job_id=?", (item["id"],)).fetchone()[0])
                stamp = now()
                db.execute(
                    "INSERT INTO job_versions(id,job_id,version,output,source,note,created) VALUES(?,?,?,?,?,?,?)",
                    (uid(),item["id"],version,cleaned,"migration","工作流状态移出正文元数据",stamp),
                )
                db.execute("UPDATE jobs SET output=?,updated=? WHERE id=?", (cleaned,stamp,item["id"]))
                db.execute(
                    "UPDATE documents SET text=?,sha=? WHERE id=?",
                    (cleaned,hashlib.sha256(cleaned.encode()).hexdigest(),item["id"]),
                )
                directory = self.data / "runs" / item["id"]
                if directory.is_dir():
                    (directory / "交付物.md").write_text(cleaned,encoding="utf-8")
                    (directory / f"交付物-v{version:04d}.md").write_text(cleaned,encoding="utf-8")
            migrated_versions = db.execute("""
                SELECT j.id,j.output,MAX(v.version) AS version
                FROM jobs j JOIN job_versions v ON v.job_id=j.id
                WHERE v.source='migration'
                GROUP BY j.id,j.output
            """).fetchall()
            for item in migrated_versions:
                current_comments = db.execute(
                    "SELECT 1 FROM document_comments WHERE job_id=? AND version=? LIMIT 1",
                    (item["id"],item["version"]),
                ).fetchone()
                if current_comments:
                    continue
                previous = db.execute(
                    "SELECT id,quote FROM document_comments WHERE job_id=? AND version=?",
                    (item["id"],item["version"]-1),
                ).fetchall()
                for comment in previous:
                    if comment["quote"] in item["output"]:
                        db.execute(
                            "UPDATE document_comments SET version=?,updated=? WHERE id=?",
                            (item["version"],now(),comment["id"]),
                        )
            accepted_jobs = db.execute("""
                SELECT j.id,j.title,j.output,j.sources,MAX(v.version) AS version
                FROM jobs j JOIN reviews r ON r.job_id=j.id
                LEFT JOIN job_versions v ON v.job_id=j.id
                WHERE r.decision='accepted'
                GROUP BY j.id,j.title,j.output,j.sources
            """).fetchall()
            for item in accepted_jobs:
                try:
                    sources = json.loads(item["sources"])
                except (TypeError,ValueError):
                    sources = []
                invalid = self.citation_issues(item["output"],sources)
                open_comment = db.execute(
                    "SELECT 1 FROM document_comments WHERE job_id=? AND version=? AND status='open' LIMIT 1",
                    (item["id"],item["version"]),
                ).fetchone()
                if not invalid and not open_comment:
                    continue
                db.execute("DELETE FROM reviews WHERE job_id=?", (item["id"],))
                db.execute(
                    "UPDATE documents SET kind='deliverable',name=? WHERE id=?",
                    (item["title"]+"（待评审草稿）.md",item["id"]),
                )
            db.execute("UPDATE jobs SET status='interrupted',error='服务重启导致任务中断，可重新创建任务。',updated=? WHERE status IN ('running','queued')", (now(),))
