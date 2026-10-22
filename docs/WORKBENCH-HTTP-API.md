# 产品工作台 HTTP API 调用说明

版本：v1.2｜日期：2026-10-22｜对象：研究 Windows EXE 或源码运行版的技术同事

这是当前 `workbench` 本地服务已经实现的 HTTP 接口，默认地址为 `http://127.0.0.1:8765`。EXE 与源码运行版应使用同一组 HTTP 路由；启动方式和 EXE 自身参数以随包使用说明为准。本说明重点覆盖项目、文件导入、竞品评论和商店采集、Android 自动走查及外部收入资料，同时保留全部现有文档任务接口供查阅。

API 返回软件执行状态和已保存资料，不保证外部商店可访问、设备任务完成或业务结论成立。接口不是独立采集器 `packages/competitor-collector` 的 API；后者默认端口 8766、账号和 Cookie 规则另见其说明。

可执行的标准库客户端示例见 [api_client_example.py](../scripts/packaging/api_client_example.py)。默认只检查连接；显式传入 App 后才创建示例项目和发起采集，翻译关闭。

## 1. 连接与请求约定

### 1.1 本地地址和认证

- 服务默认只监听 `127.0.0.1`。`Host` 必须精确为 `127.0.0.1:<实际端口>` 或 `localhost:<实际端口>`，否则返回 403。修改端口后，相应 URL 和 Host 一起修改。
- GET 不要求 token；`GET /api/state` 返回本服务当前 `token`。
- **所有 POST** 必须在请求头带 `X-Workbench-Token: <state.token>`。token 在服务进程启动时随机生成，重启后需重新读取，不是长期 API Key。
- POST 的 `Origin` 可以省略；若提供，必须是 `http://127.0.0.1:<实际端口>` 或 `http://localhost:<实际端口>`，不能带末尾 `/` 或替换为其他域名。
- **本工作台没有 Cookie 登录／注册／会话认证，不用登录独立采集器账号。** 不返回 `Set-Cookie`，也不使用 Cookie 代替 POST token。这是单机请求校验，不是多用户权限系统。
- 请求体统一为 UTF-8 JSON，通常设 `Content-Type: application/json`。无额外字段的操作也发送 `{}`；空请求体会被拒绝。
- 只有 GET 和 POST 有实现。PUT、PATCH、DELETE、OPTIONS 没有实现，基础 HTTP handler 通常返回 501；删除／恢复等操作使用下文列出的 POST。
- 未提供跨站 CORS 配置、API 版本协商、Swagger/OpenAPI 描述、WebSocket 或 SSE 任务流。浏览器跨站客户端需另行设计接入；Python 等本机调用方可直接请求。

不要把 token 写死在脚本、日志或交接文档中。GET 响应可能包含项目资料和运行环境信息，不能把这个本地服务直接当成已授权的团队公网服务。

### 1.2 响应和错误

JSON 响应通常为 `application/json; charset=utf-8`，但**没有统一的 `{data: ...}` 包装**：创建项目返回项目对象，搜索返回带 `items` 的对象，`/api/search` 直接返回数组。文件接口返回原始字节，不能统一调用 `.json()`。

错误通常为：

```json
{"error": "可读的中文错误信息"}
```

| HTTP 状态 | 当前含义 |
|---|---|
| 200 | 普通读取／修改成功；部分异步任务启动也返回 200 |
| 201 | 项目、资料、版本、准备任务、会话或人工记录已创建 |
| 202 | 竞品采集、采集重试、Android 开始／续跑已受理，不代表执行完成 |
| 400 | 参数、资料、状态或业务前置条件不满足；许多“不存在”也返回 400 |
| 403 | Host、Origin 或 POST token 校验失败 |
| 404 | 未匹配到路由；不要把所有 400 都当成 404 |
| 413 | POST 请求体为空或超过 handler 限制 |
| 500 | 服务读取／执行失败；响应不会给出完整内部异常栈 |

普通 POST 原始 JSON 请求体上限为 **24 MiB**；`POST /api/projects/import` 为 **400 MiB**。这些是 HTTP 层限制，文件／项目包还要通过各自校验。多数业务冲突使用 400，并没有统一的 409／429 错误模型。响应设 `Cache-Control: no-store`。

### 1.3 共用标识

| 字段 | 含义 |
|---|---|
| `project_id` | 工作台项目 ID，不是商店 App ID |
| `version_id` | 工作台产品版本 ID；省略或 `""` 表示产品级工作 |
| `app_id` | Google Play 包名或 App Store 数字 ID |
| `package` | Android 实机目标包名，不接受商店链接 |
| `serial` | ADB 设备标识；多设备时必须明确选择 |
| `id` / `job_id` / `session_id` | 对应路由返回的任务或会话 ID；不要自行推算 |

`version_id` 是产品工作归类，`app_version` 是设备安装包版本，交付物的 `current_version` 是 Markdown 编辑历史；三者不能互换。清单接口一般没有分页／游标承诺，客户端不要自行追加 `page`、`cursor` 并假定有效。

## 2. Python 调用基础

以下示例使用 `requests`，可先安装 `python -m pip install requests`。示例片段按顺序放在同一 Python 脚本中运行；真实采集和设备操作仅在明确填写了相应 App／serial／范围后执行。

```python
import base64
import os
import time
from pathlib import Path
import requests

BASE = os.environ.get("WORKBENCH_URL", "http://127.0.0.1:8765").rstrip("/")
http = requests.Session()
http.trust_env = False  # 本地请求不走环境代理

def get_json(path, params=None, timeout=60):
    response = http.get(BASE + path, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()

TOKEN = get_json("/api/state")["token"]  # 不打印、不持久化

def post_json(path, body, timeout=90):
    response = http.post(
        BASE + path,
        headers={"X-Workbench-Token": TOKEN},
        json=body,
        timeout=timeout,
    )
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
    return response.json()

def wait_for(path, terminal, timeout=1800, interval=3):
    deadline = time.monotonic() + timeout
    while True:
        record = get_json(path)
        if record["status"] in terminal:
            return record
        if time.monotonic() >= deadline:
            raise TimeoutError("轮询到期；先检查已有任务，不重复提交采集或设备操作")
        time.sleep(interval)

def download(path, destination, params=None, timeout=120):
    response = http.get(BASE + path, params=params, timeout=timeout)
    response.raise_for_status()
    Path(destination).write_bytes(response.content)
```

若服务重启导致 403，重新读取 token 后再检查任务状态。网络超时不证明任务未受理，先读取已有记录，不盲目重发 POST。

## 3. 项目和产品版本

### 3.1 创建项目

`POST /api/projects`，返回 201 和项目对象。

```python
project = post_json("/api/projects", {
    "name": "接口研究项目",
    "brief": "只采集明确选择的竞品资料，不生成产品分析。",
    "workflow_mode": "fast",
    "platform": "Android-first",
})
project_id = project["id"]
version_id = ""  # 不创建产品版本也可采集
```

| 请求字段 | 规则 |
|---|---|
| `name` | 必填，去首尾空白后 1–100 字 |
| `brief` | 可选，最多 12000 字 |
| `workflow_mode` | `fast`（默认）或 `full` |
| `platform` | 可选文本，最多 80 字；前端常用 `Android-first`、`iOS-first`、`双端` |
| `team` | 可选，最多 1000 字 |
| `timebox` | 可选，最多 80 字 |

响应包含 `id,name,brief,created,workflow_mode,platform,team,timebox`。后续读取 `GET /api/state?project=<project_id>` 可获取项目、资料、产品版本、任务和商店采集清单。

### 3.2 可选产品版本

```python
version = post_json("/api/product-versions", {
    "project_id": project_id,
    "name": "研究批次 1",
    "version_type": "feature",
    "status": "planning",
    "goal": "保存本批采集资料",
})
version_id = version["id"]
```

`name` 必填且最多 80 字，同项目内不能重名。`version_type` 为 `new-product/feature/experience/monetization/bugfix`；`status` 为 `planning/developing/testing/released/reviewed/archived`；`goal` 最多 2000 字，`target_date` 为最多 40 字的文本。修改使用 `POST /api/product-versions/{version_id}`，请求体仍需 `project_id`，省略其他字段保留原值。

## 4. 文件导入和原始资料读取

### 4.1 单文件 JSON Base64 上传

`POST /api/documents`，返回 201。**不是 multipart/form-data**，没有文件路径扫描、任意 URL 下载或文件夹上传 API；客户端读取文件并传 Base64。

```python
source = Path(os.environ["SOURCE_FILE"])  # 你明确选择的本机资料
document = post_json("/api/documents", {
    "project_id": project_id,
    "version_id": version_id,
    "name": source.name,
    "content": base64.b64encode(source.read_bytes()).decode("ascii"),
    "category": "research",
})
document_id = document["id"]
preview = get_json(f"/api/documents/{document_id}")
download(f"/api/documents/{document_id}/download", "downloaded-source" + source.suffix)
```

支持 MD、TXT、CSV、JSON、文本 PDF、DOCX、PNG、JPG、JPEG、WEBP。每个原文件 **1 字节–12 MiB**；文件名最多 180 字，不含路径分隔符。PDF 加密或没有可读取文字时会拒绝，需先解密／OCR。当前导入不支持 XLSX、PPTX、XLS、任意二进制附件。

`category` 可省略自动推断，枚举：`competitor/reviews/images/policy/technical/research/deliverable/other`。图片可附 `subcategory=competitor/prototype/data/policy/feedback/reference/other`；其他类别不保留图片子分类。

上传时可附 `competitor_id`，将原件同时关联到当前项目的未归档竞品；`material_type` 可指定下节的竞品资料类型。未指定竞品的资料保留为项目公共资料。`category/subcategory` 是文件分类，`material_type` 是该文件与竞品关联的类型，两者不互相替代。

新文件响应形如 `{"id":"...","name":"...","characters":123,"duplicate":false}`；同项目同 SHA-256 文件返回已有 `id,name,duplicate:true`，不保证有 `characters`。指定新 `version_id` 时会关联已有资料到该版本。前端“一批最多 30 份”是客户端暂存规则，HTTP 接口本身一次只收一个文件。

重复上传时若指定另一个 `competitor_id`，会为已有原件增加归属关联，不复制文件，也不会移除原有竞品关联。

### 4.2 获取、分类和翻译

- `GET /api/documents/{id}` 返回解析正文 `text` 和元数据；CSV 额外含 `csv_preview`，最多展示前 200 行，并包含 `total_rows/truncated/headers/rows/kind/translation`。评论识别字段包括 `review_id,content,score,published_at`。
- `GET /api/documents/{id}/download` 返回上传原件；当前原件下载要求 `kind=upload`，生成文档走 jobs 下载接口。
- `GET /api/assets/{project_id}/{document_id}` 返回项目图片，不能传任意磁盘路径。
- `POST /api/documents/{id}/category`：`{"project_id":"...","category":"reviews"}`。
- `POST /api/documents/{id}/subcategory`：`{"project_id":"...","subcategory":"reference"}`。
- `POST /api/documents/{id}/translate`：`{}`，同步补充已导入评论 CSV 的中文列，一次最多处理 500 条。使用已配置的采集／翻译环境，可能耗时数分钟；可单独把请求 timeout 设为 1000 秒。响应含新增／已有译文计数，之后重新读取 document 查看，不使用 scrape 轮询。
- `POST /api/documents/{id}/delete` 只删除**未被正文、历史版本或任务引用的上传图片**，请求体 `{"project_id":"..."}`；不是通用文档删除接口。

### 4.3 竞品档案、公共资料与明确分析输入

界面使用一个“项目资料”页：竞品资料按档案整理，未归属竞品的原始资料放在项目公共资料中。档案只增加资料关系，不搬动原件；同一份已入库原件可关联多个竞品。竞品身份由同一项目内的 `platform + app_id` 确定，不按文件名猜测归属。

| 接口 | 输入及行为 | 成功响应 |
|---|---|---|
| `GET /api/competitors` | query 必填 `project_id`，可选 `version_id` | 200 `{"competitors":[...]}`，含归档档案、资料类型计数、待确认批次数等 |
| `GET /api/competitors/{id}` | 同上；id 为档案 ID，不是商店应用 ID | 200 档案详情，含 `documents/scrapes/captures` |
| `POST /api/competitors` | `project_id,platform,app_id,title?,role?,note?` | 201 新建或返回已有档案；再次提交不覆盖既有自定义备注、用途或名称（仅默认应用 ID 名称可补为真实名称） |
| `POST /api/competitors/{id}/update` | `project_id`，可选 `title,role,note,archived` | 200 档案对象；省略字段保留原值 |
| `POST /api/competitors/{id}/documents` | `project_id,document_ids,material_type?` | 200 `{"competitor_id":"...","document_ids":[...]}` |
| `POST /api/competitors/{id}/unlink` | `project_id,document_ids` | 200 解除关联结果，`files_deleted:false`；不删除原件 |
| `POST /api/competitors/inputs` | `project_id,competitor_ids,document_ids,version_id?` | 200 核对后的明确输入快照；不创建或运行分析任务 |

`platform` 为 `google_play/app_store`；Google Play 用包名，App Store 用数字 ID。商店地址由身份生成，不接受任意来源 URL。`title` 最多 300 字，更新时不能为空；`note` 最多 5000 字；`role` 为 `""/primary/feature/monetization`（未指定用途／主对标／功能参考／变现参考），`archived` 必须为布尔值。归档不删除文件；采集和新的明确输入不能选择已归档档案，恢复使用 `archived:false`。

`material_type` 为 `store_info/reviews/store_screenshot/device_screenshot/module_flow/note/revenue/attachment`；省略时按当前资料元数据推断。关联只接受同项目 `kind=upload` 的已入库原件，不接受其他项目资料或生成草稿。重复关联可更新该竞品下的资料类型；解除关联仅影响指定竞品，不清除其他关联。

列表和详情中，不传 `version_id` 查看项目全部范围；传具体版本 ID 查看“项目公共范围＋该版本”，传空值 `version_id=` 只查看产品级公共范围。资料关联接口不改文件的版本归属；应在上传时正确填写版本。

明确输入接口的 `competitor_ids/document_ids` 均为 ID 数组，返回 `sources`（文件 ID、名称、SHA-256、创建时间及选中竞品归属）、`captured_at` 和 `source_selection_mode:"explicit"`。所选资料必须已确认入库，并处于同项目及当前版本范围；竞品资料必须至少属于一个同时勾选的未归档竞品。项目公共资料可以配合 `competitor_ids:[]` 单独使用。只勾选竞品不会自动把它的所有文件加入输入，待确认采集批次也不会成为可引用原件。

核对输入后，需另行调用 `/api/prepare` 并显式传 `source_selection_mode:"explicit"`、同一组 `document_ids/competitor_ids`，才会准备任务包；准备任务最多明确选择 1–12 份。保存输入快照不等于生成或确认分析结论，详见第 10 节。

### 4.4 本机 Codex 连接与首次登录

这一组接口是本机工作台设置，不是项目数据。状态检查、浏览器登录、实际模型测试严格分开；打开页面或 `GET` 不启动 CLI，不自动发送模型请求。

| 接口 | 请求 | 返回 |
|---|---|---|
| `GET /api/integrations/codex` | 无 | 200 安全状态快照与有限发现的 CLI 候选 |
| `POST /api/integrations/codex` | `{"binary_path":"本机绝对路径/codex.exe"}`；空字符串恢复自动 | 200 新快照；只保存路径，不保存认证 |
| `POST /api/integrations/codex/check` | `{}` | 202；异步执行 CLI 版本、`login status`，不推理 |
| `POST /api/integrations/codex/login` | `{"confirmed":true}` | 202；官方 CLI 打开浏览器，由本人授权 |
| `POST /api/integrations/codex/test` | `{"confirmed":true}` | 202；固定极小模型请求，需要使用者确认额度 |
| `POST /api/integrations/codex/cancel` | `{"operation_id":"当前操作ID"}` | 200；仅取消该次连接操作，不登出账号 |

快照含 `available,command,binary_path,source,candidates,version,model,config_path,env_managed,message`，以及 `auth,test,operation`：

- `auth.status` 为 `unknown/logged_in/not_logged_in/error`，仅返回认证方式枚举与安全中文摘要，不返回 CLI 原始文本。
- `test.status` 为 `not_tested/passed/failed`。登录成功不自动变成生成测试通过。
- `operation` 为 `null` 或含 `id,kind,status,started_at,updated_at,message` 的对象。`kind` 为 `check/login/test`；`status` 为 `running/succeeded/failed/cancelled`。轮询同一个只读 GET，不能靠反复 POST 查询进度。
- 登录或测试必须是 JSON 布尔值 `confirmed: true`，缺少确认或写成字符串都拒绝。路径保存拒绝命令参数、脚本、网络共享及非本机原生 CLI。
- 本机环境变量强制指定 CLI 时，不能在页面覆盖；保存路径、PATH/npm 与有限桌面目录发现用于其余情况。未找到不静默安装软件。
- 改路径、登录和测试与正在执行的文档生成、设备走查互斥；取消后进程尚未回收时仍不放行新操作。
- 连接测试在临时空目录执行固定 Prompt，不携带任何项目背景、评论或截图，不启用用户工具、MCP、搜索或 shell。它会使用当前本机模型连接及账号额度。
- 登录原文、认证文件和临时测试结果不进入项目、数据库或项目导出包。只有非秘密 CLI 路径保存在本机 preferences。

## 5. 商店候选搜索和详情

### 5.1 搜索候选

`POST /api/competitors/search` 是同步查询，返回 200，不创建采集任务、不调用模型、不自动选择候选。

```python
found = post_json("/api/competitors/search", {
    "project_id": project_id,
    "version_id": version_id,
    "platform": "google_play",
    "query": os.environ.get("STORE_QUERY", "document reader"),
    "country": "us",
    "lang": "en",
    "limit": 12,
    "refresh": False,
}, timeout=90)
for candidate in found["items"]:
    print(candidate.get("title"), candidate.get("app_id"))
```

| 请求字段 | 规则 |
|---|---|
| `project_id` | 必填；`version_id` 可选但必须属于该项目 |
| `platform` | `google_play`（默认）或 `app_store` |
| `query` | 必填，1–160 字，不含控制字符 |
| `country` | 两位小写国家码，默认 `us`；另支持 `global` |
| `lang` | 默认 `en`，支持 `zh-cn` 等格式；搜索语言不是用户国籍 |
| `limit` | 1–30 的整数，默认 12；前端默认 12 不等于 API 上限 |
| `refresh` | 可选布尔值，跳过对应缓存重新查 |

`global` 只合并 `us,gb,de,jp,in,id,br,sa` 八个市场，按平台＋App ID 去重，不是全球全量。响应有 `items,cached,collected_at,warnings,scope,countries,attempted_countries,successful_countries,failed_countries`；每项保留可用的具体 `lookup_country` 与 `observed_countries`。失败市场不自动用美国替代。

### 5.2 单个详情

`POST /api/competitors/detail`：必填 `project_id,app_id`，可选 `platform`（默认 google_play）、`version_id,country,lang,refresh`。Google Play 使用包名，App Store 使用数字 ID。

```python
detail = post_json("/api/competitors/detail", {
    "project_id": project_id,
    "platform": "google_play",
    "app_id": os.environ["STORE_APP_ID"],  # 你已经选定的候选
    "country": "us",
    "lang": "en",
}, timeout=90)
```

若传 `country=global`，还必须传具体 `lookup_country`；不能把 global 作为一个详情商店。详情读取不会自动入库。响应包含读取结果及 `lookup_country`，字段以商店实际返回为准；App Store 没返回 Subtitle 时不会猜补。

## 6. 竞品商店和评论采集

### 6.1 检查采集环境；源码版按需配置 legacy

读取配置可通过 `GET /api/state` 的 `integrations.review_scraper`。EXE 在没有显式配置外部采集目录时，使用随包 `packages/competitor-collector` 原生引擎，返回 `backend="builtin"`；不要求同事另装旧桌面采集器。此模式评论翻译使用 Google 网页翻译，仍需相应网络可用。

源码版默认使用旧桌面采集环境，或 EXE 已显式选择外部目录时，返回 `backend="legacy"`。仅在需要这种模式时保存以下配置：

```python
settings = post_json("/api/integrations/review-scraper", {
    "root": os.environ["REVIEW_SCRAPER_ROOT"],
    "enabled": True,
    # "python": os.environ["REVIEW_SCRAPER_PYTHON"],  # 可选存在的 Python 路径
})
```

legacy 的 `root` 必须包含 `app/scrapers.py`。优先使用保存的 Python，其次该目录 `.venv/Scripts/python.exe` 或 `.venv/bin/python`，再考虑当前 Python。该模式翻译读取旧工具已配置的 DeepSeek，失败可能回退 Google；不通过本 HTTP API 提交或返回密钥。配置检查不是完整依赖或联网验证。独立采集器自身网页默认行为与翻译选项另见其 README，不能把其 8766 接口套用到本工作台。

### 6.2 推荐的商店与评论组合采集

`POST /api/competitors/collect` 返回 202，格式：

```json
{
  "count": 1,
  "items": [{"id": "采集任务ID", "status": "queued"}],
  "countries": ["us"],
  "requested_countries": ["us"],
  "total_review_fetch_limit": 20,
  "warnings": []
}
```

异步线程可能已推进到 running，不能要求响应一定停在 queued。

```python
batch = post_json("/api/competitors/collect", {
    "project_id": project_id,
    "version_id": version_id,
    "entries": [os.environ["STORE_APP_URL"]],  # 明确选择的官方链接或应用 ID
    "countries": ["us"],
    "count_per_country": 20,
    "sort": "newest",
    "translate": False,
})
scrape_id = batch["items"][0]["id"]
record = wait_for(f"/api/reviews/scrape/{scrape_id}",
                  {"ready", "completed", "empty", "failed", "cancelled"})
print(record["status"], record.get("review_count"), record.get("warnings", []))
```

| 请求字段 | 规则 |
|---|---|
| `entries` | 官方商店链接或应用 ID，数组或按行分隔文本；平台由输入解析。可与 `competitor_ids` 合用，或仅提供后者；合并去重后必须为 1–8 个 App |
| `competitor_ids` | 可选，当前项目未归档竞品档案 ID 数组，最多 8 个；读取其固定商店身份，不重新搜索或自动选品 |
| `countries` | 必填，最多 20 个具体国家码；组合采集另支持 `global` 展开为八市场 |
| `count_per_country` | 默认 100，范围 1–500；组合采集对 App Store 实际压到最多 100／市场 |
| `sort` | `newest`（默认）或 `relevant` |
| `date_from,date_to` | 可选 `YYYY-MM-DD`，开始不得晚于结束 |
| `translate` | 布尔值；**此接口默认 true**；不需要翻译时显式 false |
| `collect_listing,collect_reviews,collect_screenshots` | 布尔值，均默认 true；分别控制商店信息、评论、商店宣传图。每个竞品至少一项为 true；截图不包含 App 内实机页面 |
| `collection_options` | 可选对象，按竞品档案 ID（无已有档案时按 `app_id`）覆盖上述三项采集勾选；例如 `{"档案ID":{"collect_reviews":false}}`。`translate` 仍使用本次请求的顶层开关，且不采评论时不会翻译 |
| `version_id` | 可选，决定采集记录与确认资料归属 |
| `selections` | 可选选用信息；提供时须覆盖每个待采集 App，见下 |

商店图采集需要读取商店元数据，但未勾选商店信息时不会把该文档作为入库成果；未勾选评论时也不会导入评论 CSV。组合采集会建立或复用竞品档案，结果仍先待确认，确认后才将本次勾选的原件关联入档案。采集勾选与分析输入勾选相互独立，不会因完成采集而自动发起分析。

可共用的评论筛选：

| 字段 | 规则 |
|---|---|
| `ratings` | 1–5 星数组，或逗号／空白分隔文本 |
| `include_keywords,exclude_keywords` | 数组或逗号／换行分隔文本；每类最多 20 个，每词最多 80 字符 |
| `reply_filter` | `any`（默认）、`replied`、`unreplied` |
| `version_filter` | 可选 App 版本文本，最多 100 字符 |
| `min_thumbs_up` | 默认 0，范围 0–1000000 |

`selections` 元素为 `platform,app_id,role`，其中 role 为 `primary/feature/monetization`；可附 `note,title,query,search_country,lookup_country,observed_countries`。仅采指定链接时可省略整个 selections；若提供不能漏项或混入其他 App。

采集包含商店信息、截图和评论，没有独立 `collect_listing=false` 开关；只要评论用下节旧接口。评论数是筛选前抓取上限，筛选后可能减少，不保证取满。每款翻译最多前 500 条，其余保留原文。同一个项目已有 queued／running 商店或评论采集时，新请求被拒绝。

### 6.3 预览、确认、下载、取消和重试

`GET /api/reviews/scrape/{scrape_id}` 返回任务对象，主要字段：

- 身份和状态：`id,project_id,version_id,platform,app_id,status,created,updated,error`。
- 统计与资料：`review_count,warning_count,translated_count,screenshot_count,document_ids,result_doc_id,listing_document_id,review_document_id`。
- 预览：`listing,review_samples,screenshot_preview_urls,warnings,filter_stats`；评论样本最多 5 条。
- `request` 当前是 **JSON 字符串**，需 `json.loads(record["request"])`，不是对象。不要把原始 request 不加筛选地发布到外部。

组合采集状态：`queued → running → ready → completed`。`ready` 为待确认，尚未进入项目资料；`completed` 是确认后已入库。失败终态可为 `empty/failed/cancelled`；`error` 在 ready/completed 时也可能承载部分失败提示，不应只靠它是否为空判成功。

预览通过后由调用方明确确认：

```python
if record["status"] == "ready":
    # 仅在你已经检查 listing、review_samples、warnings 后执行这一行。
    confirmed = post_json(f"/api/reviews/scrape/{scrape_id}/confirm", {})
    for doc_id in confirmed["document_ids"]:
        meta = get_json(f"/api/documents/{doc_id}")
        download(f"/api/documents/{doc_id}/download", meta["name"])
```

`confirm` 只允许 ready，重复确认会报 400。保存商店 Markdown、评论 CSV 和图片为项目资料，不自动开始 F1 或分析任务。批量确认是前端逐项调用，没有独立 batch-confirm API。

- 取消：`POST /api/reviews/scrape/{id}/cancel`，仅 queued／running，返回 200 任务对象。
- 重试：`POST /api/reviews/scrape/{id}/retry`，仅 failed／empty／cancelled，返回 202；**会创建新 ID**，旧记录保留，按新 ID 轮询。
- 没有独立的商店采集 ZIP 下载路由；确认后下载每份 document，或导出完整项目包。

### 6.4 旧的单 App 纯评论接口

`POST /api/reviews/scrape` 仍存在，参数为 `project_id,platform,app_id,countries,count_per_country,sort,date_from,date_to,version_id,translate` 及共用筛选字段，返回 202 的**单个任务对象**。

与组合采集的重要区别：

- 不传 `entries`，用单个 `platform + app_id`；countries 只接受具体两位国家码，不展开 global，另兼容 `markets` 别名。
- `translate` 默认 **false**，不是组合接口默认值。
- **成功后直接将评论 CSV 写入项目资料并变为 completed，不经过 ready／confirm。** 需要“先预览再入库”的统一流程时使用组合采集。
- `count_per_country` 校验 1–500，但 App Store 的外部后端／分页本身可能更低，不能据参数承诺条数。

## 7. Android 自动实机走查

这里公开的是**会话编排 API**。HTTP 不开放任意 ADB shell、裸坐标点击或通用 `observe/act_observe` 路由；单步工具仅由受限 MCP 暴露给本轮模型。独立采集器的人工点控 API 不属于此服务。

### 7.1 配置和只读设备检测

```python
settings = get_json("/api/android-capture/settings")
if not settings["adb_available"]:
    settings = post_json("/api/android-capture/settings", {
        "adb_path": os.environ["ADB_PATH"],
    })
devices = get_json("/api/android-capture/devices")["devices"]
print(devices)
```

settings 返回 `adb_path,adb_available,codex_available,skill_available,ready,message`。Windows 路径必须是存在的 `.exe`，不能附命令参数。也可由本机 `WORKBENCH_ADB_PATH` 配置。设备响应为 `{"devices":[{"serial":"...","state":"device","model":"..."}],"message":"..."}`，还可能出现 offline／unauthorized／recovery／sideload。只有 state=device 可开始；接口不会代替手机授权 USB 调试。

### 7.2 创建、开始和轮询

```python
capture = post_json("/api/android-capture/sessions", {
    "project_id": project_id,
    "version_id": version_id,
    "package": os.environ["ANDROID_PACKAGE"],
    "serial": os.environ["ANDROID_SERIAL"],
    "title": "指定范围走查",
    "scope": os.environ["ANDROID_CAPTURE_SCOPE"],
})
capture_id = capture["id"]
post_json(f"/api/android-capture/sessions/{capture_id}/start", {}, timeout=90)
result = wait_for(f"/api/android-capture/sessions/{capture_id}",
                  {"ready", "paused", "blocked", "failed", "cancelled", "interrupted", "confirmed"},
                  timeout=900)
print(result["status"], result.get("summary"), result.get("pause_reason"))
```

创建返回 201 和 prepared 会话。`project_id,package,scope` 必填；`scope` 2–5000 字，`title` 默认包名且最多 120 字；`serial` 可仅在恰好一台在线设备时省略。创建时通过 ADB 只读检查已安装 App 和版本，**不会安装 App，也不会自动开始模型走查**。

开始返回 202，模型需要时可启动已确认包名。当前服务固定每轮 60 次动作／600 秒；该 HTTP API 没有开放 model、max_actions、budget_seconds、adb命令等请求覆盖项。模型读取本机当前配置与已登录账号，需支持图像和工具调用，产生正常模型用量。

会话主要字段：`id,project_id,version_id,package,serial,title,scope,app_version,status,created,updated,summary,error,pause_reason,document_ids`；`app_version` 是 `{name,code}`。详情另有 `modules,progress,observations,composites,composite_count`。`progress` 是供 UI 阅读的近期进度，`observations` 是最多最近 100 条截图清单，`composites` 是已收尾结果引用的拼图清单；原始完整证据可通过 ZIP 获取。

### 7.3 状态、暂停、确认和导出

| 状态／操作 | 规则 |
|---|---|
| `prepared → queued → running` | 创建与开始分开；queued／running 可取消 |
| `ready` | 模型完成且交付检查通过，待人工确认入资料 |
| `paused/blocked` | 需要手机处理或仍有未覆盖处，保留部分证据 |
| `failed/cancelled/interrupted` | 执行异常、停止、服务重启中断；不自动重新操作设备 |
| `POST .../{id}/resume` | paused／blocked／failed／cancelled／interrupted／ready 可续跑；新一轮预算，旧地图／编号保留；App 版本变化则拒绝混入 |
| `POST .../{id}/cancel` | 写取消标记并停止子进程；尚未完全退出时不能同设备重开 |
| `POST .../{id}/confirm` | ready／paused／blocked 且已有实际截图可确认，包括显式接受部分证据；confirmed 再确认会返回既有结果 |
| `confirmed` | 实机图、流程图和走查索引已进入创建会话时的项目／版本；不代表全 App 完整覆盖或 QA 通过 |

登录、权限、系统选择器、购买／试用、设备断开等需要接管时，先在手机处理，再调用 resume；不能让 HTTP 调用方代替模型重放旧坐标。相同 serial 的活任务／进程不能并行。

```python
# 预览单张实机图或模块图：path 必须来自响应，而非任意磁盘路径。
for image in result.get("composites", []):
    download(f"/api/android-capture/sessions/{capture_id}/file",
             Path(image["path"]).name, params={"path": image["path"]})

# 下载会话原始证据、地图与模块图；可在未确认入库前下载。
download(f"/api/android-capture/sessions/{capture_id}/export", "android-capture.zip")

# 仅在已经接受本轮覆盖和缺口后调用；不会因下载而自动入库。
# confirmed_capture = post_json(f"/api/android-capture/sessions/{capture_id}/confirm", {})
```

`/file?path=...` 只允许会话内 `observations/`、`flow_export/` 及规定的地图／耗时文件，不公开 request.json 或模型执行日志。XML、Markdown、JSONL 为文本，图片为图片响应。当前会话 ZIP 与项目导出会过滤本机执行配置、连接字段、凭据和模型尝试日志。不要把 API 的 ready 或 PNG 文件校验当成真实商业效果、支付或 SDK 测试结论。

## 8. 外部收入资料的人工录入

`POST /api/competitors/revenue` 返回 201：`{"document":{...},"record":{...,"manual":true,"verified":false}}`。该接口只是**保存你已经核对的数据**，不会访问来源链接，不调用 Sensor Tower／AppMagic／AppTweak 收费 API，不估算广告收入。

必填字段：`project_id,platform,app_id,title,provider,value_display,currency,period_start,period_end,country,revenue_type,basis,data_nature,observed_on,source_url,acknowledged`；`version_id,note` 可选。

| 字段 | 规则 |
|---|---|
| `platform` | `google_play/app_store`；App Store ID 为数字 |
| `provider` | 数据来源名称，最多 80 字 |
| `value_display` | 金额或区间文本，最多 100 字；不是自动计算字段 |
| `currency` | 三位币种代码，保存为大写 |
| `period_start/period_end/observed_on` | 有效 `YYYY-MM-DD`；开始 ≤ 结束 ≤ 查看日期；查看日期不晚于北京时间当前日期 |
| `country` | 两位国家码或来源明确标示的 `global` |
| `revenue_type` | `iap/ads/combined/paid_download/unknown`；combined 需来源明确包括广告 |
| `basis` | `consumer_spend/publisher_net/unknown` |
| `data_nature` | `estimate/disclosed/unknown` |
| `source_url` | 公开 HTTPS 来源，不含账号密码、token／密钥参数 |
| `acknowledged` | 必须为 JSON 布尔值 true，确认这是人工记录而非系统核验 |

```python
# 这些值都从你实际核对的资料填写；示例不提供虚构收入金额。
revenue = post_json("/api/competitors/revenue", {
    "project_id": project_id,
    "version_id": version_id,
    "platform": "google_play",
    "app_id": os.environ["STORE_APP_ID"],
    "title": os.environ["STORE_APP_TITLE"],
    "provider": os.environ["REVENUE_PROVIDER"],
    "value_display": os.environ["REVENUE_VALUE"],
    "currency": os.environ["REVENUE_CURRENCY"],
    "period_start": os.environ["REVENUE_PERIOD_START"],
    "period_end": os.environ["REVENUE_PERIOD_END"],
    "observed_on": os.environ["REVENUE_OBSERVED_ON"],
    "country": os.environ["REVENUE_COUNTRY"],
    "revenue_type": os.environ["REVENUE_TYPE"],
    "basis": os.environ["REVENUE_BASIS"],
    "data_nature": os.environ["REVENUE_DATA_NATURE"],
    "source_url": os.environ["REVENUE_SOURCE_URL"],
    "acknowledged": True,
})
records = get_json("/api/competitors/revenue", {
    "project_id": project_id, "version_id": version_id,
    "platform": "google_play", "app_id": os.environ["STORE_APP_ID"],
})
assert records["automatic_provider_connected"] is False
```

GET 响应为 `items,truncated,automatic_provider_connected`，按项目／产品版本／平台／App ID 查询；产品级查询不自动混入其他版本。扫描最近最多 200 份该范围人工资料，`truncated=true` 提示可能未覆盖更早记录。留存、画像、投放报表等其他外部数据目前用第 4 节文件上传，没有自动指标计算或经营平台同步 API。

## 9. 项目包导入导出

```python
download(f"/api/projects/{project_id}/export", "workbench-project.zip", timeout=180)

# 明确选择一个已有工作台项目包后导入；创建新项目，不覆盖原项目。
# package = Path(os.environ["WORKBENCH_PROJECT_ZIP"])
# imported = post_json("/api/projects/import", {
#     "content": base64.b64encode(package.read_bytes()).decode("ascii")
# }, timeout=180)
```

项目 ZIP 包含背景、产品版本、上传资料、任务／交付物／版本／批注／评审、商店采集、Android 证据记录，以及竞品档案和资料归属关系。格式标识 `workbench-project-v1`，内部数据结构版本 3，导入兼容旧结构版本 1、2。服务校验 ZIP 路径、成员大小、总大小和 SHA-256；原 ZIP 及解压总量均限制在 200 MiB。

导入返回新项目对象，资料／产品版本／任务／会话 ID 重新映射。运行中任务变为中断，不自动继续模型或设备操作。项目包不带 Codex 认证、Lanhu 凭据、本机集成路径、向量索引或浏览器缓存。导出／导入不是程序升级、完整电脑备份或 EXE 分发 API。

## 10. 其他已有模型文档接口

采集使用者可以跳过本节。项目里仍保留分析／需求等能力，但采集完成不自动触发它们。

1. `POST /api/prepare`：`project_id,task,instruction?,document_ids?,version_id?,source_selection_mode?,competitor_ids?`，返回 201 的 prepared 任务。task 使用 `/api/state` 中 pack/task 的 `key`；显式参考最多 12 份。
2. `POST /api/jobs/{id}/start`：`{}`，返回 200；后台 `queued → running → completed`，轮询 `GET /api/jobs/{id}`。一次只允许一个文档生成任务。
3. completed 先是待评审草稿；`POST .../review`，`decision=accepted/changes_requested`，可附 note。accepted 需无当前未解决批注、无无效来源／图片引用、无阻断质量错误。
4. `POST .../edit` 保存正文新版本，编辑／恢复会撤销本稿确认；`revise/revise-comments` 只准备新的修订任务，还要显式 start。
5. `GET .../download` 下载当前 Markdown；`GET .../export?format=docx|pdf|xlsx|csv&version=<可选文档版本号>` 渲染指定版本。XLSX／CSV 是从文档表格导出，不是原始项目数据库全量导出。
6. F1 五章确认后 `POST /api/assemble` 合并，body 含 `project_id`，可选 `task=fast/new-product-analysis,version_id`；此步骤不调用模型改写正文，完整 F1 仍待确认。

`source_selection_mode` 默认为 `auto`，保留既有检索选源行为。设置 `explicit` 时，必须提供 1–12 份 `document_ids`，并按第 4.3 节同时传所属 `competitor_ids`（仅公共资料可为空数组）；服务不会再检索补入其他竞品资料，也不会因勾选竞品而自动选取全部原件。任务必需的已确认前章仍作为独立上游交接保留；模板、项目背景和补充要求也仍参与任务准备。`/api/competitors/inputs` 的核对结果不会自动保存在下一次 prepare 请求中，调用方须再次传入这些字段。

prepared 仅表示任务包已准备好，仍须显式 start 才运行模型；执行记录保存本次输入方式、文件与竞品 ID。后续改变资料勾选不会自动改写已准备任务的来源快照，需要重新准备任务。

文档任务取消／失败／重启中断后可 `POST .../restore` 回 prepared；不能直接重复 start。上游变更只提示复核，不自动重写下游。工作台确认与公司业务评审、外部原型实际修改、设备验收结果是不同状态。

## 11. 全量路由参考

下列是当前公开的规范路径。未列出服务类内部函数并不代表存在同名 HTTP API。所有 POST 均适用第 1 节请求校验。

### 11.1 GET

| 路径 | 输入／用途 | 成功响应 |
|---|---|---|
| `/api/state` | 可选 query `project`；启动／项目总状态 | 200 状态对象，含 token |
| `/api/search` | query `project,q`；q 最多采用前 4000 字 | 200 来源片段数组 |
| `/api/assets/{project_id}/{document_id}` | 项目图片 | 200 PNG／JPEG／WEBP |
| `/api/documents/{id}` | 资料正文／CSV 预览 | 200 document |
| `/api/documents/{id}/download` | 上传原件下载 | 200 原文件字节 |
| `/api/projects/{id}/export` | 完整项目包 | 200 ZIP 附件 |
| `/api/reviews/scrape/{id}` | 评论／商店异步任务详情和预览 | 200 scrape |
| `/api/competitors` | query `project_id,version_id?`；竞品档案及计数 | 200 `{competitors:[...]}` |
| `/api/competitors/{id}` | query `project_id,version_id?`；档案及关联资料、采集、实机记录 | 200 档案详情 |
| `/api/competitors/revenue` | query `project_id,platform,app_id,version_id?` | 200 人工记录列表 |
| `/api/android-capture/settings` | 本机能力检测 | 200 settings |
| `/api/android-capture/devices` | 执行 ADB devices -l | 200 devices/message |
| `/api/android-capture/sessions` | query `project_id,version_id?` | 200 `{sessions:[...]}` |
| `/api/android-capture/sessions/{id}` | 会话详情／进度轮询 | 200 session |
| `/api/android-capture/sessions/{id}/file` | query `path`，限定证据文件 | 200 图片／文本／JSON 文件 |
| `/api/android-capture/sessions/{id}/export` | 走查证据包 | 200 ZIP 附件 |
| `/api/jobs/{id}` | 文档任务详情、正文、来源、评审、检查 | 200 job |
| `/api/jobs/{id}/quality` | 轻量确定性检查结果 | 200 quality |
| `/api/jobs/{id}/versions` | Markdown 修订历史 | 200 版本数组 |
| `/api/jobs/{id}/versions/{version}` | 某一历史版本 | 200 版本对象 |
| `/api/jobs/{id}/prompt` | 生成任务包 | 200 Markdown 附件 |
| `/api/jobs/{id}/download` | 当前正文 | 200 Markdown 附件 |
| `/api/jobs/{id}/export` | query `format=docx/pdf/xlsx/csv,version?` | 200 文件附件 |
| `/` | 工作台 HTML | 200 HTML |
| `/app.js`、`/style.css` | 前端入口和样式 | 200 JS／CSS |
| `/modules/*`、`/render/*`、`/features/*` | static 内存在的 JS／CSS／HTML 文件 | 200 静态文件；越界／不存在为 404 |

### 11.2 POST 项目、资料和集成

| 路径 | 请求体主要字段 | 成功响应 |
|---|---|---|
| `/api/projects` | `name,brief?,workflow_mode?,platform?,team?,timebox?` | 201 project |
| `/api/project/update` | `id,brief?,workflow_mode?,platform?,team?,timebox?`；省略 brief 会置空；不支持改名 | 200 project |
| `/api/project/delete` | `id,confirmation`；confirmation 为完整项目名；移入本地回收站 | 200 删除结果 |
| `/api/trash/restore` | `id` 为回收站项 ID | 200 恢复项目 |
| `/api/trash/delete` | `id,confirmation` 为完整原项目名；永久删除 | 200 删除结果 |
| `/api/context` | `project_id,foundation?,working?`；两层各最多 12000 字；省略会写空 | 200 `{ok:true}` |
| `/api/conditions` | `project_id,id?,title,owner,due,status?,evidence?,block_level?,review_date?` | 201 条件记录 |
| `/api/product-versions` | `project_id,name,version_type?,status?,goal?,target_date?` | 201 version |
| `/api/product-versions/{id}` | `project_id` 和待修改版本字段 | 200 version |
| `/api/documents` | `project_id,name,content,version_id?,category?,subcategory?,competitor_id?,material_type?`；content 为 Base64 | 201 上传／重复结果 |
| `/api/documents/{id}/category` | `project_id,category` | 200 document |
| `/api/documents/{id}/subcategory` | `project_id,subcategory` | 200 document |
| `/api/documents/{id}/delete` | `project_id`；仅未引用图片 | 200 删除结果 |
| `/api/documents/{id}/translate` | `{}`；同步补评论译文 | 200 翻译统计 |
| `/api/projects/import` | `content` 为项目 ZIP 的 Base64 | 201 新 project |
| `/api/lanhu/snapshot` | `project_id,url,pages,version_id?` | 201 导入 document |
| `/api/packs` | `id,enabled`；布尔值 | 200 `{ok:true}` |
| `/api/integrations/lanhu` | `command?,package?,config_path?,enabled?` | 200 配置检测 |
| `/api/integrations/review-scraper` | legacy：`root,python?,enabled?`；EXE builtin：可省略 root，或回传当前随包 root，保留原生后端 | 200 配置检测 |

conditions 的 status 为 `open/in_progress/waiting_evidence/closed/waived`，block_level 为 `development/internal-test/external-release/non-blocking`；closed／waived 必须填 evidence。快速模式前端隐藏条件入口，接口仍保留。

Lanhu 配置目前只允许 `npx/npx.cmd` 和 `mcp-lanhu`。检测到配置不代表已请求蓝湖页面。snapshot 的 url 为公开／脱敏 `https://lanhuapp.com/...`，pages 为 1–120 项，每项可含 `id,name,states,text`，由外部已授权会话先只读取得；接口只存快照，不读取任意蓝湖 URL。

### 11.3 POST 采集

| 路径 | 请求体主要字段 | 成功响应 |
|---|---|---|
| `/api/competitors` | `project_id,platform,app_id,title?,role?,note?` | 201 新建或已有档案 |
| `/api/competitors/{id}/update` | `project_id,title?,role?,note?,archived?` | 200 档案 |
| `/api/competitors/{id}/documents` | `project_id,document_ids,material_type?`；关联已有原件 | 200 关联结果 |
| `/api/competitors/{id}/unlink` | `project_id,document_ids`；只解除关系 | 200 解除结果，`files_deleted:false` |
| `/api/competitors/inputs` | `project_id,competitor_ids,document_ids,version_id?`；只核对来源 | 200 明确输入快照 |
| `/api/competitors/search` | `project_id,query,platform?,country?,lang?,limit?,refresh?,version_id?` | 200 搜索结果 |
| `/api/competitors/detail` | `project_id,app_id,platform?,country?,lookup_country?,lang?,refresh?,version_id?` | 200 详情 |
| `/api/competitors/collect` | `project_id,countries,entries?/competitor_ids?`，采样／筛选／翻译／三项采集勾选／`collection_options?`／选用信息 | 202 `{count,items,...}` |
| `/api/reviews/scrape` | `project_id,app_id,platform?,countries` 及采样／筛选／翻译 | 202 单 scrape；成功直接入库 |
| `/api/reviews/scrape/{id}/cancel` | `{}` | 200 scrape |
| `/api/reviews/scrape/{id}/confirm` | `{}`，仅组合采集 ready | 200 completed scrape |
| `/api/reviews/scrape/{id}/retry` | `{}` | 202 **新 ID** scrape |
| `/api/competitors/revenue` | 收入来源与口径字段、`acknowledged:true` | 201 `{document,record}` |
| `/api/android-capture/settings` | `adb_path` | 200 settings |
| `/api/android-capture/sessions` | `project_id,package,scope,serial?,title?,version_id?,competitor_id?` | 201 prepared session |
| `/api/android-capture/sessions/{id}/start` | `{}` | 202 session |
| `/api/android-capture/sessions/{id}/resume` | `{}` | 202 session |
| `/api/android-capture/sessions/{id}/cancel` | `{}` | 200 session |
| `/api/android-capture/sessions/{id}/confirm` | `{}` | 200 confirmed session |

### 11.4 POST 文档任务

| 路径 | 请求体主要字段 | 成功响应 |
|---|---|---|
| `/api/prepare` | `project_id,task,instruction?,document_ids?,version_id?,source_selection_mode?,competitor_ids?` | 201 prepared job |
| `/api/assemble` | `project_id,task?,version_id?` | 201 合并 F1 job |
| `/api/jobs/{id}/start` | `{}` | 200 异步执行 job |
| `/api/jobs/{id}/cancel` | `{}` | 200 job |
| `/api/jobs/{id}/restore` | `{}`，cancelled／failed／interrupted | 200 prepared job |
| `/api/jobs/{id}/restore-cancelled` | `{}`，仅 cancelled，兼容旧入口 | 200 prepared job |
| `/api/jobs/{id}/archive` | `archived?`，默认 true | 200 job；非破坏隐藏 |
| `/api/jobs/{id}/review` | `decision=accepted/changes_requested,note?` | 200 job；修改意见须非空 |
| `/api/jobs/{id}/revise` | `{}`，先有 changes_requested 评审 | 200 新 prepared 修订 job |
| `/api/jobs/{id}/revise-comments` | `{}`，使用当前版本 open 批注 | 200 新 prepared 修订 job |
| `/api/jobs/{id}/edit` | `output,note?`，完整 Markdown | 200 新文档版本 job |
| `/api/jobs/{id}/versions/{version}` | `{}`，恢复历史正文并创建新版本 | 200 job |
| `/api/jobs/{id}/import` | `output`，仅 prepared | 200 completed job |
| `/api/jobs/{id}/comments` | `version,block_id,block_type,block_label,quote,action,note,author?` | 201 comment |
| `/api/jobs/{id}/comments/{comment_id}` | `status=open/resolved` | 200 comment |

批注 block_id 为 `block-<正整数>`，quote 必须出现在当前正文；action 为 `add/modify/delete/compress/preserve`，block_type 为前端正文块类型。新增／重新打开当前版本批注会撤销该稿确认。以任务详情的 `current_version` 绑定批注，不能把历史版本位置应用到新稿。

## 12. 工作台实际调用的外部接口／工具

下表来自随包采集引擎、scrapers 和工作台适配器的实际调用。它区分厂商公开接口、公开网页抓取和本机工具；不是所有条目都属于官方开放 API。这里记录接口形态与配置名，不提供账号、密钥或已经接通的承诺。

| 外部接口／工具 | 用途与实际调用方式 | 接口属性、凭据／环境 | 常见失败与边界 |
|---|---|---|---|
| Google Play 商店 | `google_play_scraper.search()` 搜索，`app()` 读取详情，`reviews()` 按国家／语言拉评论；来源页形如 `https://play.google.com/store/apps/details?id=<package>&gl=<country>` | 第三方库对公开商店的抓取，**不是 Google Play Developer API**；不要求 Play Console 密钥。EXE 用随包库，legacy 用选定 Python 的依赖 | 商店页面或库协议变化、地区未上架、网络／限流、依赖缺失；返回采样评论，不保证全量历史 |
| Apple iTunes Search | `GET https://itunes.apple.com/search`；参数 `term,country,entity=software,limit,lang`，当前 lang 映射为 `ja_jp` 或 `en_us` | Apple 公开 iTunes 搜索接口；不需要 App Store Connect 凭据 | 国家无结果、网络／限流或返回格式异常；只是商店候选，不能作为收入或下载量数据 |
| Apple iTunes Lookup | `GET https://itunes.apple.com/lookup`；参数 `id,country`，候选详情查询也传 `entity=software` | Apple 公开详情接口；不需要账号密钥；候选发现只允许 `itunes.apple.com` 的 HTTPS 请求与受限重定向 | 国家没有该 App；未返回的 Subtitle 等字段留空并警告，不猜补 |
| App Store 评论 RSS | `GET https://itunes.apple.com/<country>/rss/customerreviews/page=<page>/id=<id>/sortby=mostrecent/json` | Apple 的公开评论 RSS JSON feed；不是 App Store Connect 分析／经营 API；不需要密钥 | 当前最多访问 10 页并受请求数量限制；中途失败保留已取得页并给警告，不保证完整历史 |
| 商店宣传图片 CDN | 读取商店返回的截图 URL；后端允许 `googleusercontent.com`、`ggpht.com`、`mzstatic.com`、`apple.com` 及其子域名，HTTPS／443 | 官方商店 CDN 文件下载，**不是任意 URL 下载接口**；逐次校验重定向，最多 3 次跳转；单张最多 12 MiB，限定 PNG／JPEG／WEBP 并校验尺寸 | CDN 失败、格式／大小不符会记录警告；商店宣传图不是实机证据。前端 CSP 的预览域名更窄，不能保证白名单中每个域名都能远程预览 |
| Google 网页翻译 | `deep_translator.GoogleTranslator(source="auto", target="zh-CN").translate(...)`；单段最多传前 4500 字符 | 依赖库对 Google Translate 网页服务的访问，**不是 Google Cloud Translation 的官方付费 API／API Key 流程**；EXE builtin 默认使用；采集 HTTP API 不暴露 provider 选择 | 网络、限流或页面协议变化；失败保留原文和空译文／警告，不把未翻译当成已完成翻译 |
| DeepSeek／OpenAI 兼容翻译 | legacy 使用旧工具配置，经 OpenAI Python 客户端 `chat.completions.create()` 调用已配置 `base_url`、`model`，要求 JSON 对齐结果 | legacy 读取旧工具自身配置，工作台不复制密钥。独立包引擎另支持 `COMPETITOR_COLLECTOR_API_KEY`、`COMPETITOR_COLLECTOR_BASE_URL`、`COMPETITOR_COLLECTOR_MODEL` 的 OpenAI 兼容 provider；**本工作台 HTTP API 没有这些密钥写入接口** | 缺配置、鉴权／额度、超时、JSON 或译文数量不匹配；legacy 会拆批重试并可能回退 Google，独立 OpenAI provider 不承诺相同回退 |
| Codex CLI | 文档任务调用本机 `codex exec`；Android 自动走查启动独立受限 runner，连接本会话截图 MCP，由模型看图决定模块与操作 | 沿用技术同事本机 Codex 账号、模型与选定连接配置；包内不提供或复制认证密钥。Android 需要支持工具与图像的模型；会消耗模型用量 | CLI 未安装／未登录、模型或连接不可用、网络／额度、超时／取消、缺结构化 finish。能启动进程不代表已经走完整个 App |
| Android ADB | 本机可执行文件连接已授权设备；使用 `devices -l`、包名预检、固定包启动、UI dump／截图、受限 tap／back／swipe | 本机工具和 USB／已有设备连接，无云端 API Key；需可用 ADB、设备授权、目标 App 已安装，多设备需 serial | unauthorized／offline、包不存在、设备版本变化、外部页面／权限页或预算到限会暂停／阻塞。HTTP 不提供任意 shell、APK 安装或清数据 |
| Lanhu MCP | 读取由外部已授权 MCP 客户端完成；工作台仅保存连接配置、接收 `/api/lanhu/snapshot` 的结构化快照 | 本工作台没有直接调用 Lanhu 页面读取 API；配置存在不代表接通，不随包复制外部会话凭据 | 需外部客户端先成功读取；不能只给 URL 就承诺自动导入页面 |
| 收入／留存／画像／投放平台 | 本地人工收入记录和资料上传；`source_url` 只保存来源，不请求它 | 未自动接入 Sensor Tower、AppMagic、GA4、Firebase、友盟、广告或投放平台 API；由同事另行扩展 | 来源可能是估算／披露／未知；当前记录 `manual=true,verified=false`，不能写成平台自动核验 |

本机文件导入、普通项目管理和预览使用文件系统／SQLite 及相应 PDF、DOCX、图片库，不要求外部账号。EXE 默认采用**关键词检索**，不内置 embedding 模型，也不因启动或关键词搜索自动下载 embedding 模型。源码的可选 Hybrid 检索依赖其模型与索引环境，不可用时回退关键词；独立 Product KB MCP 是另一个只读 stdio 服务，不属于本 HTTP API。

商店网络、Google 翻译、模型 provider 和设备连接是不同依赖；其中某项成功不能代替其他项的验证。本文只做源码／接口静态核对，没有执行真实账号请求、付费模型任务或设备走查。

### 12.1 未实现的 HTTP 能力

目前**没有**以下 HTTP 能力：账号登录／注册／Cookie 会话、任意 shell 或 ADB 命令、安装 APK／清数据、iOS 实机操作、自动获取收入／投放／留存平台数据、任意 URL 爬取、通用 OCR、Figma／Axure 自动绘制、自动 SDK／支付验收、直接执行 MCP 工具、通用数据库查询、通用资料 DELETE、运行日志流或自动全 App 覆盖保证。不能仅凭 service 中有函数或前端有按钮就构造一个未列出的 API。

研究或修改接口时优先核对以下源文件：

- [HTTP 请求校验与状态码](../workbench/api/handler.py)
- [全部路由分发](../workbench/api/routes.py)
- [响应编码与下载文件名](../workbench/api/serializers.py)
- [前端请求与 token 用法](../workbench/static/modules/api.js)
- [评论与商店采集适配](../workbench/adapters/review_scraper.py)
- [候选发现](../workbench/adapters/competitor_discovery.py)
- [随包采集引擎、商店接口、翻译与图片下载](../packages/competitor-collector/competitor_collector/engine.py)
- [Google Play 和 App Store RSS 评论采样](../packages/competitor-collector/competitor_collector/scrapers.py)
- [Android 会话](../workbench/services/android_capture_service.py)
- [资料导入与读取](../workbench/services/material_service.py)
- [人工收入记录](../workbench/services/competitor_revenue_service.py)
- [项目包导入导出](../workbench/services/export_service.py)

本文示例不含真实 token、账号、私人数据或真实收入值。示例代码经静态核对；执行实际商店采集、设备走查或模型生成前，仍需调用方明确选择真实对象与范围。
