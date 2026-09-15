"""Product-version lifecycle and document relationships."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class VersionService(BoundService):
    def list(self, project_id):
        self.project(project_id)
        return self.rows(
            """SELECT v.*,
                      (SELECT COUNT(*) FROM jobs j WHERE j.version_id=v.id) AS job_count,
                      (SELECT COUNT(*) FROM version_documents d WHERE d.version_id=v.id) AS document_count
               FROM product_versions v
               WHERE v.project_id=?
               ORDER BY CASE v.status
                   WHEN 'developing' THEN 0 WHEN 'testing' THEN 1 WHEN 'planning' THEN 2
                   WHEN 'released' THEN 3 WHEN 'reviewed' THEN 4 ELSE 5 END,
                   v.updated DESC""",
            (project_id,),
        )

    def get(self, project_id, version_id):
        self.project(project_id)
        rows = self.rows(
            "SELECT * FROM product_versions WHERE id=? AND project_id=?",
            (str(version_id).strip(), project_id),
        )
        if not rows:
            raise ValueError("产品版本不存在或不属于当前项目。")
        return rows[0]

    def resolve(self, project_id, version_id):
        version_id = str(version_id or "").strip()
        return self.get(project_id, version_id) if version_id else None

    @staticmethod
    def _values(payload, existing=None):
        if not isinstance(payload, dict):
            raise ValueError("产品版本参数无效。")
        existing = existing or {}
        values = {
            "name": str(payload.get("name", existing.get("name", ""))).strip(),
            "version_type": str(payload.get("version_type", existing.get("version_type", "feature"))).strip() or "feature",
            "status": str(payload.get("status", existing.get("status", "planning"))).strip() or "planning",
            "goal": str(payload.get("goal", existing.get("goal", ""))).strip(),
            "target_date": str(payload.get("target_date", existing.get("target_date", ""))).strip(),
        }
        if not values["name"] or len(values["name"]) > 80:
            raise ValueError("版本号或版本名必填且不超过 80 字。")
        if values["version_type"] not in PRODUCT_VERSION_TYPES:
            raise ValueError("版本类型无效。")
        if values["status"] not in PRODUCT_VERSION_STATUSES:
            raise ValueError("版本状态无效。")
        if len(values["goal"]) > 2000 or len(values["target_date"]) > 40:
            raise ValueError("版本目标或目标日期过长。")
        return values

    def create(self, project_id, payload):
        self.project(project_id)
        values = self._values(payload)
        version_id, stamp = uid(), now()
        try:
            with self.db() as db:
                db.execute(
                    """INSERT INTO product_versions(id,project_id,name,version_type,status,goal,target_date,created,updated)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (version_id, project_id, values["name"], values["version_type"], values["status"],
                     values["goal"], values["target_date"], stamp, stamp),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("当前项目已有同名版本。") from exc
        return self.get(project_id, version_id)

    def update(self, project_id, version_id, payload):
        existing = self.get(project_id, version_id)
        values = self._values(payload, existing)
        try:
            with self.db() as db:
                db.execute(
                    """UPDATE product_versions
                       SET name=?,version_type=?,status=?,goal=?,target_date=?,updated=?
                       WHERE id=? AND project_id=?""",
                    (values["name"], values["version_type"], values["status"], values["goal"],
                     values["target_date"], now(), version_id, project_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("当前项目已有同名版本。") from exc
        return self.get(project_id, version_id)

    def link_document(self, project_id, document_id, version_id, relation="evidence"):
        version = self.get(project_id, version_id)
        rows = self.rows(
            "SELECT id FROM documents WHERE id=? AND project_id=?",
            (str(document_id).strip(), project_id),
        )
        if not rows:
            raise ValueError("资料不存在或不属于当前项目。")
        relation = str(relation or "evidence").strip()
        if relation not in {
            "evidence", "lanhu", "review-evidence", "competitor-listing",
            "competitor-screenshot", "deliverable",
        }:
            raise ValueError("资料与版本的关系无效。")
        with self.db() as db:
            db.execute(
                """INSERT INTO version_documents(version_id,document_id,relation,created)
                   VALUES(?,?,?,?)
                   ON CONFLICT(version_id,document_id) DO UPDATE SET relation=excluded.relation""",
                (version["id"], rows[0]["id"], relation, now()),
            )
        return {"version_id": version["id"], "document_id": rows[0]["id"], "relation": relation}

    def unlink_document(self, project_id, document_id, version_id):
        self.get(project_id, version_id)
        with self.db() as db:
            removed = db.execute(
                "DELETE FROM version_documents WHERE version_id=? AND document_id=?",
                (version_id, str(document_id).strip()),
            ).rowcount
        if not removed:
            raise ValueError("资料没有关联到该产品版本。")
        return {"removed": True, "version_id": version_id, "document_id": str(document_id).strip()}
