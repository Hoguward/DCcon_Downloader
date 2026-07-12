"""
DCcon Downloader GUI (Python tkinter 대체)
- 원본 DCcon-Downloader 기능을 재구현한 한글 GUI
- 인기/신상 목록, 키워드 검색, 디시콘 상세 보기, 일괄 다운로드
- GIF/PNG/JPG 모두 정상 처리 (Content-Disposition 따옴표 버그 회피)

실행:
    python dccon_gui.py

의존성 (자동 설치 시도):
    pip install requests beautifulsoup4 pillow
"""

import io
import os
import re
import sys
import json
import time
import struct
import shutil
import tempfile
import threading
import subprocess
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor

# ---------- 의존성 자동 안내 ----------
_missing = []
try:
    import requests
except ImportError:
    _missing.append("requests")
try:
    from bs4 import BeautifulSoup
except ImportError:
    _missing.append("beautifulsoup4")
try:
    from PIL import Image, ImageTk, ImageSequence
except ImportError:
    _missing.append("pillow")
try:
    import ttkbootstrap  # noqa: F401  (테마용)
except ImportError:
    _missing.append("ttkbootstrap")
try:
    import win32clipboard  # noqa: F401  (클립보드 이미지/파일 복사용)
    import win32con  # noqa: F401
except ImportError:
    _missing.append("pywin32")

if _missing:
    msg = (
        "필요한 패키지가 설치되어 있지 않습니다:\n"
        f"  {', '.join(_missing)}\n\n"
        "명령 프롬프트에서 다음을 실행하세요:\n"
        f"  pip install {' '.join(_missing)}\n"
    )
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("패키지 누락", msg)
    except Exception:
        print(msg)
    sys.exit(1)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import ttkbootstrap as tb
try:
    from ttkbootstrap.style import ThemeDefinition
except Exception:
    ThemeDefinition = None


# ---------- 설정 ----------
BASE = "https://dccon.dcinside.com"
DETAIL_URL = f"{BASE}/index/package_detail"
TOP5_URL = "https://json2.dcinside.com/json1/dccon_{kind}_top5.php?jsoncallback={kind}_top5"
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

INVALID_FN_CHARS = re.compile(r'[\\/:*?"<>|]')
# Segoe UI는 한글 글리프가 없어 한글 텍스트를 그릴 때 Windows가 다른
# 폰트로 자동 대체(fallback)하는데, 이 과정에서 bold 굵기가 문자 종류
# (한글 vs 영문/숫자)별로 들쭉날쭉하게 적용되는 문제가 있었다. 한글/영문
# 모두 안정적으로 지원하고 bold 웨이트도 확실한 맑은 고딕으로 통일한다.
FONT_FAMILY = "맑은 고딕"
THUMB_SIZE = (150, 150)
THUMB_WORKERS = 16      # 썸네일/미리보기 동시 다운로드 스레드 수
THUMB_CACHE_MAX = 800   # 메모리에 유지할 썸네일 최대 개수 (초과 시 오래된 것부터 제거)
LIST_CACHE_TTL = 600    # 일간/주간 인기·NEW 목록 캐시 유효 시간(초) = 10분
GRID_COLS = 5           # 카드 그리드 최소/기본 열 수

# 색상 팔레트 (카드/호버 등 UI 공용) — DCinside 계열 근사값
COL_BG = "#ffffff"
COL_BORDER = "#dfe1e5"
COL_ACCENT = "#1e5fdb"       # DCinside 계열 로열 블루
COL_HOVER_BG = "#e8f0fe"     # 선택/호버 시 연한 파랑 배경
COL_THUMB_BG = "#f4f6f8"
COL_DOWNLOADED = "#1d9e75"      # 보관 중(다운로드됨) 카드 강조 — DCINSIDE_THEME_COLORS["success"]와 통일
COL_DOWNLOADED_BG = "#e6f7f1"   # 보관 중 카드 배경 (COL_HOVER_BG와 밝기 톤 맞춤)

# ttkbootstrap 커스텀 테마 색상 (DCinside 근사)
DCINSIDE_THEME_COLORS = {
    "primary": "#1e5fdb",
    "secondary": "#5f6b7a",
    "success": "#1d9e75",
    "info": "#2c6bed",
    "warning": "#ba7517",
    "danger": "#e24b4a",
    "light": "#f5f6f8",
    "dark": "#1c2a56",
    "bg": "#ffffff",
    "fg": "#222222",
    "selectbg": "#1e5fdb",
    "selectfg": "#ffffff",
    "border": "#dfe1e5",
    "inputfg": "#222222",
    "inputbg": "#ffffff",
    "active": "#e8f0fe",
}
CARD_WIDTH = 190        # 카드 1개가 차지하는 대략적인 폭(px) - 열 수 동적 계산용
PREVIEW_CELL_WIDTH = 120  # 상세창 미리보기 셀 폭(px) - 열 수 동적 계산용


def calc_cols(width: int, item_width: int, min_cols: int = 1) -> int:
    """가용 폭(width)에 아이템 폭(item_width)이 몇 개 들어가는지 계산."""
    return max(min_cols, width // item_width)


def bind_mousewheel(canvas: tk.Canvas):
    """마우스 포인터 아래에 있는 canvas만 휠 스크롤되도록 바인딩.

    <Enter>/<Leave> 시점에 bind_all을 걸고 해제하는 방식은, 상세창이 뜨는
    순간처럼 마우스가 실제로는 이동하지 않았는데 그 아래에 새 위젯이
    나타나는 경우 <Enter>가 발생하지 않아 스크롤이 먹통이 되는 문제가
    있었다. 대신 canvas마다 root에 전역으로 휠 이벤트를 걸어두되, 이벤트가
    들어올 때마다 event.widget에서 부모를 타고 올라가며 "지금 이 캔버스에
    속한 위젯 위에서 발생했는지"를 판별해, 맞을 때만 그 캔버스를 스크롤한다.
    """
    alive = {"value": True}

    def _on_wheel(e):
        if not alive["value"]:
            return
        widget = e.widget
        while widget is not None:
            if widget is canvas:
                # 콘텐츠가 뷰포트보다 길 때만 스크롤. 짧을 때 스크롤하면
                # 카드가 아래로 밀려나 빈 공간이 생기는 버그가 있었다.
                bbox = canvas.bbox("all")
                if bbox and (bbox[3] - bbox[1]) > canvas.winfo_height():
                    canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
                return
            widget = getattr(widget, "master", None)

    def _on_destroy(_e=None):
        alive["value"] = False

    canvas.bind_all("<MouseWheel>", _on_wheel, add="+")
    canvas.bind("<Destroy>", _on_destroy, add="+")


def update_scrollregion(canvas: tk.Canvas):
    """scrollregion 을 콘텐츠 크기에 맞추고, 콘텐츠가 뷰포트보다 짧으면
    스크롤 위치를 맨 위로 고정한다.

    콘텐츠(카드 한 줄 등)가 캔버스보다 짧은데도 이전 스크롤 위치가 남아
    있으면 카드가 아래로 밀려 보이는 문제가 있었다. 콘텐츠가 짧을 때는
    항상 맨 위(0)로 되돌려 이 현상을 막는다.
    """
    bbox = canvas.bbox("all")
    if not bbox:
        return
    canvas.configure(scrollregion=bbox)
    if (bbox[3] - bbox[1]) <= canvas.winfo_height():
        canvas.yview_moveto(0)


def _app_dir() -> str:
    """프로그램(스크립트 또는 .exe)이 실제 위치한 폴더를 반환.

    - Python 직접 실행:  dccon_gui.py 가 있는 폴더
    - PyInstaller .exe:  DCcon-Downloader.exe 가 있는 폴더
        (sys.frozen 이 True 이면 sys.executable 의 디렉토리를 사용.
         __file__ 은 임시 압축해제 폴더를 가리키므로 부적절.)
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _default_download_dir() -> str:
    """기본 다운로드 폴더를 결정.

    우선순위:
      1) <앱폴더>/../dccon_downloaded  가 이미 존재  → 그걸 사용
         (원본 DCcon-Downloader 와 같은 곳을 가리켜 기존 콘 컬렉션과 합쳐짐)
      2) <앱폴더>/dccon_downloaded     를 사용
         (.exe를 새 위치에 둔 경우, .exe 옆에 깔끔하게 폴더 생성)

    어느 쪽이든 [📁 변경] 버튼으로 사용자가 자유롭게 바꿀 수 있음.
    """
    base = _app_dir()
    parent_loc = os.path.abspath(os.path.join(base, "..", "dccon_downloaded"))
    if os.path.isdir(parent_loc):
        return parent_loc
    return os.path.abspath(os.path.join(base, "dccon_downloaded"))


DEFAULT_DOWNLOAD_DIR = _default_download_dir()

CONFIG_PATH = os.path.join(_app_dir(), "config.json")
CLIPBOARD_TMP_DIR = os.path.join(tempfile.gettempdir(), "dccon_clipboard_tmp")


def load_config() -> dict:
    """config.json을 읽어 dict로 반환. 없거나 손상됐으면 빈 dict.

    키 단위로 best-effort 적용하는 쪽(호출부)에서 누락된 키는 알아서
    기본값으로 폴백하므로, 여기서는 파일 자체의 존재/파싱 실패만 처리한다.
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(partial: dict) -> None:
    """기존 config.json에 partial을 병합해 저장. 실패해도 조용히 무시.

    실행 중 여러 지점(폴더 변경, 창 크기 변경, 화면 전환)에서 호출되므로
    쓰기 실패(권한 문제 등)가 앱 동작을 막으면 안 된다.
    """
    try:
        data = load_config()
        data.update(partial)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------- 유틸 ----------
def sanitize_filename(name: str) -> str:
    name = (name or "").strip().strip('"').strip("'")
    name = INVALID_FN_CHARS.sub("_", name)
    return name.strip() or "untitled"


def filename_from_response(resp, fallback: str) -> str:
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


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_NATSORT_RE = re.compile(r"(\d+)")


def _natural_sort_key(filename: str):
    """'icon_10'이 'icon_2'보다 앞에 오는 사전식 정렬 오류를 막는 정렬 키."""
    return [int(p) if p.isdigit() else p.lower() for p in _NATSORT_RE.split(filename)]


def _read_image_bytes(path_or_url: str, api) -> bytes:
    """온라인 URL과 로컬 파일 경로를 모두 받아 이미지 bytes를 반환.

    카드 썸네일/상세창 미리보기가 온라인(디시인사이드 URL)과 로컬(내
    보관함, 저장된 파일 경로) 두 소스를 동일한 방식으로 다뤄야 해서
    이 판별을 한 곳에 모았다. DcconAPI 자체는 순수 HTTP 클라이언트로
    유지하고, 로컬 분기는 이 모듈 레벨 함수에서 처리한다.
    """
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return api.fetch_thumb(path_or_url)
    with open(path_or_url, "rb") as f:
        return f.read()


def _scan_local_packages(download_dir: str) -> list:
    """저장 폴더 하위의 <제목>/icon_*.* 구조를 스캔해 카드용 item 리스트로 변환.

    각 하위 폴더 = 다운로드된 디시콘 패키지 하나. 폴더 안 이미지 파일
    중 자연 정렬 기준 첫 번째를 대표 썸네일로 쓴다. 제목(폴더명) 가나다순
    정렬로 반환한다.
    """
    items = []
    if not os.path.isdir(download_dir):
        return items
    for entry in os.scandir(download_dir):
        if not entry.is_dir():
            continue
        images = [
            f for f in os.listdir(entry.path)
            if f.lower().endswith(IMAGE_EXTS)
        ]
        if not images:
            continue
        images.sort(key=_natural_sort_key)
        thumb_path = os.path.join(entry.path, images[0])
        items.append({
            "title": entry.name,
            "nick_name": "",
            "img": thumb_path,
            "package_idx": "",
            "is_local": True,
            "folder_path": entry.path,
        })
    items.sort(key=lambda it: _natural_sort_key(it["title"]))
    return items


def _local_titles(download_dir: str) -> set:
    """저장 폴더에 이미 다운로드된 디시콘의 폴더명(제목) 집합.

    _scan_local_packages 가 반환하는 title 은 폴더명 그대로이고, 폴더명은
    다운로드 시 sanitize_filename(원본 제목)으로 만들어진다. 그래서 온라인
    목록의 제목과 비교할 때는 항상 sanitize_filename(item["title"])을
    거쳐야 특수문자가 포함된 제목도 올바르게 매칭된다.
    """
    return {it["title"] for it in _scan_local_packages(download_dir)}


def _is_animated_bytes(image_bytes: bytes) -> bool:
    try:
        im = Image.open(io.BytesIO(image_bytes))
        return getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1
    except Exception:
        return False


def _copy_bytes_as_dib(image_bytes: bytes) -> None:
    """정지 이미지 bytes를 Windows 클립보드에 CF_DIB(표준 이미지)로 복사.

    BMP로 저장한 뒤 14바이트 파일헤더(BITMAPFILEHEADER)를 제거하면
    남는 것이 곧 DIB(BITMAPINFOHEADER + 픽셀 데이터)다. CF_DIB는 알파
    채널을 지원하지 않으므로 RGB로 변환한다.
    """
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "BMP")
    dib = buf.getvalue()[14:]
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
    finally:
        win32clipboard.CloseClipboard()


def _copy_file_as_hdrop(file_path: str) -> None:
    """파일 자체를 Windows 클립보드에 CF_HDROP(파일 복사)으로 올린다.

    표준 이미지 포맷(CF_DIB)은 정지 프레임 한 장만 담을 수 있어 GIF
    애니메이션이 소실된다. CF_HDROP은 "파일 탐색기에서 파일을 복사한
    것"과 동일하게 동작해 대상 앱이 원본 파일을 그대로 읽으므로
    애니메이션이 보존된다 (실측 검증됨). DROPFILES 구조체를 수동으로
    조립해야 pywin32의 SetClipboardData(CF_HDROP, ...)에 넘길 수 있다.
    """
    file_list = (file_path + "\0").encode("utf-16-le") + "\0".encode("utf-16-le")
    header = struct.pack("<LLLLL", 20, 0, 0, 0, 1)  # DROPFILES: pFiles, pt, fNC, fWide
    data = header + file_list
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_HDROP, data)
    finally:
        win32clipboard.CloseClipboard()


def _ensure_clipboard_tmp_dir() -> str:
    """CF_HDROP용 임시 폴더를 준비. 이전 세션 잔여물은 베스트 에포트로 정리."""
    try:
        shutil.rmtree(CLIPBOARD_TMP_DIR, ignore_errors=True)
    except Exception:
        pass
    os.makedirs(CLIPBOARD_TMP_DIR, exist_ok=True)
    return CLIPBOARD_TMP_DIR


# ---------- API 래퍼 ----------
class DcconAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        # 커넥션 풀 확대 + 재시도.
        # 기본 HTTPAdapter의 pool_maxsize(10)는 썸네일을 동시에 많이 받을 때
        # 병목이 된다. 워커 수(THUMB_WORKERS)에 맞춰 풀을 키워 keep-alive
        # 커넥션을 재사용하고, 일시적 5xx/429 에는 짧게 재시도한다.
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
        adapter = HTTPAdapter(
            pool_connections=THUMB_WORKERS,
            pool_maxsize=THUMB_WORKERS * 2,
            max_retries=retries,
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_top5(self, kind: str):
        """kind in {'day','week'}. JSONP 응답에서 배열만 추출."""
        url = TOP5_URL.format(kind=kind)
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

    def search(self, keyword: str, page: int = 1, sort: str = "hot"):
        """검색. (검색결과수문자열, 페이지수, items)

        DCInside 검색은 키워드가 URL path segment 안에 들어가므로
        반드시 percent-encoding 해야 합니다. requests가 path를 자동으로
        인코딩하지 않으므로 quote()로 명시적으로 처리합니다.
        """
        # encodeURIComponent 와 동등한 동작 (특수문자, 한글 모두 인코딩)
        encoded = quote(keyword, safe="")
        url = f"{BASE}/{sort}/{page}/title/{encoded}"
        r = self.session.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 서버가 /title/keyword 를 다른 경로로 리다이렉트했으면 검색 실패로 판단.
        if "/title/" not in r.url:
            return "(0건)", 0, []

        # 검색 결과 페이지에는 .search_num 이 존재합니다.
        # 없으면 페이지 구조가 바뀐 것일 수 있으니 결과 0으로 처리.
        tag = soup.select_one(".search_num")
        if not tag:
            return "(0건)", 0, []
        num_text = tag.get_text(strip=True)
        if "(0건)" in num_text:
            return num_text, 0, []

        items = self._parse_listbox(soup, ".dccon_shop_list .div_package")
        # 검색 페이지에서 셀렉터가 바뀌었을 가능성 대비
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

    def download_image(self, url: str, fallback_name: str, out_dir: str) -> str:
        with self.session.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            fn = filename_from_response(r, fallback_name)
            full = os.path.join(out_dir, fn)
            with open(full, "wb") as f:
                for chunk in r.iter_content(65536):
                    if chunk:
                        f.write(chunk)
            return fn

    def fetch_thumb(self, url: str) -> bytes:
        r = self.session.get(url, timeout=15)
        r.raise_for_status()
        return r.content

    # --- 내부 ---
    @staticmethod
    def _parse_last_page(soup) -> int:
        a = soup.select_one(".page_end")
        if not a:
            # 마지막 페이지를 찾지 못하면 1로 가정
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


# ---------- GUI ----------
class DcconApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DCcon Downloader (Python GUI)")

        self._config = load_config()

        self.geometry("1100x720")
        self.minsize(900, 600)
        self.maxsize(self.winfo_screenwidth(), self.winfo_screenheight())

        self.api = DcconAPI()
        self.executor = ThreadPoolExecutor(max_workers=THUMB_WORKERS)
        self.current_items = []
        self._show_pager = True
        self.thumb_refs = {}      # 카드 썸네일 ImageTk 참조 보관
        self.preview_refs = []    # 상세창 이미지 참조 보관
        # 일간/주간 인기·NEW 목록 결과 캐시. 키: ("top", period) 또는
        # ("new", kind, page). 값: (timestamp, last_page, items, show_pager).
        # config.json에는 넣지 않는다 — 휘발성 데이터라 재시작 후 오래된
        # 값이 남으면 오히려 혼란스럽다(설계 논의 결론).
        self._list_cache = {}
        saved_dir = self._config.get("download_dir")
        initial_dir = saved_dir if saved_dir and os.path.isdir(saved_dir) else DEFAULT_DOWNLOAD_DIR
        self.download_dir = tk.StringVar(value=initial_dir)
        self.mode = tk.StringVar(value="new")        # new | search | top | local
        self.period = tk.StringVar(value="day")      # day | week (top용)
        self.page = 1
        self.last_page = 1
        self.last_search = ""
        self._did_initial_fit = False   # 첫 로딩 후 창 높이를 콘텐츠에 맞추는 1회성 플래그
        self._geometry_save_job = None  # <Configure> 디바운스용 after() 핸들

        # 저장된 창 크기/위치가 있으면 그대로 적용하고, 콘텐츠 맞춤 자동 조정은
        # 건너뛴다 (사용자가 이미 조정한 크기를 존중).
        saved_geometry = self._config.get("window_geometry")
        if saved_geometry:
            try:
                self.geometry(saved_geometry)
                self._did_initial_fit = True
            except Exception:
                pass

        _ensure_clipboard_tmp_dir()

        self._build_ui()
        self._bind_shortcuts()
        self.bind("<Configure>", self._on_window_configure)
        self.after(100, self._restore_last_mode)

    def _restore_last_mode(self):
        """config.json에 저장된 마지막 화면(모드)으로 복원. 없으면 NEW 목록."""
        saved = self._config.get("last_mode") or {}
        mode = saved.get("mode")
        page = saved.get("page", 1) if isinstance(saved.get("page"), int) else 1
        if mode == "top" and saved.get("period") in ("day", "week"):
            self.load_top(saved["period"])
        elif mode == "search" and saved.get("search_keyword"):
            self.search_var.set(saved["search_keyword"])
            self.do_search(page=page)
        elif mode == "local":
            self.load_local(page)
        else:
            self.load_list("new", page)

    def _on_window_configure(self, event):
        # top-level 창 자체의 이동/리사이즈만 관심 대상 — 자식 위젯의
        # <Configure> 이벤트가 훨씬 자주 버블링되므로 걸러낸다.
        if event.widget is not self:
            return
        if self._geometry_save_job is not None:
            self.after_cancel(self._geometry_save_job)
        self._geometry_save_job = self.after(300, self._save_window_geometry)

    def _save_window_geometry(self):
        self._geometry_save_job = None
        save_config({"window_geometry": self.geometry()})

    def _save_last_mode(self, **fields):
        """현재 화면 상태를 config.json에 저장. 각 로딩 함수에서 호출."""
        save_config({"last_mode": fields})

    def _bind_shortcuts(self):
        def focus_search(_e=None):
            self.search_entry.focus_set()
            self.search_entry.select_range(0, "end")
            return "break"
        self.bind_all("<Control-f>", focus_search)
        self.bind_all("<F5>", lambda e: self.reload_current())

    def reload_current(self):
        """현재 보고 있는 화면(모드/페이지)을 그대로 다시 불러온다.

        F5/새로고침 버튼에서만 호출되므로 목록 캐시를 무시하고(force=True)
        항상 서버에서 새로 받아온다. 탭 버튼 클릭은 이 함수를 거치지 않아
        캐시를 그대로 활용한다.
        """
        mode = self.mode.get()
        if mode == "top":
            self.load_top(self.period.get(), force=True)
        elif mode == "search" and self.last_search:
            self._goto_page(self.page)
        elif mode == "local":
            self.load_local(self.page)
        else:
            self.load_list("new", self.page, force=True)

    def _sync_nav_active(self):
        """현재 보기(mode/period)에 해당하는 세그먼트 탭만 primary 로 강조."""
        mode = self.mode.get()
        period = self.period.get()
        states = {
            self.nav_day: mode == "top" and period == "day",
            self.nav_week: mode == "top" and period == "week",
            self.nav_new: mode == "new",
            self.nav_local: mode == "local",
        }
        for btn, on in states.items():
            btn.configure(bootstyle="primary" if on else "secondary-outline")

    # ---------- UI 구성 ----------
    def _build_ui(self):
        # ttkbootstrap 로 DCinside 근사 테마 적용. 커스텀 테마 등록에 실패하면
        # 내장 라이트 테마(litera)로 폴백한다.
        self.style = tb.Style()
        applied = False
        if ThemeDefinition is not None:
            try:
                self.style.register_theme(
                    ThemeDefinition("dcinside", DCINSIDE_THEME_COLORS, "light")
                )
                self.style.theme_use("dcinside")
                applied = True
            except Exception:
                applied = False
        if not applied:
            try:
                self.style.theme_use("litera")
            except Exception:
                pass

        # 상단 브랜드 바 — 파란 포인트를 길게 주는 헤더.
        # ttkbootstrap 테마 하에서 일반 tk 위젯의 bg 가 무시될 수 있어,
        # 테마와 확실히 호환되는 bootstyle(primary / inverse-primary)로 칠한다.
        header = tb.Frame(self, bootstyle="primary")
        header.pack(side="top", fill="x")
        tb.Label(header, text="DCcon Downloader", bootstyle="inverse-primary",
                 font=(FONT_FAMILY, 13, "bold")).pack(side="left", padx=(14, 8), pady=9)
        tb.Label(header, text="디시콘 일괄 다운로더", bootstyle="inverse-primary",
                 font=(FONT_FAMILY, 9)).pack(side="left", pady=9)

        # 저장 폴더 UI를 브랜드 바 오른쪽에 배치. 검색 툴바에 함께 두면
        # 창이 좁아졌을 때 [변경]/[열기] 버튼이 창 밖으로 밀려 안 보이는
        # 문제가 있었는데, 브랜드 바는 폭이 넉넉하고 이 앱에서 사용
        # 빈도가 높은 기능이라 상시 노출되는 자리로 옮겼다.
        tb.Button(header, text="열기", bootstyle="secondary-outline",
                  command=self.open_dir).pack(side="right", padx=(0, 14), pady=9)
        # light-outline 은 파란 브랜드 바 배경과 대비가 거의 없어 텍스트가
        # 안 보이는 문제가 있었다. warning(노란색 계열)로 확실한 대비를 준다.
        tb.Button(header, text="📁 변경", bootstyle="warning",
                  command=self.choose_dir).pack(side="right", padx=(0, 6), pady=9)
        self.dir_entry = ttk.Entry(header, textvariable=self.download_dir, state="readonly", width=32)
        self.dir_entry.pack(side="right", padx=(0, 6), pady=9)
        tb.Label(header, text="저장 폴더:", bootstyle="inverse-primary",
                 font=(FONT_FAMILY, 9)).pack(side="right", padx=(20, 4), pady=9)

        # 상단 툴바
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(side="top", fill="x")

        # 세그먼트 탭 (현재 보기만 primary 로 강조)
        self.nav_day = tb.Button(top, text="일간 인기", bootstyle="secondary-outline",
                                 command=lambda: self.load_top("day"))
        self.nav_day.pack(side="left")
        self.nav_week = tb.Button(top, text="주간 인기", bootstyle="secondary-outline",
                                  command=lambda: self.load_top("week"))
        self.nav_week.pack(side="left", padx=(4, 12))
        self.nav_new = tb.Button(top, text="NEW", bootstyle="secondary-outline",
                                 command=lambda: self.load_list("new", 1))
        self.nav_new.pack(side="left", padx=(0, 4))
        self.nav_local = tb.Button(top, text="내 보관함", bootstyle="secondary-outline",
                                   command=lambda: self.load_local(1))
        self.nav_local.pack(side="left", padx=(0, 4))
        tb.Button(top, text="⟳ 새로고침", bootstyle="secondary-link",
                  command=self.reload_current).pack(side="left", padx=(0, 12))

        # 페이지네이션을 검색 줄 오른쪽 끝에 배치 — 이전에는 검색 줄 아래에
        # 독립된 줄(nav)로 있었으나, 저장 폴더 UI가 브랜드 바로 옮겨가며
        # 줄 수를 줄이기 위해 같은 줄로 합쳤다. side="right" 는 pack 순서의
        # 역순으로 채워지므로, 가장 오른쪽에 보일 title_lbl 을 먼저 pack 한다.
        self.title_lbl = ttk.Label(top, text="", foreground="#666")
        self.title_lbl.pack(side="right", padx=(20, 0))
        self.next_btn = tb.Button(top, text="다음 ▶", bootstyle="secondary-outline", command=self.next_page)
        self.next_btn.pack(side="right")
        self.page_lbl = ttk.Label(top, text="1 / 1")
        self.page_lbl.pack(side="right", padx=8)
        self.prev_btn = tb.Button(top, text="◀ 이전", bootstyle="secondary-outline", command=self.prev_page)
        self.prev_btn.pack(side="right")

        ttk.Label(top, text="검색:").pack(side="left")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.search_var, width=22)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda e: self.do_search())
        ent.bind("<Escape>", lambda e: (self.search_var.set(""), self.focus_set()))
        self.search_entry = ent
        tb.Button(top, text="찾기", bootstyle="primary", command=self.do_search).pack(side="left")

        # 현재 경로를 툴팁처럼 보여주기 위해 경로가 너무 길 때 끝부분만 보이도록
        # entry의 view를 끝으로 이동 (저장 폴더 입력창은 브랜드 바에 있음)
        def _scroll_end(*_):
            try:
                self.dir_entry.xview_moveto(1.0)
            except Exception:
                pass
        self.download_dir.trace_add("write", _scroll_end)
        self.after(50, _scroll_end)

        # 메인 카드 영역 (스크롤 가능한 캔버스)
        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True, padx=10, pady=8)
        self.canvas = tk.Canvas(body, highlightthickness=0, bg=COL_BG)
        self.vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        self.grid_frame = ttk.Frame(self.canvas)
        # anchor="n": 그리드를 캔버스 가로 중앙에 배치 (좌우 여백 균등).
        # 실제 중앙 x 좌표는 _on_canvas_resize 에서 캔버스 폭에 맞춰 갱신한다.
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="n")
        self.grid_frame.bind("<Configure>", lambda e: self._on_grid_configure())
        self.grid_cols = GRID_COLS
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        bind_mousewheel(self.canvas)

        # 상태바
        self.status_var = tk.StringVar(value="준비")
        ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(10, 4)).pack(side="bottom", fill="x")

    def _on_canvas_resize(self, event):
        # 그리드를 캔버스 가로 중앙으로 이동 (그리드 폭은 콘텐츠에 맞게 자연 크기 유지).
        self.canvas.coords(self.canvas_window, event.width / 2, 0)
        new_cols = calc_cols(event.width, CARD_WIDTH, min_cols=1)
        if new_cols != self.grid_cols:
            self.grid_cols = new_cols
            if self.current_items:
                self._show_items(self.current_items, self._show_pager, keep_scroll=True)

    def _on_grid_configure(self):
        update_scrollregion(self.canvas)
        self._sync_scrollbar()

    def _sync_scrollbar(self):
        """콘텐츠가 뷰포트보다 길 때만 세로 스크롤바를 표시.

        스크롤이 필요 없을 때 스크롤바를 숨겨 오른쪽에 남는 빈 여백을
        없애고 좌우 여백을 대칭으로 만든다.
        """
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        need = (bbox[3] - bbox[1]) > self.canvas.winfo_height()
        mapped = self.vbar.winfo_ismapped()
        if need and not mapped:
            self.vbar.pack(side="right", fill="y")
        elif not need and mapped:
            self.vbar.pack_forget()

    # ---------- 헬퍼 ----------
    def set_status(self, msg):
        self.status_var.set(msg)
        self.update_idletasks()

    def _cache_thumb(self, key, img):
        """썸네일 참조를 캐시에 저장하고 상한을 넘으면 오래된 것부터 제거.

        dict는 삽입 순서를 보존하므로 앞쪽(=오래된) 항목부터 버린다.
        참조를 유지해야 ImageTk 이미지가 GC 되지 않으므로 캐시가 곧
        메모리 라이프타임 관리 역할도 겸한다.
        """
        self.thumb_refs[key] = img
        if len(self.thumb_refs) > THUMB_CACHE_MAX:
            drop = len(self.thumb_refs) - THUMB_CACHE_MAX
            for k in list(self.thumb_refs)[:drop]:
                self.thumb_refs.pop(k, None)

    def choose_dir(self):
        cur = self.download_dir.get()
        # 현재 폴더가 없으면 부모 폴더에서 시작
        start = cur if os.path.isdir(cur) else os.path.dirname(cur) or os.getcwd()
        d = filedialog.askdirectory(
            title="디시콘 저장 폴더 선택",
            initialdir=start,
            mustexist=False,
        )
        if d:
            # tkinter는 슬래시(/)로 반환 — Windows 표시용으로 백슬래시로 변환
            d = os.path.normpath(d)
            self.download_dir.set(d)
            save_config({"download_dir": d})

    def open_dir(self):
        d = self.download_dir.get()
        os.makedirs(d, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(d)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showerror("열기 실패", str(e))

    # ---------- 목록 로딩 ----------
    def clear_grid(self, reset_scroll: bool = True):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        if reset_scroll:
            self.canvas.yview_moveto(0)

    def update_nav(self, show_pager=True):
        self.page_lbl.config(text=f"{self.page} / {self.last_page}")
        state_prev = "normal" if self.page > 1 and show_pager else "disabled"
        state_next = "normal" if self.page < self.last_page and show_pager else "disabled"
        self.prev_btn.config(state=state_prev)
        self.next_btn.config(state=state_next)

    def _cache_get(self, key):
        """목록 캐시 조회. TTL이 지났으면 만료된 것으로 취급해 None 반환."""
        entry = self._list_cache.get(key)
        if entry is None:
            return None
        ts, last_page, items, show_pager = entry
        if time.time() - ts > LIST_CACHE_TTL:
            return None
        return last_page, items, show_pager

    def load_top(self, period, force: bool = False):
        self.mode.set("top"); self.period.set(period); self.page = 1; self.last_page = 1
        self._sync_nav_active()
        self.title_lbl.config(text=f"{'일간' if period=='day' else '주간'} 인기 디시콘")
        self._save_last_mode(mode="top", period=period)

        cache_key = ("top", period)
        if not force:
            cached = self._cache_get(cache_key)
            if cached is not None:
                last_page, items, show_pager = cached
                self.last_page = last_page
                self.set_status("불러오는 중... (캐시)")
                self.clear_grid()
                self._show_items(items, show_pager)
                return

        self.set_status("불러오는 중...")
        # 썸네일 캐시는 유지 — 같은 콘을 다시 볼 때 즉시 표시 (재다운로드 방지)
        self.clear_grid()
        threading.Thread(target=self._fetch_top, args=(period,), daemon=True).start()

    def _fetch_top(self, period):
        try:
            items = self.api.get_top5(period)
            # JSON 응답은 thumb_img 대신 img, title, nick_name, package_idx 키일 수 있음
            normalized = []
            for it in items:
                normalized.append({
                    "package_idx": str(it.get("package_idx", "")),
                    "img": it.get("img", ""),
                    "title": it.get("title", ""),
                    "nick_name": it.get("nick_name", ""),
                })
            self._list_cache[("top", period)] = (time.time(), 1, normalized, False)
            self.after(0, self._show_items, normalized, False)
        except Exception as e:
            self.after(0, self.set_status, f"실패: {e}")

    def load_list(self, kind, page, force: bool = False):
        self.mode.set(kind); self.page = page
        self._sync_nav_active()
        self.title_lbl.config(text="NEW 디시콘")
        self._save_last_mode(mode="new", page=page)

        cache_key = ("new", kind, page)
        if not force:
            cached = self._cache_get(cache_key)
            if cached is not None:
                last_page, items, show_pager = cached
                self.last_page = last_page
                self.set_status(f"{kind.upper()} {page}페이지 (캐시)")
                self.clear_grid()
                self._show_items(items, show_pager)
                return

        self.set_status(f"{kind.upper()} {page}페이지 불러오는 중...")
        # 썸네일 캐시는 유지 — 같은 콘을 다시 볼 때 즉시 표시 (재다운로드 방지)
        self.clear_grid()
        threading.Thread(target=self._fetch_list, args=(kind, page), daemon=True).start()

    def _fetch_list(self, kind, page):
        try:
            last, items = self.api.get_list(kind, page)
            self.last_page = max(last, page)
            self._list_cache[("new", kind, page)] = (time.time(), self.last_page, items, True)
            self.after(0, self._show_items, items, True)
        except Exception as e:
            self.after(0, self.set_status, f"실패: {e}")

    def do_search(self, page: int = 1):
        kw = self.search_var.get().strip()
        if not kw:
            return
        self.mode.set("search"); self.last_search = kw; self.page = page
        self._sync_nav_active()
        self.title_lbl.config(text=f'검색: "{kw}"')
        self.set_status("검색 중...")
        self._save_last_mode(mode="search", search_keyword=kw, page=page)
        # 썸네일 캐시는 유지 — 같은 콘을 다시 볼 때 즉시 표시 (재다운로드 방지)
        self.clear_grid()
        threading.Thread(target=self._fetch_search, args=(kw, page), daemon=True).start()

    def _fetch_search(self, kw, page):
        try:
            num_text, pages, items = self.api.search(kw, page)
            self.last_page = max(pages, 1)
            self.page = page
            self.after(0, self.set_status, f"검색 결과 {num_text}")
            self.after(0, self._show_items, items, True)
        except Exception as e:
            self.after(0, self.set_status, f"검색 실패: {e}")

    def prev_page(self):
        if self.page <= 1:
            return
        self._goto_page(self.page - 1)

    def next_page(self):
        if self.page >= self.last_page:
            return
        self._goto_page(self.page + 1)

    def _goto_page(self, p):
        mode = self.mode.get()
        if mode == "new":
            self.load_list(mode, p)
        elif mode == "search":
            self.page = p
            self.set_status(f'"{self.last_search}" {p}페이지 검색 중...')
            self._save_last_mode(mode="search", search_keyword=self.last_search, page=p)
            self.clear_grid()
            threading.Thread(target=self._fetch_search, args=(self.last_search, p), daemon=True).start()
        elif mode == "local":
            self.load_local(p)

    # ---------- 내 보관함 (로컬 목록) ----------
    def load_local(self, page: int = 1):
        """서버 호출 없이 저장 폴더를 스캔해 로컬에 저장된 디시콘 목록을 표시."""
        self.mode.set("local"); self.page = page
        self._sync_nav_active()
        self.title_lbl.config(text="내 보관함")
        self.set_status("저장 폴더 스캔 중...")
        self._save_last_mode(mode="local", page=page)
        self.clear_grid()
        threading.Thread(target=self._fetch_local, args=(page,), daemon=True).start()

    def _fetch_local(self, page):
        try:
            all_items = _scan_local_packages(self.download_dir.get())
            per_page = 15
            self.last_page = max(1, (len(all_items) + per_page - 1) // per_page)
            page = max(1, min(page, self.last_page))
            self.page = page
            start = (page - 1) * per_page
            page_items = all_items[start:start + per_page]
            self.after(0, self._show_items, page_items, True)
        except Exception as e:
            self.after(0, self.set_status, f"실패: {e}")

    # ---------- 카드 렌더링 ----------
    def _show_items(self, items, show_pager, keep_scroll=False):
        self.current_items = items
        self._show_pager = show_pager
        self.update_nav(show_pager)
        self.clear_grid(reset_scroll=False)
        if not items:
            ttk.Label(self.grid_frame, text="결과가 없습니다.", padding=20).grid(row=0, column=0)
            self.set_status("결과 없음")
            self.canvas.yview_moveto(0)
            return
        # 내 보관함 화면은 항목 전체가 이미 다운로드된 것이므로 하이라이트가
        # 무의미해 계산을 건너뛴다. 그 외 화면에서는 카드마다 디스크를 다시
        # 스캔하지 않도록 한 번만 스캔해 재사용한다.
        local_titles = (
            set() if self.mode.get() == "local"
            else _local_titles(self.download_dir.get())
        )
        for i, it in enumerate(items):
            r, c = divmod(i, self.grid_cols)
            card = self._make_card(self.grid_frame, it, local_titles)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")
        # 새 목록을 그렸으면 스크롤을 맨 위로. (창 크기 변경으로 인한
        # 재배치일 때는 keep_scroll=True 로 현재 위치를 유지한다.)
        if not keep_scroll:
            self.canvas.yview_moveto(0)
        # 첫 실행 시 카드가 화면 아래에서 잘리지 않도록 창 높이를 콘텐츠에
        # 맞춰 한 번만 조정한다.
        if not keep_scroll and not self._did_initial_fit:
            self.after_idle(self._fit_window_to_content)
        self.set_status(f"{len(items)}개 표시")

    def _fit_window_to_content(self):
        """카드 그리드 전체가 세로로 보이도록 창 높이를 콘텐츠에 맞춘다.

        - 썸네일 박스가 고정 크기라 이미지 로딩 전에도 높이가 안정적이다.
        - 화면 높이를 넘지 않도록 상한을 둔다(작업표시줄/타이틀바 여유 포함).
        - 최초 1회만 실행 — 이후 사용자가 창 크기를 바꾸면 존중한다.
        """
        if self._did_initial_fit:
            return
        self.update_idletasks()
        canvas_h = self.canvas.winfo_height()
        canvas_w = self.canvas.winfo_width()
        if canvas_h <= 1 or canvas_w <= 1:
            # 아직 레이아웃 전이면 잠시 후 재시도
            self.after(50, self._fit_window_to_content)
            return
        self._did_initial_fit = True

        content_h = self.grid_frame.winfo_reqheight()
        content_w = self.grid_frame.winfo_reqwidth()
        chrome_h = self.winfo_height() - canvas_h   # 툴바/페이저/상태바 등 캔버스 외 높이
        # 가로 크롬에서 스크롤바 폭은 제외한다. 콘텐츠가 다 맞으면 스크롤바가
        # 숨겨지므로, 포함하면 오른쪽에 그만큼 빈 여백이 남는다.
        sb = 16 if self.vbar.winfo_ismapped() else 0
        chrome_w = self.winfo_width() - canvas_w - sb

        # 세로: 카드 전체 높이 + 약간의 여유
        needed_h = chrome_h + content_h + 8
        # 가로: 콘텐츠 폭 + 좌우 여백(각 20px). 현재 열 수가 유지되도록 넉넉히.
        needed_w = chrome_w + content_w + 40

        screen_h = self.winfo_screenheight()
        screen_w = self.winfo_screenwidth()
        target_h = max(int(min(needed_h, screen_h - 80)), 600)
        target_w = max(int(min(needed_w, screen_w - 40)), 900)
        self.geometry(f"{target_w}x{target_h}")

    def _make_card(self, parent, item, local_titles: set = frozenset()):
        # 이미 저장 폴더에 다운로드되어 있는 디시콘인지 — 다운로드 시
        # 폴더명이 sanitize_filename(제목)이므로 같은 변환을 거쳐 비교한다.
        is_downloaded = sanitize_filename(item["title"]) in local_titles

        # tk.Frame + highlightthickness 로 테두리를 그려 호버 시 색만 바꿔
        # 부드러운 강조 효과를 낸다 (ttk 테두리는 색 제어가 까다로움).
        card = tk.Frame(parent, bg=COL_BG, bd=0,
                        highlightthickness=1,
                        highlightbackground=COL_BORDER, highlightcolor=COL_BORDER)
        inner = tk.Frame(card, bg=COL_BG)
        inner.pack(padx=8, pady=8)

        # 고정 크기 썸네일 영역 — 이미지 로딩 전후로 카드 크기가 흔들리지 않음
        thumb_box = tk.Frame(inner, width=THUMB_SIZE[0], height=THUMB_SIZE[1],
                             bg=COL_THUMB_BG)
        thumb_box.pack()
        thumb_box.pack_propagate(False)
        thumb = tk.Label(thumb_box, text="…", bg=COL_THUMB_BG, fg="#c4c4c4",
                         font=(FONT_FAMILY, 22))
        thumb.pack(expand=True)

        title = tk.Label(inner, text=item["title"][:24], bg=COL_BG, fg="#222",
                         wraplength=THUMB_SIZE[0], justify="center",
                         font=(FONT_FAMILY, 9, "bold"))
        title.pack(pady=(8, 0))
        seller = tk.Label(inner, text=item["nick_name"][:24], bg=COL_BG, fg="#999",
                          font=(FONT_FAMILY, 8))
        seller.pack()

        widgets = (card, inner, thumb_box, thumb, title, seller)
        for w in widgets:
            w.bind("<Button-1>", lambda e, it=item: self.open_detail(it))
            w.configure(cursor="hand2")

        def _set_hover(on):
            # 호버 중에는 항상 파랑으로 강조(지금 가리키고 있다는 의미이므로
            # 보관 여부와 무관). 호버가 아닐 때는 보관된 항목이면 초록,
            # 아니면 기본 회색 테두리로 되돌아간다.
            if on:
                border, bg = COL_ACCENT, COL_HOVER_BG
            elif is_downloaded:
                border, bg = COL_DOWNLOADED, COL_DOWNLOADED_BG
            else:
                border, bg = COL_BORDER, COL_BG
            card.configure(highlightbackground=border, highlightcolor=border, bg=bg)
            inner.configure(bg=bg)
            title.configure(bg=bg)
            seller.configure(bg=bg)

        def on_enter(_e):
            _set_hover(True)

        def on_leave(_e):
            # 자식 위젯 사이를 오갈 때 발생하는 Leave 로 깜빡이지 않도록,
            # 포인터가 실제로 카드 밖으로 나갔는지 확인.
            x, y = card.winfo_pointerxy()
            w = card.winfo_containing(x, y)
            while w is not None:
                if w is card:
                    return
                w = getattr(w, "master", None)
            _set_hover(False)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

        if is_downloaded:
            _set_hover(False)  # 초기 렌더링에 보관 하이라이트 색 적용

        cached = self.thumb_refs.get(item["img"])
        if cached is not None:
            thumb.configure(image=cached, text="")
            return card

        def load_thumb():
            try:
                data = _read_image_bytes(item["img"], self.api)
                im = Image.open(io.BytesIO(data))
                im.thumbnail(THUMB_SIZE)
                tkim = ImageTk.PhotoImage(im)
                self._cache_thumb(item["img"], tkim)
                def apply():
                    if thumb.winfo_exists():
                        thumb.configure(image=tkim, text="")
                self.after(0, apply)
            except Exception:
                def fail():
                    if thumb.winfo_exists():
                        thumb.configure(text="✕", fg="#d0d0d0")
                self.after(0, fail)
        self.executor.submit(load_thumb)
        return card

    # ---------- 상세 / 다운로드 ----------
    def open_detail(self, item):
        DetailDialog(self, item)


class DetailDialog(tk.Toplevel):
    def __init__(self, master: DcconApp, item: dict):
        super().__init__(master)
        self.master_app = master
        self.item = item
        self.title(item.get("title") or "디시콘")
        self.minsize(480, 400)
        self.transient(master)
        self._place_over_parent(master, 820, 640)
        self.bind("<Escape>", lambda e: self.destroy())
        self.detail = None
        self.image_refs = []
        self.cancel_flag = threading.Event()
        self.preview_urls = []
        self.preview_cols = 0
        self.preview_canvas = None
        self.preview_inner = None
        self.preview_cache = {}   # url -> ImageTk.PhotoImage, 리사이즈 재배치 시 재다운로드 방지
        self.raw_cache = {}       # url/경로 -> 원본 bytes, 클립보드 복사용(원본 화질 필요)

        ttk.Label(self, text="불러오는 중...", padding=20).pack()
        threading.Thread(target=self._load, daemon=True).start()

    def _place_over_parent(self, master, w, h):
        """상세창을 부모(썸네일) 창 위에 중앙 정렬로 배치.

        부모 창의 화면 좌표를 기준으로만 계산한다. winfo_screenwidth/height
        는 '주 모니터' 크기만 돌려주므로, 그 값으로 클램프하면 부모가 2번
        모니터에 있을 때 상세창이 주 모니터로 끌려간다. 그래서 화면 클램프는
        하지 않고 부모 기준 상대 위치만 사용한다 → 부모와 같은 모니터에 뜬다.
        """
        try:
            master.update_idletasks()
            px, py = master.winfo_rootx(), master.winfo_rooty()
            pw, ph = master.winfo_width(), master.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.geometry(f"{w}x{h}")

    def _load(self):
        if self.item.get("is_local"):
            self._load_local()
            return
        try:
            d = self.master_app.api.get_detail(self.item["package_idx"])
            self.detail = d
            self.after(0, self._render)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("실패", str(e), parent=self))
            self.after(0, self.destroy)

    def _load_local(self):
        """내 보관함 항목: 서버 재조회 없이 폴더 안 파일을 그대로 나열."""
        try:
            folder = self.item["folder_path"]
            files = [
                f for f in os.listdir(folder)
                if f.lower().endswith(IMAGE_EXTS)
            ]
            files.sort(key=_natural_sort_key)
            urls = [os.path.join(folder, f) for f in files]
            self.detail = {
                "title": self.item["title"],
                "seller": "",
                "tags": "",
                "description": "",
                "urls": urls,
                "is_local": True,
            }
            self.after(0, self._render)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("실패", str(e), parent=self))
            self.after(0, self.destroy)

    def _render(self):
        for w in self.winfo_children():
            w.destroy()

        # 제목 파란 바 (메인 헤더와 동일 톤)
        titlebar = tb.Frame(self, bootstyle="primary")
        titlebar.pack(fill="x")
        tb.Label(titlebar, text=self.detail["title"], bootstyle="inverse-primary",
                 font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", padx=12, pady=8)

        head = ttk.Frame(self, padding=(12, 8)); head.pack(fill="x")
        ttk.Label(head, text=self.detail["seller"], foreground="#555").pack(anchor="w")
        if self.detail["tags"]:
            ttk.Label(head, text="태그: " + self.detail["tags"], foreground="#888").pack(anchor="w")
        if self.detail["description"]:
            ttk.Label(head, text=self.detail["description"], wraplength=720, foreground="#444").pack(anchor="w", pady=(4, 0))

        ttk.Separator(self).pack(fill="x", padx=10)

        # 진행 상태 + 버튼 — 내 보관함(로컬) 항목은 이미 저장된 파일이므로
        # "다운로드" 개념 자체가 없어 이 영역을 통째로 생략한다.
        self.progress = None
        if not self.detail.get("is_local"):
            bar = ttk.Frame(self, padding=(10, 4)); bar.pack(fill="x")
            self.progress = tb.Progressbar(bar, mode="determinate", bootstyle="primary")
            self.progress.pack(side="left", fill="x", expand=True)
            tb.Button(bar, text=f"전체 {len(self.detail['urls'])}개 다운로드", bootstyle="primary",
                      command=self.start_download).pack(side="left", padx=(8, 0))

        # 미리보기 그리드
        prev_frame = ttk.Frame(self, padding=10); prev_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(prev_frame, highlightthickness=0)
        vbar = ttk.Scrollbar(prev_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")
        inner = ttk.Frame(canvas)
        cwin = canvas.create_window((0, 0), window=inner, anchor="n")
        inner.bind("<Configure>", lambda e: update_scrollregion(canvas))
        canvas.bind("<Configure>", lambda e: self._on_preview_resize(e, cwin))
        bind_mousewheel(canvas)

        self.preview_canvas = canvas
        self.preview_inner = inner
        self.preview_urls = self.detail["urls"]
        self._layout_preview_grid()

    def _on_preview_resize(self, event, cwin):
        # 미리보기 그리드를 캔버스 가로 중앙으로 이동
        self.preview_canvas.coords(cwin, event.width / 2, 0)
        new_cols = calc_cols(event.width, PREVIEW_CELL_WIDTH, min_cols=1)
        if new_cols != self.preview_cols:
            self._layout_preview_grid(new_cols)

    def _layout_preview_grid(self, cols: int = None):
        if cols is None:
            width = self.preview_canvas.winfo_width()
            cols = calc_cols(width, PREVIEW_CELL_WIDTH, min_cols=1)
        self.preview_cols = cols
        for w in self.preview_inner.winfo_children():
            w.destroy()
        for i, u in enumerate(self.preview_urls):
            r, c = divmod(i, cols)
            # 테두리 카드 — 이모티콘마다 구분되는 칸
            card = tk.Frame(self.preview_inner, bg=COL_BG, bd=0, highlightthickness=1,
                            highlightbackground=COL_BORDER, highlightcolor=COL_BORDER)
            card.grid(row=r, column=c, padx=6, pady=6, sticky="n")
            box = tk.Frame(card, width=104, height=104, bg=COL_THUMB_BG)
            box.pack(padx=4, pady=4)
            box.pack_propagate(False)
            lbl = tk.Label(box, text="…", bg=COL_THUMB_BG, fg="#c4c4c4")
            lbl.pack(expand=True)

            name = "메인 이미지" if i == 0 else f"icon_{i}"
            self._wire_preview_cell(card, box, lbl, i, u, name)
            self._load_preview(u, lbl)

    def _wire_preview_cell(self, card, box, lbl, index, url, name):
        """미리보기 카드에 호버 강조 + 우클릭 다운로드 메뉴를 연결."""
        widgets = (card, box, lbl)

        def enter(_e):
            card.configure(highlightbackground=COL_ACCENT, highlightcolor=COL_ACCENT)

        def leave(_e):
            x, y = card.winfo_pointerxy()
            w = card.winfo_containing(x, y)
            while w is not None:
                if w is card:
                    return
                w = getattr(w, "master", None)
            card.configure(highlightbackground=COL_BORDER, highlightcolor=COL_BORDER)

        def popup(e):
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label=name, state="disabled")
            menu.add_separator()
            # 내 보관함(로컬) 항목은 이미 저장된 파일이므로 "다운로드" 메뉴가
            # 의미 없어 생략한다. "복사"는 온라인/로컬 모두 항상 제공.
            if not self.detail.get("is_local"):
                menu.add_command(label="다운로드",
                                 command=lambda: self._download_single(index, url, name))
            menu.add_command(label="복사",
                             command=lambda: self._copy_preview_to_clipboard(index, url))
            try:
                menu.tk_popup(e.x_root, e.y_root)
            finally:
                menu.grab_release()

        for w in widgets:
            w.configure(cursor="hand2")
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-3>", popup)

    def _download_single(self, index, url, name):
        """개별 이모티콘 1개만 저장. (전체 다운로드와 같은 폴더 규칙)"""
        if not self.detail:
            return
        title = sanitize_filename(self.detail["title"]) or "package"
        base = self.master_app.download_dir.get()
        out = os.path.join(base, title)
        os.makedirs(out, exist_ok=True)
        fallback = "main_img" if index == 0 else f"icon_{index}"
        self.master_app.set_status(f"{name} 다운로드 중...")

        def task():
            try:
                fn = self.master_app.api.download_image(url, fallback, out)
                self.master_app.after(0, self.master_app.set_status, f"저장됨: {fn}")
            except Exception as e:
                self.master_app.after(0, self.master_app.set_status, f"실패: {e}")

        threading.Thread(target=task, daemon=True).start()

    def _load_preview(self, url, label):
        cached = self.preview_cache.get(url)
        if cached is not None:
            self._apply_preview(label, cached)
            return

        def task():
            try:
                data = _read_image_bytes(url, self.master_app.api)
                # 리사이즈된 미리보기(preview_cache)와 별개로 원본 bytes를
                # 캐시해둔다 — 클립보드 복사 시 100x100로 축소된 화질이
                # 아니라 원본 화질/원본 GIF 프레임 전체가 필요하기 때문.
                self.raw_cache[url] = data
                entry = self._build_preview_entry(data)
                self.preview_cache[url] = entry
                self.after(0, lambda: self._apply_preview(label, entry))
            except Exception:
                pass
        self.master_app.executor.submit(task)

    def _build_preview_entry(self, data):
        """미리보기용 이미지 엔트리 생성.

        - 정적: ("static", PhotoImage)
        - 움짤(GIF 다중 프레임): ("anim", [PhotoImage...], [duration_ms...])
        """
        im = Image.open(io.BytesIO(data))
        animated = getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1
        if not animated:
            frame = im.convert("RGBA")
            frame.thumbnail((100, 100))
            ph = ImageTk.PhotoImage(frame)
            self.image_refs.append(ph)
            return ("static", ph)

        frames, durations = [], []
        for fr in ImageSequence.Iterator(im):
            f = fr.convert("RGBA")
            f.thumbnail((100, 100))
            ph = ImageTk.PhotoImage(f)
            self.image_refs.append(ph)
            frames.append(ph)
            # 너무 빠른 프레임은 40ms 하한으로 (일부 GIF은 duration=0)
            durations.append(max(40, int(fr.info.get("duration", 100) or 100)))
        return ("anim", frames, durations)

    def _apply_preview(self, label, entry):
        """엔트리를 라벨에 적용. 움짤이면 프레임을 순환 재생한다."""
        if not label.winfo_exists():
            return
        # 이전 애니메이션 정지 (리사이즈 재배치 등)
        job = getattr(label, "_anim_job", None)
        if job is not None:
            try:
                label.after_cancel(job)
            except Exception:
                pass
            label._anim_job = None

        if entry[0] == "static":
            label.configure(image=entry[1], text="")
            return

        frames, durations = entry[1], entry[2]

        def step(i=0):
            if not label.winfo_exists():
                return
            label.configure(image=frames[i], text="")
            nxt = (i + 1) % len(frames)
            label._anim_job = label.after(durations[i], lambda: step(nxt))

        step(0)

    def start_download(self):
        if not self.detail:
            return
        title = sanitize_filename(self.detail["title"]) or "package"
        base = self.master_app.download_dir.get()
        out = os.path.join(base, title)
        os.makedirs(out, exist_ok=True)

        urls = self.detail["urls"]
        self.progress.configure(maximum=len(urls), value=0)
        self.master_app.set_status(f'"{self.detail["title"]}" 다운로드 시작')

        def task():
            api = self.master_app.api
            done = 0; failed = []
            # 0번은 main_img, 1번부터는 icon_i
            for i, u in enumerate(urls):
                name = "main_img" if i == 0 else f"icon_{i}"
                try:
                    api.download_image(u, name, out)
                except Exception as e:
                    failed.append(i)
                done += 1
                self.after(0, lambda d=done: self.progress.configure(value=d))
                self.master_app.after(0, self.master_app.set_status, f"{done}/{len(urls)} 받는 중...")
            self.master_app.after(0, self._on_finish, out, failed)

        threading.Thread(target=task, daemon=True).start()

    def _on_finish(self, out, failed):
        self.master_app.set_status(f"완료: {out}")
        if failed:
            msg = f"일부 실패 (실패 인덱스: {failed})\n저장 위치:\n{out}\n\n폴더를 열까요?"
        else:
            msg = f"저장 완료\n{out}\n\n폴더를 열까요?"
        if messagebox.askyesno("다운로드 완료", msg, parent=self):
            self._open_folder(out)

    def _open_folder(self, path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("열기 실패", str(e), parent=self)

    def _copy_preview_to_clipboard(self, index, url_or_path):
        """이미지를 다운로드하지 않고 클립보드에 바로 복사.

        정지 이미지는 표준 이미지 포맷(CF_DIB)으로 즉시 복사한다.
        GIF는 CF_DIB로 복사하면 첫 프레임만 남고 애니메이션이 소실되므로
        (실측 확인), 파일 자체를 클립보드에 올리는 CF_HDROP을 쓴다 —
        로컬 항목은 이미 있는 파일 경로를 그대로, 온라인 항목은 원본
        bytes를 임시 폴더에 flush한 뒤 그 경로를 사용한다. CF_HDROP은
        일부 메신저(카카오톡 PC 등)가 지원하지 않을 수 있다(대상 앱의
        한계이며 우리 쪽에서 해결할 수 없음을 확인함).
        """
        self.master_app.set_status("복사 중...")
        is_local = self.detail.get("is_local", False)

        def task():
            try:
                if is_local:
                    # 로컬 파일은 이미 디스크에 있으므로 그대로 사용
                    with open(url_or_path, "rb") as f:
                        data = f.read()
                    if _is_animated_bytes(data):
                        _copy_file_as_hdrop(os.path.abspath(url_or_path))
                    else:
                        _copy_bytes_as_dib(data)
                else:
                    data = self.raw_cache.get(url_or_path)
                    if data is None:
                        data = _read_image_bytes(url_or_path, self.master_app.api)
                        self.raw_cache[url_or_path] = data
                    if _is_animated_bytes(data):
                        tmp_name = f"clip_{index}_{sanitize_filename(self.detail['title'])}.gif"
                        tmp_path = os.path.join(CLIPBOARD_TMP_DIR, tmp_name)
                        with open(tmp_path, "wb") as f:
                            f.write(data)
                        _copy_file_as_hdrop(os.path.abspath(tmp_path))
                    else:
                        _copy_bytes_as_dib(data)
                self.master_app.after(0, self.master_app.set_status, "클립보드에 복사됨")
            except Exception as e:
                self.master_app.after(0, self.master_app.set_status, f"복사 실패: {e}")

        threading.Thread(target=task, daemon=True).start()


# ---------- 진입점 ----------
if __name__ == "__main__":
    app = DcconApp()
    app.mainloop()