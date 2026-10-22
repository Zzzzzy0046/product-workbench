"""Collection-only composition root. No document-generation or workflow service."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from urllib.parse import urlparse

from workbench.adapters.codex_runner import CodexRunner
from workbench.adapters.competitor_discovery import CompetitorDiscoveryAdapter
from workbench.adapters.review_scraper import ReviewScraperAdapter
from workbench.api.handler import Handler
from workbench.core.constants import HERE
from workbench.services.android_capture_service import AndroidCaptureService, CONFIG_KEY
from workbench.services.competitor_revenue_service import CompetitorRevenueService
from workbench.services.competitor_service import CompetitorService
from workbench.services.export_service import ExportService
from workbench.services.material_service import MaterialService
from workbench.services.project_service import ProjectService
from workbench.services.storage_service import StorageService
from workbench.services.version_service import VersionService

EDITION = 'data-collection'
RELEASE = '2026.10.22.1'


def find_local_adb():
    """Only inspect known local tool locations and the previous local preference."""
    candidates = [os.environ.get('WORKBENCH_ADB_PATH', ''), shutil.which('adb') or '']
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
    prior = local / 'ProductWorkbenchResearch/data/workbench.sqlite3'
    if prior.is_file():
        try:
            with sqlite3.connect(prior.as_uri() + '?mode=ro', uri=True, timeout=2) as db:
                row = db.execute('SELECT value FROM preferences WHERE key=?', (CONFIG_KEY,)).fetchone()
                saved = json.loads(row[0]) if row else {}
                if isinstance(saved, dict):
                    candidates.append(saved.get('adb_path', ''))
        except (OSError, sqlite3.Error, ValueError, TypeError):
            pass
    for variable in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        if os.environ.get(variable):
            candidates.append(str(Path(os.environ[variable]) / 'platform-tools/adb.exe'))
    candidates += [str(local / 'Android/Sdk/platform-tools/adb.exe'), 'C:/Android/platform-tools/adb.exe']
    desktop = Path.home() / 'Desktop'
    for pattern in ('platform-tools/adb.exe', 'Tools/platform-tools/adb.exe',
                    'scrcpy*/adb.exe', 'scrcpy*/*/adb.exe',
                    'Tools/scrcpy*/adb.exe', 'Tools/scrcpy*/*/adb.exe'):
        candidates.extend(str(p) for p in sorted(desktop.glob(pattern)))
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.name.lower() in {'adb.exe', 'adb'} and path.is_file():
            return path.resolve()
    return None


class CollectionCaptureService(AndroidCaptureService):
    def settings(self):
        result = super().settings()
        if not result['adb_available']:
            adb = find_local_adb()
            if adb:
                with self.db() as db:
                    db.execute('INSERT OR REPLACE INTO preferences(key,value) VALUES(?,?)',
                               (CONFIG_KEY, json.dumps({'adb_path': str(adb)})))
                result = super().settings()
        return result


class CollectionWorkbench:
    """Reuse the existing tested collectors, with an explicit small host surface."""
    _DELEGATES = {
        'project_service': ('project', 'context', 'create_project'),
        'material_service': ('add_document', 'document', 'document_file', 'upload_path', 'asset',
                             'citation_issues', 'asset_issues', 'normalize_sources'),
        'export_service': ('export_project', '_safe_export_name'),
        'review_scraper': ('review_scraper_settings', 'save_review_scraper_settings', 'scrapes',
                           'scrape', 'start_competitor_collection', 'start_review_scrape',
                           'cancel_scrape', 'confirm_competitor_collection', 'retry_scrape',
                           'translate_review_document'),
        'competitor_discovery': ('search_competitors', 'competitor_detail'),
    }

    def __init__(self, data_dir):
        self.data = Path(data_dir).expanduser().resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data / 'workbench.sqlite3'
        self.lock = threading.RLock()
        self.processes = {}
        self.scrape_processes, self.scrape_threads = {}, {}
        self.token = secrets.token_urlsafe(32)
        self.project_service = ProjectService(self)
        self.version_service = VersionService(self)
        self.material_service = MaterialService(self)
        self.export_service = ExportService(self)
        self.review_scraper = ReviewScraperAdapter(self)
        self.competitor_discovery = CompetitorDiscoveryAdapter(self)
        self.competitor_revenue = CompetitorRevenueService(self)
        self.competitor_service = CompetitorService(self)
        self.android_capture = CollectionCaptureService(self)
        StorageService(self).initialize()
        self.android_capture.recover()
        self.competitor_service.migrate()

    def __getattr__(self, name):
        for service, allowed in self._DELEGATES.items():
            if name in allowed:
                return getattr(object.__getattribute__(self, service), name)
        raise AttributeError(name)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def rows(self, sql, arguments=()):
        with self.db() as db:
            return [dict(row) for row in db.execute(sql, arguments)]

    stop_process = staticmethod(CodexRunner.stop_process)

    def state(self, project_id=None):
        result = {'edition': EDITION, 'release': RELEASE, 'token': self.token,
                  'projects': self.rows('SELECT id,name,brief,created FROM projects ORDER BY created DESC'),
                  'integrations': {'review_scraper': self.review_scraper_settings()},
                  'documents': [], 'scrapes': []}
        if project_id:
            result['project'] = self.project(project_id)
            result['documents'] = self.rows(
                'SELECT id,name,kind,category,subcategory,created,length(text) AS characters '
                'FROM documents WHERE project_id=? ORDER BY created DESC', (project_id,))
            result['scrapes'] = self.scrapes(project_id)
        return result

    def close(self):
        self.android_capture.close()
        self.competitor_discovery.close()
        with self.lock:
            for process in list(self.scrape_processes.values()):
                self.stop_process(process)


class CollectionHandler(Handler):
    server_version = 'DataCollector/1.0'
    _GET_EXACT = {'/api/state', '/api/android-capture/settings', '/api/android-capture/devices',
                  '/api/android-capture/sessions', '/api/competitors/revenue'}
    _GET_PATTERNS = (
        r'/api/assets/[a-f0-9]+/[a-f0-9]+', r'/api/projects/[a-f0-9]+/export',
        r'/api/reviews/scrape/[a-f0-9]+', r'/api/documents/[a-f0-9]+(?:/download)?',
        r'/api/android-capture/sessions/[a-f0-9]+(?:/(?:file|export))?',
    )
    _POST_EXACT = {'/api/projects', '/api/documents', '/api/integrations/review-scraper',
                   '/api/competitors/search', '/api/competitors/detail', '/api/competitors/collect',
                   '/api/competitors/revenue', '/api/reviews/scrape',
                   '/api/android-capture/settings', '/api/android-capture/sessions'}
    _POST_PATTERNS = (r'/api/reviews/scrape/[a-f0-9]+/(?:cancel|retry|confirm)',
                      r'/api/documents/[a-f0-9]+/translate',
                      r'/api/android-capture/sessions/[a-f0-9]+/(?:start|resume|cancel|confirm)')
    _STATIC = {
        '/': ('collection_static/index.html', 'text/html'),
        '/collection.js': ('collection_static/collection.js', 'text/javascript'),
        '/collection.css': ('collection_static/collection.css', 'text/css'),
        '/style.css': ('static/style.css', 'text/css'),
        **{f'/features/{name}.js': (f'static/features/{name}.js', 'text/javascript')
           for name in ('android_capture', 'integrations', 'competitor_discovery', 'competitor_revenue')},
    }

    @classmethod
    def allowed(cls, path, method):
        exact, patterns = (cls._GET_EXACT, cls._GET_PATTERNS) if method == 'GET' else (cls._POST_EXACT, cls._POST_PATTERNS)
        return path in exact or any(re.fullmatch(pattern, path) for pattern in patterns)

    def do_GET(self):
        if not self.valid_host():
            return self.respond({'error': '无效 Host。'}, 403)
        path = urlparse(self.path).path
        if path in self._STATIC:
            relative, mime = self._STATIC[path]
            candidate = HERE / relative
            if candidate.is_file():
                return self.respond(candidate.read_bytes(), content_type=mime + '; charset=utf-8')
        if not self.allowed(path, 'GET'):
            return self.respond({'error': '数据采集版不提供此功能。'}, 404)
        return super().do_GET()

    def do_POST(self):
        if not self.allowed(urlparse(self.path).path, 'POST'):
            # Drain bounded request bodies before closing HTTP/1.0 on Windows.
            # Otherwise rejecting a route while its body is still arriving can
            # reset the socket instead of delivering the intended JSON 404.
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if 0 < length <= 1024 * 1024:
                self.rfile.read(length)
            return self.respond({'error': '数据采集版不提供此功能。'}, 404)
        return super().do_POST()
