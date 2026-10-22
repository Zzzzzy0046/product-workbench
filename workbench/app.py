"""Local product workbench composition root and compatibility facade."""
from __future__ import annotations

import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from workbench.core.runtime import *
from workbench.services.project_service import ProjectService
from workbench.services.capability_service import CapabilityService
from workbench.services.material_service import MaterialService
from workbench.services.export_service import ExportService
from workbench.services.retrieval_service import RetrievalService
from workbench.services.job_service import JobService
from workbench.services.storage_service import StorageService
from workbench.services.validation_service import ValidationService
from workbench.services.version_service import VersionService
from workbench.services.workflow_router_service import WorkflowRouterService
from workbench.services.competitor_revenue_service import CompetitorRevenueService
from workbench.services.competitor_service import CompetitorService
from workbench.services.android_capture_service import AndroidCaptureService
from workbench.services.codex_connection_service import CodexConnectionService
from workbench.adapters.lanhu_adapter import LanhuAdapter
from workbench.adapters.review_scraper import ReviewScraperAdapter
from workbench.adapters.competitor_discovery import CompetitorDiscoveryAdapter
from workbench.adapters.codex_runner import CodexRunner
from workbench.api.handler import Handler


class Workbench:
    def __init__(self, data_dir=None, runner=None):
        self.data = Path(data_dir or os.environ.get("WORKBENCH_DATA", HERE / "data")).resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data / "workbench.sqlite3"
        self.runner = runner or self.run_codex
        configured_retrieval = os.environ.get("WORKBENCH_RETRIEVAL_MODE")
        self.retrieval_mode = (configured_retrieval or ("keyword" if runner is not None else "hybrid")).lower()
        if self.retrieval_mode not in {"keyword", "hybrid", "shadow"}:
            self.retrieval_mode = "hybrid"
        self.retriever = None
        self.retrieval_error = ""
        self.lock = threading.RLock()
        self.processes = {}
        self.scrape_processes = {}
        self.scrape_threads = {}
        self.threads = {}
        self.token = secrets.token_urlsafe(32)
        self.project_service = ProjectService(self)
        self.capability_service = CapabilityService(self)
        self.version_service = VersionService(self)
        self.workflow_router_service = WorkflowRouterService(self)
        self.lanhu_adapter = LanhuAdapter(self)
        self.material_service = MaterialService(self)
        self.export_service = ExportService(self)
        self.review_scraper = ReviewScraperAdapter(self)
        self.competitor_discovery = CompetitorDiscoveryAdapter(self)
        self.competitor_revenue = CompetitorRevenueService(self)
        self.competitor_service = CompetitorService(self)
        self.android_capture = AndroidCaptureService(self)
        self.retrieval_service = RetrievalService(self)
        self.job_service = JobService(self)
        self.codex_runner = CodexRunner(self)
        self.validation_service = ValidationService()
        self.storage_service = StorageService(self)
        self.storage_service.initialize()
        self.codex_connection = CodexConnectionService(self)
        self.android_capture.recover()
        self.competitor_service.migrate()

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.db() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def project(self, *args, **kwargs):
        return self.project_service.project(*args, **kwargs)

    def context(self, *args, **kwargs):
        return self.project_service.context(*args, **kwargs)

    def create_project(self, *args, **kwargs):
        return self.project_service.create_project(*args, **kwargs)

    def update_project(self, *args, **kwargs):
        return self.project_service.update_project(*args, **kwargs)

    def delete_project(self, *args, **kwargs):
        return self.project_service.delete_project(*args, **kwargs)

    def trash_items(self, *args, **kwargs):
        return self.project_service.trash_items(*args, **kwargs)

    def _trash_directory(self, *args, **kwargs):
        return self.project_service._trash_directory(*args, **kwargs)

    def restore_project(self, *args, **kwargs):
        return self.project_service.restore_project(*args, **kwargs)

    def permanently_delete_trash(self, *args, **kwargs):
        return self.project_service.permanently_delete_trash(*args, **kwargs)

    def conditions(self, *args, **kwargs):
        return self.project_service.conditions(*args, **kwargs)

    def save_condition(self, *args, **kwargs):
        return self.project_service.save_condition(*args, **kwargs)

    def registry(self, *args, **kwargs):
        return self.capability_service.registry(*args, **kwargs)

    def task(self, *args, **kwargs):
        return self.capability_service.task(*args, **kwargs)

    def task_definition(self, *args, **kwargs):
        return self.capability_service.task_definition(*args, **kwargs)

    def product_versions(self, *args, **kwargs):
        return self.version_service.list(*args, **kwargs)

    def product_version(self, *args, **kwargs):
        return self.version_service.get(*args, **kwargs)

    def create_product_version(self, *args, **kwargs):
        return self.version_service.create(*args, **kwargs)

    def update_product_version(self, *args, **kwargs):
        return self.version_service.update(*args, **kwargs)

    def workflows(self, *args, **kwargs):
        return self.workflow_router_service.list_presets(*args, **kwargs)

    def lanhu_settings(self, *args, **kwargs):
        return self.lanhu_adapter.lanhu_settings(*args, **kwargs)

    def save_lanhu_settings(self, *args, **kwargs):
        return self.lanhu_adapter.save_lanhu_settings(*args, **kwargs)

    def _source_key(self, *args, **kwargs):
        return self.material_service._source_key(*args, **kwargs)

    def normalize_sources(self, *args, **kwargs):
        return self.material_service.normalize_sources(*args, **kwargs)

    def citation_issues(self, *args, **kwargs):
        return self.material_service.citation_issues(*args, **kwargs)

    def asset_issues(self, *args, **kwargs):
        return self.material_service.asset_issues(*args, **kwargs)

    def add_document(self, *args, **kwargs):
        return self.material_service.add_document(*args, **kwargs)

    def document(self, *args, **kwargs):
        return self.material_service.document(*args, **kwargs)

    def document_file(self, *args, **kwargs):
        return self.material_service.document_file(*args, **kwargs)

    def set_document_category(self, *args, **kwargs):
        return self.material_service.set_document_category(*args, **kwargs)

    def set_document_subcategory(self, *args, **kwargs):
        return self.material_service.set_document_subcategory(*args, **kwargs)

    def translate_review_document(self, *args, **kwargs):
        return self.review_scraper.translate_review_document(*args, **kwargs)

    def add_document_to_version(self, project_id, name, content, version_id):
        return self.material_service.add_document(project_id, name, content, version_id)

    def add_lanhu_snapshot(self, *args, **kwargs):
        return self.material_service.add_lanhu_snapshot(*args, **kwargs)

    def add_lanhu_snapshot_to_version(self, project_id, url, pages, version_id):
        return self.material_service.add_lanhu_snapshot(project_id, url, pages, version_id)

    def upload_path(self, *args, **kwargs):
        return self.material_service.upload_path(*args, **kwargs)

    def asset(self, *args, **kwargs):
        return self.material_service.asset(*args, **kwargs)

    def delete_image(self, *args, **kwargs):
        return self.material_service.delete_image(*args, **kwargs)

    def _safe_export_name(self, *args, **kwargs):
        return self.export_service._safe_export_name(*args, **kwargs)

    def _portable_sources(self, *args, **kwargs):
        return self.export_service._portable_sources(*args, **kwargs)

    def _portable_scrape_request(self, *args, **kwargs):
        return self.export_service._portable_scrape_request(*args, **kwargs)

    def export_job(self, *args, **kwargs):
        return self.export_service.export_job(*args, **kwargs)

    def _safe_archive_member(self, *args, **kwargs):
        return self.export_service._safe_archive_member(*args, **kwargs)

    def export_project(self, *args, **kwargs):
        return self.export_service.export_project(*args, **kwargs)

    def _remap_sources(self, *args, **kwargs):
        return self.export_service._remap_sources(*args, **kwargs)

    def _remap_asset_refs(self, *args, **kwargs):
        return self.export_service._remap_asset_refs(*args, **kwargs)

    def import_project(self, *args, **kwargs):
        return self.export_service.import_project(*args, **kwargs)

    def review_scraper_settings(self, *args, **kwargs):
        return self.review_scraper.review_scraper_settings(*args, **kwargs)

    def save_review_scraper_settings(self, *args, **kwargs):
        return self.review_scraper.save_review_scraper_settings(*args, **kwargs)

    def scrapes(self, *args, **kwargs):
        return self.review_scraper.scrapes(*args, **kwargs)

    def _review_csv(self, *args, **kwargs):
        return self.review_scraper._review_csv(*args, **kwargs)

    def _scrape_date(self, *args, **kwargs):
        return self.review_scraper._scrape_date(*args, **kwargs)

    def start_review_scrape(self, *args, **kwargs):
        return self.review_scraper.start_review_scrape(*args, **kwargs)

    def start_competitor_collection(self, *args, **kwargs):
        return self.review_scraper.start_competitor_collection(*args, **kwargs)

    def search_competitors(self, *args, **kwargs):
        return self.competitor_discovery.search_competitors(*args, **kwargs)

    def competitor_detail(self, *args, **kwargs):
        return self.competitor_discovery.competitor_detail(*args, **kwargs)

    def _update_scrape(self, *args, **kwargs):
        return self.review_scraper._update_scrape(*args, **kwargs)

    def _run_review_scrape(self, *args, **kwargs):
        return self.review_scraper._run_review_scrape(*args, **kwargs)

    def scrape(self, *args, **kwargs):
        return self.review_scraper.scrape(*args, **kwargs)

    def cancel_scrape(self, *args, **kwargs):
        return self.review_scraper.cancel_scrape(*args, **kwargs)

    def confirm_competitor_collection(self, *args, **kwargs):
        return self.review_scraper.confirm_competitor_collection(*args, **kwargs)

    def retry_scrape(self, *args, **kwargs):
        return self.review_scraper.retry_scrape(*args, **kwargs)

    def knowledge(self, *args, **kwargs):
        return self.retrieval_service.knowledge(*args, **kwargs)

    def _keyword_search(self, *args, **kwargs):
        return self.retrieval_service._keyword_search(*args, **kwargs)

    def _hybrid(self, *args, **kwargs):
        return self.retrieval_service._hybrid(*args, **kwargs)

    def _with_image_paths(self, *args, **kwargs):
        return self.retrieval_service._with_image_paths(*args, **kwargs)

    def retrieval_status(self, *args, **kwargs):
        return self.retrieval_service.retrieval_status(*args, **kwargs)

    def search(self, *args, **kwargs):
        return self.retrieval_service.search(*args, **kwargs)

    def _remove_project_index(self, *args, **kwargs):
        return self.retrieval_service._remove_project_index(*args, **kwargs)

    def prepare(self, *args, **kwargs):
        return self.job_service.prepare(*args, **kwargs)

    def prepare_for_version(self, project_id, key, instruction, document_ids=None, version_id=""):
        return self.job_service.prepare(project_id, key, instruction, document_ids, version_id)

    def assemble_sections(self, *args, **kwargs):
        return self.job_service.assemble_sections(*args, **kwargs)

    def job(self, *args, **kwargs):
        return self.job_service.job(*args, **kwargs)

    def comments(self, *args, **kwargs):
        return self.job_service.comments(*args, **kwargs)

    def add_comment(self, *args, **kwargs):
        return self.job_service.add_comment(*args, **kwargs)

    def update_comment(self, *args, **kwargs):
        return self.job_service.update_comment(*args, **kwargs)

    def versions(self, *args, **kwargs):
        return self.job_service.versions(*args, **kwargs)

    def version(self, *args, **kwargs):
        return self.job_service.version(*args, **kwargs)

    def start(self, *args, **kwargs):
        return self.job_service.start(*args, **kwargs)

    def execute(self, *args, **kwargs):
        return self.job_service.execute(*args, **kwargs)

    def complete(self, *args, **kwargs):
        return self.job_service.complete(*args, **kwargs)

    def edit_output(self, *args, **kwargs):
        return self.job_service.edit_output(*args, **kwargs)

    def restore_version(self, *args, **kwargs):
        return self.job_service.restore_version(*args, **kwargs)

    def prepare_revision(self, *args, **kwargs):
        return self.job_service.prepare_revision(*args, **kwargs)

    def review(self, *args, **kwargs):
        return self.job_service.review(*args, **kwargs)

    def revise(self, *args, **kwargs):
        return self.job_service.revise(*args, **kwargs)

    def revise_from_comments(self, *args, **kwargs):
        return self.job_service.revise_from_comments(*args, **kwargs)

    def cancel(self, *args, **kwargs):
        return self.job_service.cancel(*args, **kwargs)

    def restore_cancelled(self, *args, **kwargs):
        return self.job_service.restore_cancelled(*args, **kwargs)

    def restore_job(self, *args, **kwargs):
        return self.job_service.restore_job(*args, **kwargs)

    def archive_job(self, *args, **kwargs):
        return self.job_service.archive_job(*args, **kwargs)

    def run_codex(self, *args, **kwargs):
        return self.codex_runner.run_codex(*args, **kwargs)

    def stop_process(self, *args, **kwargs):
        return self.codex_runner.stop_process(*args, **kwargs)

    def close(self):
        self.codex_connection.close()
        self.android_capture.close()
        self.competitor_discovery.close()
        with self.lock:
            for process in list(self.processes.values()) + list(self.scrape_processes.values()):
                self.stop_process(process)
            if self.retriever is not None:
                self.retriever.close()
                self.retriever = None

    def state(self, project_id=None):
        runtime = self.retrieval_status()
        connection = self.codex_connection.snapshot()
        cli_available = connection["available"]
        cli_error = "" if cli_available else connection.get("message", "未找到 Codex CLI。")
        runtime.update({"available":cli_available,"codex_error":cli_error,"model":configured_model() or "CLI 默认模型","knowledge_count":len(self.knowledge())})
        project = self.project(project_id) if project_id else None
        workflow_mode = project["workflow_mode"] if project else "fast"
        result = {"projects":self.rows("SELECT * FROM projects ORDER BY created DESC"),"trash":self.trash_items(),"packs":self.registry(),"workflows":self.workflows(workflow_mode),"tools":TOOLS,"runtime":runtime,"integrations":{"lanhu":self.lanhu_settings(),"review_scraper":self.review_scraper_settings(),"codex":connection},"token":self.token}
        if project_id:
            result["project"] = project
            result["versions"] = self.product_versions(project_id)
            result["context"] = self.context(project_id)
            result["conditions"] = self.conditions(project_id)
            result["documents"] = self.rows("SELECT id,name,kind,category,subcategory,created,length(text) AS characters FROM documents WHERE project_id=? ORDER BY created DESC", (project_id,))
            links = self.rows(
                """SELECT d.document_id,d.version_id,v.name AS version_name,d.relation
                   FROM version_documents d JOIN product_versions v ON v.id=d.version_id
                   WHERE v.project_id=? ORDER BY v.updated DESC""",
                (project_id,),
            )
            links_by_document = {}
            for link in links:
                links_by_document.setdefault(link["document_id"], []).append({
                    "id": link["version_id"], "name": link["version_name"], "relation": link["relation"]
                })
            for document in result["documents"]:
                document["versions"] = links_by_document.get(document["id"], [])
            result["competitors"] = self.competitor_service.list(project_id)["competitors"]
            result["competitor_document_links"] = self.competitor_service.document_links(project_id)
            for document in result["documents"]:
                associations = [link for link in result["competitor_document_links"] if link["document_id"] == document["id"]]
                document["competitor_ids"] = [link["competitor_id"] for link in associations]
                document["competitor_material_types"] = {link["competitor_id"]: link["material_type"] for link in associations}
            result["scrapes"] = self.scrapes(project_id)
            result["jobs"] = self.rows("""SELECT j.id,j.title,j.task_id,j.status,j.created,j.updated,j.error,j.workflow_mode,j.parent_job_id,j.revision_number,j.revision_reason,j.source_version,j.archived,j.version_id,v.name AS version_name,
                CASE WHEN EXISTS(SELECT 1 FROM jobs child WHERE child.parent_job_id=j.id) THEN 0 ELSE 1 END AS is_latest,
                r.decision AS review_decision,r.created AS review_created
                FROM jobs j LEFT JOIN reviews r ON j.id=r.job_id LEFT JOIN product_versions v ON v.id=j.version_id
                WHERE j.project_id=? ORDER BY j.created DESC, j.rowid DESC""", (project_id,))
            result["mode_mismatch_count"] = sum(1 for item in result["jobs"] if item["workflow_mode"] != result["project"]["workflow_mode"])
        return result


def main():
    parser = argparse.ArgumentParser(description="本地产品工作台")
    parser.add_argument("--port",type=int,default=8765)
    args = parser.parse_args()
    app = Workbench()
    app.registry()
    server = ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    server.app = app
    print(f"产品工作台已启动：http://127.0.0.1:{args.port}",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for process in list(app.processes.values()):
            app.stop_process(process)
        app.close()
        server.server_close()


if __name__ == "__main__":
    import sys
    sys.path.insert(0,str(ROOT/"src"))
    main()
