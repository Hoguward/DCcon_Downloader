"""
DCcon Downloader 웹 프록시 — 단일 FastAPI 앱.

디시인사이드 API가 CORS를 전혀 지원하지 않아(실측 확인: 모든 응답에
Access-Control-Allow-Origin 헤더 없음) 브라우저가 직접 호출할 수 없다.
이 앱이 대신 호출하고 CORS 헤더를 붙여 돌려준다.

파싱 로직 자체는 _dccon_api.py(데스크톱 앱 dccon_gui.py의 DcconAPI를
그대로 이식)에 있고, 이 파일은 그걸 HTTP 라우트로 감싸는 얇은 계층이다.
"""

import os
import sys
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

# Vercel의 Python 런타임은 api/index.py 를 모듈로 로드할 때 이 파일이 있는
# 디렉터리를 sys.path에 넣어주지 않는다(로컬 uvicorn 실행과의 차이 —
# 실배포에서 ModuleNotFoundError로 확인). 같은 폴더의 _dccon_api를 확실히
# 찾도록 경로를 명시적으로 추가한다.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _dccon_api import DcconAPI

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://hoguward.github.io")
ALLOWED_IMAGE_HOST = "dcimg5.dcinside.com"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)

api = DcconAPI()


@app.get("/api/top5")
def top5(kind: str = Query("day", pattern="^(day|week)$")):
    try:
        items = api.get_top5(kind)
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
def search(q: str, page: int = Query(1, ge=1), sort: str = "hot"):
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is required")
    try:
        num_text, total_pages, items = api.search(q, page, sort)
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
