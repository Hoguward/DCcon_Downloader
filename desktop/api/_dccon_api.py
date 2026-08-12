"""
디시인사이드 디시콘 API 클라이언트 (데스크톱 앱 dccon_gui.py의 DcconAPI를 그대로 이식).

이 파일은 데스크톱 앱과 완전히 동일한 파싱 로직을 쓴다 — 디시인사이드 페이지
구조가 개편되면 두 곳(데스크톱/웹) 모두 여기 한 곳만 고치면 되도록, GUI
의존성(tkinter, PIL 등)을 전혀 두지 않고 requests/bs4만으로 구성한다.
"""

import json
import os
import re
from urllib.parse import quote, unquote

import requests
from bs4 import BeautifulSoup

INVALID_FN_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name: str) -> str:
    """Windows 등에서 파일명에 못 쓰는 문자를 치환. 원본 dccon_gui.py와 동일."""
    name = (name or "").strip().strip('"').strip("'")
    name = INVALID_FN_CHARS.sub("_", name)
    return name.strip() or "untitled"


def filename_from_response(resp, fallback: str) -> str:
    """Content-Disposition 헤더 우선, 없으면 Content-Type으로 확장자를
    추정해 파일명을 결정. 원본 dccon_gui.py와 동일."""
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", cd, re.IGNORECASE)
    if m:
        return sanitize_filename(unquote(m.group(1)))
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.IGNORECASE)
    if m:
        return sanitize_filename(m.group(1))
    ct = resp.headers.get("Content-Type", "").lower()
    if "gif" in ct:
        ext = ".gif"
    elif "png" in ct:
        ext = ".png"
    elif "jpeg" in ct or "jpg" in ct:
        ext = ".jpg"
    elif "webp" in ct:
        ext = ".webp"
    else:
        ext = ".bin"
    return f"{fallback}{ext}"


BASE = "https://dccon.dcinside.com"
DETAIL_URL = f"{BASE}/index/package_detail"
TOP_URL = "https://json2.dcinside.com/json1/dccon_{kind}_top100.php?jsoncallback=cb"
IMG_URL = "https://dcimg5.dcinside.com/dccon.php?no={path}"

HEADERS = {
    "Referer": "https://dccon.dcinside.com/",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
}


class DcconAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        from requests.adapters import HTTPAdapter
        try:
            from urllib3.util.retry import Retry
            retries = Retry(
                total=2, connect=2, read=2, backoff_factor=0.3,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET", "POST"}),
            )
        except Exception:
            retries = 2
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_top(self, kind: str):
        """kind in {'day','week','month'}. TOP100 JSONP 응답에서 배열만
        추출한다(각 항목에 1~100의 rank 필드 포함)."""
        url = TOP_URL.format(kind=kind)
        r = self.session.get(url, timeout=15)
        r.raise_for_status()
        txt = r.text
        start = txt.find("[")
        end = txt.rfind("]")
        if start < 0 or end < 0:
            return []
        items = json.loads(txt[start:end + 1])
        for it in items:
            if it.get("img", "").startswith("//"):
                it["img"] = "https:" + it["img"]
        return items

    def get_list(self, kind: str, page: int):
        """kind in {'hot','new'}. (총_페이지, [{package_idx,img,title,nick_name}])."""
        url = f"{BASE}/{kind}/{page}"
        r = self.session.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        last_page = self._parse_last_page(soup)
        items = self._parse_listbox(soup, ".dccon_listbox .div_package")
        return last_page, items

    def search(self, keyword: str, page: int = 1, sort: str = "hot", category: str = "title"):
        """검색. (검색결과수문자열, 페이지수, items)

        category in {'title','nick_name','tags'} — 디시콘명/닉네임/태그.
        """
        encoded = quote(keyword, safe="")
        url = f"{BASE}/{sort}/{page}/{category}/{encoded}"
        r = self.session.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        if f"/{category}/" not in r.url:
            return "(0건)", 0, []

        tag = soup.select_one(".search_num")
        if not tag:
            return "(0건)", 0, []
        num_text = tag.get_text(strip=True)
        if "(0건)" in num_text:
            return num_text, 0, []

        items = self._parse_listbox(soup, ".dccon_shop_list .div_package")
        if not items:
            items = self._parse_listbox(soup, ".dccon_listbox .div_package")
        m = re.search(r"\d+", num_text)
        total = int(m.group()) if m else len(items)
        pages = max(1, (total + 14) // 15)
        return num_text, pages, items

    def get_detail(self, package_idx: str):
        r = self.session.post(
            DETAIL_URL,
            data={"package_idx": package_idx},
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        info = data.get("info", {})
        detail = data.get("detail", [])
        tags = data.get("tags", [])
        urls = [IMG_URL.format(path=info.get("main_img_path"))]
        for d in detail:
            urls.append(IMG_URL.format(path=d.get("path")))
        return {
            "title": (info.get("title") or "").strip(),
            "description": info.get("description", ""),
            "seller": f'{info.get("seller_name","")} {info.get("reg_date_short","")}'.strip(),
            "tags": ", ".join(t.get("tag", "") for t in tags),
            "urls": urls,
        }

    def fetch_image(self, url: str):
        """이미지 바이트와 Content-Type을 함께 반환 (프록시 스트리밍용)."""
        r = self.session.get(url, timeout=20)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "application/octet-stream")
        return r.content, content_type

    def download_image(self, url: str, fallback_name: str, out_dir: str) -> str:
        """이미지를 out_dir에 직접 저장(스트리밍). 원본 dccon_gui.py와 동일 —
        PyWebView 버전은 이 메서드로 지정된 저장 폴더에 실제 파일을 쓴다
        (원본 웹 배포판은 브라우저 다운로드 매니저를 썼지만, 여기서는
        데스크톱 앱답게 사용자가 고른 폴더에 그대로 저장한다)."""
        with self.session.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            fn = filename_from_response(r, fallback_name)
            full = os.path.join(out_dir, fn)
            with open(full, "wb") as f:
                for chunk in r.iter_content(65536):
                    if chunk:
                        f.write(chunk)
            return fn

    # --- 내부 ---
    @staticmethod
    def _parse_last_page(soup) -> int:
        a = soup.select_one(".page_end")
        if not a:
            return 1
        href = a.get("href", "")
        m = re.search(r"/(\d+)\s*$", href)
        return int(m.group(1)) if m else 1

    @staticmethod
    def _parse_listbox(soup, sel) -> list:
        out = []
        for el in soup.select(sel):
            img = el.select_one(".thumb_img")
            name = el.select_one(".dcon_name")
            seller = el.select_one(".dcon_seller")
            img_src = img.get("src") if img else ""
            if img_src.startswith("//"):
                img_src = "https:" + img_src
            out.append({
                "package_idx": el.get("package_idx", ""),
                "img": img_src,
                "title": (name.get_text(strip=True) if name else "").strip(),
                "nick_name": (seller.get_text(strip=True) if seller else "").strip(),
            })
        return out
