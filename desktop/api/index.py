"""
DCcon Downloader 로컬 API — PyWebView 앱이 사용하는 FastAPI 서버.

원본(web/api/index.py, GitHub Pages + Vercel 배포)에서 CORS 미들웨어를
뺀 버전이다. 이 앱은 프론트엔드(public/index.html)와 API가 같은 로컬
서버(http://127.0.0.1:PORT)에서 서빙되어 오리진이 항상 같으므로 CORS
자체가 필요 없다 — 오히려 CORSMiddleware가 있으면 file://나 다른 포트로
실수로 열었을 때 원인 파악이 어려운 에러만 늘어난다.

파싱 로직 자체는 _dccon_api.py(원본 데스크톱 앱 dccon_gui.py의 DcconAPI를
그대로 이식한 것)에 있고, 이 파일은 그걸 HTTP 라우트로 감싸는 얇은
계층이다.
"""

import os
import sys
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

# 같은 폴더의 _dccon_api를 확실히 찾도록 경로를 명시적으로 추가한다
# (원본 web/api/index.py의 Vercel 관련 코멘트는 이 프로젝트엔 해당 없지만,
# 실행 방식에 따라 sys.path 구성이 달라질 수 있어 안전하게 유지한다).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _dccon_api import DcconAPI

ALLOWED_IMAGE_HOST = "dcimg5.dcinside.com"

app = FastAPI()
api = DcconAPI()


@app.get("/api/top5")
def top5(kind: str = Query("day", pattern="^(day|week|month)$")):
    try:
        items = api.get_top(kind)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")
    return {"items": items}


@app.get("/api/list")
def list_(kind: str = Query("new", pattern="^(new|hot)$"), page: int = Query(1, ge=1)):
    try:
        last_page, items = api.get_list(kind, page)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")
    return {"last_page": last_page, "items": items}


@app.get("/api/search")
def search(
    q: str,
    page: int = Query(1, ge=1),
    sort: str = "hot",
    category: str = Query("title", pattern="^(title|nick_name|tags)$"),
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is required")
    try:
        num_text, total_pages, items = api.search(q, page, sort, category)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")
    return {"num_text": num_text, "total_pages": total_pages, "items": items}


@app.get("/api/detail")
def detail(id: str):
    try:
        return api.get_detail(id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")


@app.get("/api/image")
def image(url: str):
    if urlparse(url).netloc != ALLOWED_IMAGE_HOST:
        raise HTTPException(status_code=400, detail=f"url must be on {ALLOWED_IMAGE_HOST}")
    try:
        data, content_type = api.fetch_image(url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")
    return Response(content=data, media_type=content_type)


@app.get("/api/local_image")
def local_image(path: str):
    """내 보관함(로컬 저장 폴더) 안의 이미지 파일을 서빙.

    브라우저(WebView2)는 보안 정책상 file:// 경로를 <img src>로 직접
    열지 못하므로 이 프록시를 거친다. path는 반드시 desktop.py의
    default_download_dir() 하위 경로여야 한다 — 아니면 임의의 로컬
    파일을 읽어 유출할 수 있는 path traversal이 되므로 화이트리스트로
    막는다(실제 다운로드 폴더는 사용자가 변경할 수 있어 고정 경로 하나만
    허용할 수는 없다 — 대신 desktop.get_config()의 download_dir 및 기본
    다운로드 폴더 둘 다를 허용 루트로 취급한다).
    """
    import desktop  # main.py가 sys.path에 프로젝트 루트를 넣어두므로 사용 가능

    allowed_roots = {os.path.abspath(desktop.default_download_dir())}
    configured = desktop.load_config().get("download_dir")
    if configured:
        allowed_roots.add(os.path.abspath(configured))

    real_path = os.path.abspath(path)
    if not any(
        real_path == root or real_path.startswith(root + os.sep)
        for root in allowed_roots
    ):
        raise HTTPException(status_code=403, detail="path is outside the allowed download directory")
    if not os.path.isfile(real_path):
        raise HTTPException(status_code=404, detail="file not found")

    ext = os.path.splitext(real_path)[1].lower()
    content_type = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
    with open(real_path, "rb") as f:
        data = f.read()
    return Response(content=data, media_type=content_type)


@app.get("/api/local_packages")
def local_packages():
    """내 보관함: 현재 다운로드 폴더를 스캔해 저장된 패키지 목록 반환."""
    import desktop

    config = desktop.load_config()
    download_dir = config.get("download_dir") or desktop.default_download_dir()
    items = desktop.scan_local_packages(download_dir)
    return {"items": items}


@app.get("/api/local_package_files")
def local_package_files(folder: str):
    """내 보관함 항목 상세: 폴더 안 이미지 파일 경로 목록."""
    import desktop

    allowed_roots = {os.path.abspath(desktop.default_download_dir())}
    configured = desktop.load_config().get("download_dir")
    if configured:
        allowed_roots.add(os.path.abspath(configured))

    real_folder = os.path.abspath(folder)
    if not any(
        real_folder == root or real_folder.startswith(root + os.sep)
        for root in allowed_roots
    ):
        raise HTTPException(status_code=403, detail="folder is outside the allowed download directory")
    if not os.path.isdir(real_folder):
        raise HTTPException(status_code=404, detail="folder not found")

    files = desktop.list_local_package_files(real_folder)
    return {"files": files}


# 정적 프론트엔드(public/index.html 등)를 이 FastAPI 앱이 직접 서빙한다.
# /api/* 라우트들을 먼저 등록한 뒤 마지막에 마운트해야 경로가 겹치지 않는다.
# PyInstaller로 번들링되면 실행 파일 기준 상대 경로가 달라지므로, 개발
# 실행(python main.py)과 번들 실행(exe) 모두에서 public/ 폴더를 찾을 수
# 있도록 main.py에서 sys._MEIPASS를 고려해 경로를 넘겨준다(_static_dir).
_static_dir = os.environ.get(
    "DCCON_STATIC_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public"),
)
app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
