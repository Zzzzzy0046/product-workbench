"""Project documents, images, source normalization and citation integrity."""

from workbench.core.runtime import *
from workbench.services.base import BoundService


class MaterialService(BoundService):
    @staticmethod
    def _review_needs_translation(text, language=""):
        text = str(text or "").strip()
        language = str(language or "").strip().lower()
        if not text or language.startswith("zh") or not any(character.isalpha() for character in text):
            return False
        # A Chinese-only review does not need a duplicate translation even when
        # an imported CSV omitted its language. Japanese kana and Korean Hangul
        # still pass through for translation.
        has_han = bool(re.search(r"[\u3400-\u9fff]", text))
        has_other_script = bool(re.search(r"[A-Za-z\u3040-\u30ff\uac00-\ud7af]", text))
        return not (has_han and not has_other_script)

    def document(self, document_id):
        rows = self.rows(
            "SELECT id,project_id,name,text,kind,category,subcategory,created FROM documents WHERE id=?",
            (str(document_id).strip(),),
        )
        if not rows:
            raise ValueError("资料不存在。")
        document = rows[0]
        if document["kind"] != "upload" or Path(document["name"]).suffix.lower() != ".csv":
            return document
        path = self.upload_path(document["project_id"], document["id"], document["name"]).resolve()
        root = (self.data / "uploads" / document["project_id"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("CSV 原文件不存在。")
        content = path.read_bytes()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("CSV 编码无法识别。") from exc
        reader = csv.reader(io.StringIO(text))
        try:
            headers = [str(value).strip() or f"字段{index + 1}" for index, value in enumerate(next(reader))]
        except StopIteration:
            headers = []
        preview_rows, total_rows, widest = [], 0, len(headers)
        header_positions = {header: index for index, header in enumerate(headers)}
        original_content_index = header_positions.get("original_content")
        content_index = header_positions.get("content")
        language_index = header_positions.get("language")
        translated_index = header_positions.get("translated_content")
        translation_total = translated_count = 0
        for row in reader:
            total_rows += 1
            widest = max(widest, len(row))
            text_value = row[original_content_index] if original_content_index is not None and original_content_index < len(row) else ""
            if not str(text_value).strip() and content_index is not None and content_index < len(row):
                text_value = row[content_index]
            language_value = row[language_index] if language_index is not None and language_index < len(row) else ""
            translated_value = row[translated_index].strip() if translated_index is not None and translated_index < len(row) else ""
            if self._review_needs_translation(text_value, language_value):
                translation_total += 1
                if translated_value and translated_value != "[翻译失败]":
                    translated_count += 1
            if len(preview_rows) < 200:
                preview_rows.append([str(value)[:20000] for value in row])
        if widest > len(headers):
            headers.extend(f"字段{index + 1}" for index in range(len(headers), widest))
        preview_rows = [row + [""] * (len(headers) - len(row)) for row in preview_rows]
        review_fields = {"review_id", "content", "score", "published_at"}
        document["csv_preview"] = {
            "headers": headers,
            "rows": preview_rows,
            "total_rows": total_rows,
            "truncated": total_rows > len(preview_rows),
            "kind": "reviews" if review_fields.issubset(set(headers)) else "table",
            "translation": {
                "total": translation_total,
                "translated": translated_count,
                "missing": max(0, translation_total - translated_count),
            },
        }
        return document

    def document_file(self, document_id):
        document = self.document(document_id)
        if document["kind"] != "upload":
            raise ValueError("只有原始资料可以下载原文件。")
        path = self.upload_path(document["project_id"], document["id"], document["name"]).resolve()
        root = (self.data / "uploads" / document["project_id"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("资料原文件不存在。")
        return path.read_bytes(), document["name"]

    @staticmethod
    def _source_key(source):
        return (
            str(source.get("source_id", "")),
            str(source.get("location", "")),
            # Product KB locators can be human-readable section labels rather
            # than numeric chunk positions.  Treat the locator as an opaque
            # identity value so project and global Hybrid results normalize in
            # the same citation snapshot.
            str(source.get("chunk", 1) or 1),
        )

    def normalize_sources(self, project_id, sources):
        """Flatten citations from embedded deliverables into one closed snapshot."""
        normalized, positions, nested_maps = [], {}, {}

        def add(source):
            candidate = dict(source)
            candidate.pop("citation", None)
            key = self._source_key(candidate)
            if key in positions:
                return positions[key]
            positions[key] = len(normalized)
            normalized.append(candidate)
            return positions[key]

        base_positions = []
        for source in sources:
            base_positions.append(add(source))
        for source, position in zip(sources, base_positions):
            if source.get("kind") not in {"accepted", "deliverable"}:
                continue
            job_rows = self.rows("SELECT sources FROM jobs WHERE id=? AND project_id=?", (source.get("source_id", ""),project_id))
            if not job_rows:
                continue
            try:
                nested_sources = json.loads(job_rows[0]["sources"])
            except (TypeError,ValueError):
                continue
            referenced = citation_ids(source.get("text", ""))
            mapping = {}
            for nested in nested_sources:
                old_citation = str(nested.get("citation", ""))
                if referenced and old_citation not in referenced:
                    continue
                nested_position = add(nested)
                mapping[old_citation] = nested_position
            if mapping:
                nested_maps[str(source.get("source_id", ""))] = mapping
        for index, source in enumerate(normalized,1):
            source["citation"] = f"S{index}"
        replacement_maps = {}
        for source, position in zip(sources, base_positions):
            mapping = nested_maps.get(str(source.get("source_id", "")))
            if not mapping:
                continue
            source_id = str(source.get("source_id", ""))
            replacements = replacement_maps.get(source_id)
            if replacements is None:
                replacements = {
                    old: normalized[target]["citation"]
                    for old, target in mapping.items()
                    if old
                }
                replacement_maps[source_id] = replacements
            normalized[position]["text"] = re.sub(
                r"\[(S[1-9][0-9]*)\]",
                lambda match: f"[{replacements.get(match.group(1),match.group(1))}]",
                normalized[position].get("text", ""),
            )
        return normalized, replacement_maps

    @staticmethod
    def citation_issues(output, sources):
        valid = {str(source.get("citation", "")) for source in sources}
        return sorted(citation_ids(output) - valid, key=lambda item:int(item[1:]))

    def asset_issues(self, project_id, output):
        """Return inline image IDs that do not belong to this project."""
        invalid = []
        for document_id in sorted(set(re.findall(r"asset://([a-f0-9]{16,64})", str(output or "")))):
            try:
                self.asset(project_id, document_id)
            except ValueError:
                invalid.append(document_id)
        return invalid

    def add_document(self, project_id, name, content, version_id="", relation="evidence", category="", subcategory=""):
        self.project(project_id)
        product_version = self.version_service.resolve(project_id, version_id)
        if not isinstance(name, str) or not name or len(name) > 180 or any(c in name for c in '/\\\x00'):
            raise ValueError("文件名无效。")
        if not content or len(content) > MAX_FILE:
            raise ValueError("每个文件须为 1 字节至 12 MB。")
        digest = hashlib.sha256(content).hexdigest()
        existing = self.rows("SELECT id,name FROM documents WHERE project_id=? AND sha=?", (project_id,digest))
        if existing:
            if product_version:
                self.version_service.link_document(project_id, existing[0]["id"], product_version["id"], relation)
            return {**existing[0],"duplicate":True}
        try:
            text = extract(name, content)
        except (ValueError, ImportError):
            raise
        except Exception as exc:
            raise ValueError("文档解析失败，请检查文件格式或另存为 TXT。") from exc
        document_id = uid()
        category = str(category or infer_material_category(name, "upload")).strip().lower()
        if category not in MATERIAL_CATEGORIES:
            raise ValueError("资料分类无效。")
        subcategory = str(subcategory or infer_image_subcategory(name, category)).strip().lower()
        if category == "images" and subcategory not in IMAGE_SUBCATEGORIES:
            raise ValueError("图片分类无效。")
        if category != "images":
            subcategory = ""
        directory = self.data / "uploads" / project_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (document_id + Path(name).suffix.lower())).write_bytes(content)
        with self.db() as db:
            db.execute(
                "INSERT INTO documents(id,project_id,name,text,sha,created,kind,category,subcategory) VALUES(?,?,?,?,?,?,?,?,?)",
                (document_id,project_id,name,text,digest,now(),"upload",category,subcategory),
            )
        if product_version:
            self.version_service.link_document(project_id, document_id, product_version["id"], relation)
        return {"id":document_id,"name":name,"characters":len(text),"duplicate":False}

    def set_document_category(self, project_id, document_id, category):
        self.project(project_id)
        category = str(category or "").strip().lower()
        if category not in MATERIAL_CATEGORIES:
            raise ValueError("资料分类无效。")
        document_id = str(document_id or "").strip()
        with self.db() as db:
            row = db.execute(
                "SELECT id FROM documents WHERE id=? AND project_id=?",
                (document_id, project_id),
            ).fetchone()
            if not row:
                raise ValueError("资料不存在。")
            current = db.execute("SELECT name,subcategory FROM documents WHERE id=?", (document_id,)).fetchone()
            subcategory = current["subcategory"] if category == "images" else ""
            if category == "images" and subcategory not in IMAGE_SUBCATEGORIES:
                subcategory = infer_image_subcategory(current["name"], category)
            db.execute("UPDATE documents SET category=?,subcategory=? WHERE id=?", (category, subcategory, document_id))
        return {"id": document_id, "category": category}

    def set_document_subcategory(self, project_id, document_id, subcategory):
        self.project(project_id)
        subcategory = str(subcategory or "").strip().lower()
        if subcategory not in IMAGE_SUBCATEGORIES:
            raise ValueError("图片分类无效。")
        document_id = str(document_id or "").strip()
        with self.db() as db:
            row = db.execute(
                "SELECT id,category FROM documents WHERE id=? AND project_id=?",
                (document_id, project_id),
            ).fetchone()
            if not row:
                raise ValueError("资料不存在。")
            if row["category"] != "images":
                raise ValueError("只有截图与图片资料可以设置图片分类。")
            db.execute("UPDATE documents SET subcategory=? WHERE id=?", (subcategory, document_id))
        return {"id": document_id, "subcategory": subcategory}

    def add_lanhu_snapshot(self, project_id, url, pages, version_id=""):
        """Persist a sanitized, read-only Lanhu MCP snapshot as project evidence."""
        self.project(project_id)
        url = str(url or "").strip()
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or parsed_url.hostname not in {"lanhuapp.com", "www.lanhuapp.com"}:
            raise ValueError("蓝湖链接必须是 https://lanhuapp.com/ 地址。")
        # Invite links can carry access tokens in query parameters.  Keep only
        # stable navigation identifiers in the evidence citation; the current
        # Lanhu MCP session remains the only place where access is authorized.
        safe_query_keys = {"docId", "tid", "pid", "id", "projectId", "teamId"}
        fragment_path, separator, fragment_query = parsed_url.fragment.partition("?")
        safe_base_query = [
            (key, value)
            for key, values in parse_qs(parsed_url.query, keep_blank_values=False).items()
            if key in safe_query_keys
            for value in values[:3]
        ]
        safe_fragment_query = [
            (key, value)
            for key, values in parse_qs(fragment_query, keep_blank_values=False).items()
            if key in safe_query_keys
            for value in values[:3]
        ]
        safe_fragment = fragment_path
        if separator and safe_fragment_query:
            safe_fragment = f"{fragment_path}?{urlencode(safe_fragment_query)}"
        safe_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", urlencode(safe_base_query), safe_fragment))
        if not isinstance(pages, list) or not pages or len(pages) > 120:
            raise ValueError("蓝湖快照至少包含 1 个页面且不超过 120 个页面。")
        blocks = [
            "# 蓝湖原型快照",
            "",
            f"- 来源链接：{safe_url}",
            f"- 读取时间：{now()}",
            "- 读取方式：Lanhu MCP 只读导入",
            "- 说明：本资料是原型证据快照，页面内容用于埋点设计；不代表实现已经完成。",
        ]
        for index, page in enumerate(pages, 1):
            if not isinstance(page, dict):
                raise ValueError("蓝湖页面格式无效。")
            page_name = str(page.get("name") or page.get("title") or f"未命名页面 {index}").strip()
            page_id = str(page.get("id") or page.get("page_id") or "").strip()
            page_text = str(page.get("text") or page.get("content") or "").replace("\x00", "").strip()
            states = page.get("states") or []
            if len(page_name) > 300 or len(page_id) > 300 or len(page_text) > 100000:
                raise ValueError("蓝湖页面名称、ID 或内容过长。")
            if not isinstance(states, list):
                states = [str(states)]
            state_text = "、".join(str(item).strip()[:120] for item in states if str(item).strip())
            blocks.extend([
                "",
                f"## 页面 {index}：{page_name}",
                f"- 页面 ID：{page_id or '未提供'}",
                f"- 状态：{state_text or '未提供'}",
                "",
                page_text or "页面没有可读取的文字内容。",
            ])
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.add_document(project_id, f"蓝湖原型快照-{stamp}.md", "\n".join(blocks).encode("utf-8"), version_id, "lanhu")

    def upload_path(self, project_id, document_id, name):
        return self.data / "uploads" / project_id / (document_id + Path(name).suffix.lower())

    def asset(self, project_id, document_id):
        """Resolve an image uploaded to the current project without path traversal."""
        self.project(project_id)
        rows = self.rows(
            "SELECT id,name FROM documents WHERE id=? AND project_id=? AND kind='upload'",
            (str(document_id), project_id),
        )
        if not rows or Path(rows[0]["name"]).suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError("图片不存在或不是当前项目的图片资料。")
        path = self.upload_path(project_id, rows[0]["id"], rows[0]["name"]).resolve()
        root = (self.data / "uploads" / project_id).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("图片文件不存在。")
        return path, rows[0]["name"]

    def delete_image(self, project_id, document_id):
        """Delete an unreferenced project image without breaking history."""
        with self.lock:
            self.project(project_id)
            document_id = str(document_id)
            rows = self.rows(
                "SELECT id,name FROM documents WHERE id=? AND project_id=? AND kind='upload'",
                (document_id, project_id),
            )
            if not rows or Path(rows[0]["name"]).suffix.lower() not in IMAGE_SUFFIXES:
                raise ValueError("图片不存在或不是当前项目的图片资料。")

            # Keep old versions, prepared task snapshots and source notes safe.
            # Deleting an image that an old version still references would make
            # version restore and re-export silently produce a broken document.
            needle = f"asset://{document_id}"
            source_id_pattern = re.compile(rf"(?:source_id|document_id)\"?\s*[:=]\s*\"?{re.escape(document_id)}")
            references = []
            for item in self.rows(
                "SELECT id,title,output,prompt,sources FROM jobs WHERE project_id=?",
                (project_id,),
            ):
                if needle in str(item.get("output") or "") or needle in str(item.get("prompt") or "") or source_id_pattern.search(str(item.get("sources") or "")):
                    references.append(f"任务 {item['title']}")
            for item in self.rows(
                "SELECT v.job_id,v.version,v.output FROM job_versions v JOIN jobs j ON j.id=v.job_id WHERE j.project_id=?",
                (project_id,),
            ):
                if needle in str(item.get("output") or ""):
                    references.append(f"历史版本 V{item['version']}")
            for item in self.rows(
                "SELECT id,name,text FROM documents WHERE project_id=? AND id<>?",
                (project_id, document_id),
            ):
                if needle in str(item.get("text") or ""):
                    references.append(f"资料 {item['name']}")
            if references:
                unique = list(dict.fromkeys(references))
                raise ValueError(
                    f"图片仍被 {len(unique)} 个正文、历史版本或任务引用，不能删除。请先移除引用后再删除。"
                )

            path = self.upload_path(project_id, document_id, rows[0]["name"]).resolve()
            root = (self.data / "uploads" / project_id).resolve()
            if not path.is_relative_to(root):
                raise ValueError("图片文件路径校验失败。")
            backup = path.read_bytes() if path.is_file() else None
            try:
                path.unlink(missing_ok=True)
                with self.db() as db:
                    db.execute("DELETE FROM version_documents WHERE document_id=?", (document_id,))
                    db.execute(
                        "DELETE FROM documents WHERE id=? AND project_id=? AND kind='upload'",
                        (document_id, project_id),
                    )
            except Exception:
                if backup is not None and not path.exists():
                    path.write_bytes(backup)
                raise
            return {"deleted": True, "id": document_id, "name": rows[0]["name"]}
