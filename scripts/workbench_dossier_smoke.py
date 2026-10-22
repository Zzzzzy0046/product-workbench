"""Local synthetic dossier UI fixture, with no external model or store calls."""
from io import BytesIO
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    sys.path.insert(0, str(location))
from PIL import Image, ImageDraw
from workbench.app import Workbench, Handler

data = ROOT / "work" / "dossier-update-20261022" / "qa-data"
app = Workbench(data, runner=lambda job: "# 合成测试交付物\n\n只用于本机界面测试，没有调用模型。")
if not app.rows("SELECT id FROM projects"):
    project = app.create_project("GBA 竞品档案演示", "合成演示资料，用于检验归档、勾选和导出，不代表竞品真实情况。")
    for number, package in ((1, "com.synthetic.gba.alpha"), (2, "com.synthetic.gba.beta")):
        competitor = app.competitor_service.upsert(project["id"], {"platform": "google_play", "app_id": package, "title": f"GBA 演示竞品 {number}", "role": "primary" if number == 1 else "feature"})
        listing = app.add_document(project["id"], f"商店资料-演示{number}.md", f"# 合成商店资料 {number}\n\n## 短描述\n这是演示短描述。\n\n## 长描述\n这里只是测试资料，不是实际竞品内容。".encode())
        reviews = app.add_document(project["id"], f"竞品评论-演示{number}.csv", ("review_id,content,original_content,translated_content,score,market,app_id\n" + f"review-{number},Synthetic review,Synthetic review,合成评论,4,us,{package}\n").encode("utf-8-sig"))
        raw = BytesIO()
        image = Image.new("RGB", (320, 640), "#e3eee7" if number == 1 else "#eee8de")
        ImageDraw.Draw(image).text((30, 45), f"SYNTHETIC SCREEN {number}", fill="#1d4939")
        image.save(raw, "PNG")
        screenshot = app.add_document(project["id"], f"演示截图{number}.png", raw.getvalue(), category="images", subcategory="competitor")
        for document, kind in ((listing, "store_info"), (reviews, "reviews"), (screenshot, "store_screenshot")):
            app.competitor_service.attach_documents(project["id"], competitor["id"], [document["id"]], kind)
    app.add_document(project["id"], "未分配的通用研究.txt", "这份是通用项目资料，没有竞品归属。".encode())
server = ThreadingHTTPServer(("127.0.0.1", 18865), Handler)
server.app = app
print("Synthetic dossier QA: http://127.0.0.1:18865/", flush=True)
try:
    server.serve_forever()
finally:
    app.close()
    server.server_close()
