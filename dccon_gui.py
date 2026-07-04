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
    from PIL import Image, ImageTk
except ImportError:
    _missing.append("pillow")

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
THUMB_SIZE = (150, 150)
GRID_COLS = 5           # 카드 그리드 최소/기본 열 수
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
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
                return
            widget = getattr(widget, "master", None)

    def _on_destroy(_e=None):
        alive["value"] = False

    canvas.bind_all("<MouseWheel>", _on_wheel, add="+")
    canvas.bind("<Destroy>", _on_destroy, add="+")

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


# ---------- API 래퍼 ----------
class DcconAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

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
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.maxsize(self.winfo_screenwidth(), self.winfo_screenheight())

        self.api = DcconAPI()
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.current_items = []
        self._show_pager = True
        self.thumb_refs = {}      # 카드 썸네일 ImageTk 참조 보관
        self.preview_refs = []    # 상세창 이미지 참조 보관
        self.download_dir = tk.StringVar(value=DEFAULT_DOWNLOAD_DIR)
        self.mode = tk.StringVar(value="new")        # new | search | top
        self.period = tk.StringVar(value="day")      # day | week (top용)
        self.page = 1
        self.last_page = 1
        self.last_search = ""

        self._build_ui()
        self.after(100, lambda: self.load_list("new", 1))

    # ---------- UI 구성 ----------
    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # 상단 툴바
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(side="top", fill="x")

        ttk.Button(top, text="일간 인기", command=lambda: self.load_top("day")).pack(side="left")
        ttk.Button(top, text="주간 인기", command=lambda: self.load_top("week")).pack(side="left", padx=(4, 12))

        ttk.Button(top, text="NEW", command=lambda: self.load_list("new", 1)).pack(side="left", padx=(0, 12))

        ttk.Label(top, text="검색:").pack(side="left")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.search_var, width=22)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda e: self.do_search())
        ttk.Button(top, text="찾기", command=self.do_search).pack(side="left")

        ttk.Label(top, text="  저장 폴더:").pack(side="left", padx=(20, 4))
        # 경로는 직접 편집 불가 — 반드시 [...] 버튼으로 폴더 선택 대화상자 사용
        self.dir_entry = ttk.Entry(
            top, textvariable=self.download_dir, width=36, state="readonly"
        )
        self.dir_entry.pack(side="left")
        # 폴더 선택 버튼 (Windows 탐색기 폴더 아이콘 느낌으로 강조)
        ttk.Button(top, text="📁 변경", command=self.choose_dir).pack(side="left", padx=(4, 4))
        ttk.Button(top, text="열기", command=self.open_dir).pack(side="left")

        # 현재 경로를 툴팁처럼 보여주기 위해 경로가 너무 길 때 끝부분만 보이도록
        # entry의 view를 끝으로 이동
        def _scroll_end(*_):
            try:
                self.dir_entry.xview_moveto(1.0)
            except Exception:
                pass
        self.download_dir.trace_add("write", _scroll_end)
        self.after(50, _scroll_end)

        # 페이지네이션
        nav = ttk.Frame(self, padding=(10, 0))
        nav.pack(side="top", fill="x")
        self.prev_btn = ttk.Button(nav, text="◀ 이전", command=self.prev_page)
        self.prev_btn.pack(side="left")
        self.page_lbl = ttk.Label(nav, text="1 / 1")
        self.page_lbl.pack(side="left", padx=8)
        self.next_btn = ttk.Button(nav, text="다음 ▶", command=self.next_page)
        self.next_btn.pack(side="left")
        self.title_lbl = ttk.Label(nav, text="", foreground="#666")
        self.title_lbl.pack(side="left", padx=20)

        # 메인 카드 영역 (스크롤 가능한 캔버스)
        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True, padx=10, pady=8)
        self.canvas = tk.Canvas(body, highlightthickness=0)
        vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.grid_cols = GRID_COLS
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        bind_mousewheel(self.canvas)

        # 상태바
        self.status_var = tk.StringVar(value="준비")
        ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(10, 4)).pack(side="bottom", fill="x")

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        new_cols = calc_cols(event.width, CARD_WIDTH, min_cols=1)
        if new_cols != self.grid_cols:
            self.grid_cols = new_cols
            if self.current_items:
                self._show_items(self.current_items, self._show_pager)

    # ---------- 헬퍼 ----------
    def set_status(self, msg):
        self.status_var.set(msg)
        self.update_idletasks()

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

    def load_top(self, period):
        self.mode.set("top"); self.period.set(period); self.page = 1; self.last_page = 1
        self.title_lbl.config(text=f"{'일간' if period=='day' else '주간'} 인기 디시콘")
        self.set_status("불러오는 중...")
        self.thumb_refs.clear()
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
            self.after(0, self._show_items, normalized, False)
        except Exception as e:
            self.after(0, self.set_status, f"실패: {e}")

    def load_list(self, kind, page):
        self.mode.set(kind); self.page = page
        self.title_lbl.config(text="NEW 디시콘")
        self.set_status(f"{kind.upper()} {page}페이지 불러오는 중...")
        self.thumb_refs.clear()
        self.clear_grid()
        threading.Thread(target=self._fetch_list, args=(kind, page), daemon=True).start()

    def _fetch_list(self, kind, page):
        try:
            last, items = self.api.get_list(kind, page)
            self.last_page = max(last, page)
            self.after(0, self._show_items, items, True)
        except Exception as e:
            self.after(0, self.set_status, f"실패: {e}")

    def do_search(self):
        kw = self.search_var.get().strip()
        if not kw:
            return
        self.mode.set("search"); self.last_search = kw; self.page = 1
        self.title_lbl.config(text=f'검색: "{kw}"')
        self.set_status("검색 중...")
        self.thumb_refs.clear()
        self.clear_grid()
        threading.Thread(target=self._fetch_search, args=(kw, 1), daemon=True).start()

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
            self.thumb_refs.clear()
            self.clear_grid()
            threading.Thread(target=self._fetch_search, args=(self.last_search, p), daemon=True).start()

    # ---------- 카드 렌더링 ----------
    def _show_items(self, items, show_pager):
        self.current_items = items
        self._show_pager = show_pager
        self.update_nav(show_pager)
        self.clear_grid(reset_scroll=False)
        if not items:
            ttk.Label(self.grid_frame, text="결과가 없습니다.", padding=20).grid(row=0, column=0)
            self.set_status("결과 없음")
            return
        for i, it in enumerate(items):
            r, c = divmod(i, self.grid_cols)
            card = self._make_card(self.grid_frame, it)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")
        self.set_status(f"{len(items)}개 표시")

    def _make_card(self, parent, item):
        frame = ttk.Frame(parent, padding=8, relief="solid", borderwidth=1)
        thumb = ttk.Label(frame, text="(로딩 중)")
        thumb.pack()
        title = ttk.Label(frame, text=item["title"][:18], wraplength=160, justify="center", anchor="center")
        title.pack(pady=(6, 0))
        seller = ttk.Label(frame, text=item["nick_name"][:18], foreground="#888")
        seller.pack()
        for w in (frame, thumb, title, seller):
            w.bind("<Button-1>", lambda e, it=item: self.open_detail(it))
            w.configure(cursor="hand2")

        cached = self.thumb_refs.get(item["img"])
        if cached is not None:
            thumb.configure(image=cached, text="")
            return frame

        def load_thumb():
            try:
                data = self.api.fetch_thumb(item["img"])
                im = Image.open(io.BytesIO(data))
                im.thumbnail(THUMB_SIZE)
                tkim = ImageTk.PhotoImage(im)
                self.thumb_refs[item["img"]] = tkim
                def apply():
                    if thumb.winfo_exists():
                        thumb.configure(image=tkim, text="")
                self.after(0, apply)
            except Exception:
                pass
        self.executor.submit(load_thumb)
        return frame

    # ---------- 상세 / 다운로드 ----------
    def open_detail(self, item):
        DetailDialog(self, item)


class DetailDialog(tk.Toplevel):
    def __init__(self, master: DcconApp, item: dict):
        super().__init__(master)
        self.master_app = master
        self.item = item
        self.title(item.get("title") or "디시콘")
        self.geometry("820x640")
        self.minsize(480, 400)
        self.transient(master)
        self.detail = None
        self.image_refs = []
        self.cancel_flag = threading.Event()
        self.preview_urls = []
        self.preview_cols = 0
        self.preview_canvas = None
        self.preview_inner = None
        self.preview_cache = {}   # url -> ImageTk.PhotoImage, 리사이즈 재배치 시 재다운로드 방지

        ttk.Label(self, text="불러오는 중...", padding=20).pack()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            d = self.master_app.api.get_detail(self.item["package_idx"])
            self.detail = d
            self.after(0, self._render)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("실패", str(e), parent=self))
            self.after(0, self.destroy)

    def _render(self):
        for w in self.winfo_children():
            w.destroy()

        head = ttk.Frame(self, padding=10); head.pack(fill="x")
        ttk.Label(head, text=self.detail["title"], font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(head, text=self.detail["seller"], foreground="#555").pack(anchor="w")
        if self.detail["tags"]:
            ttk.Label(head, text="태그: " + self.detail["tags"], foreground="#888").pack(anchor="w")
        if self.detail["description"]:
            ttk.Label(head, text=self.detail["description"], wraplength=720, foreground="#444").pack(anchor="w", pady=(4, 0))

        ttk.Separator(self).pack(fill="x", padx=10)

        # 진행 상태 + 버튼
        bar = ttk.Frame(self, padding=(10, 4)); bar.pack(fill="x")
        self.progress = ttk.Progressbar(bar, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text=f"전체 {len(self.detail['urls'])}개 다운로드", command=self.start_download).pack(side="left", padx=(8, 0))

        # 미리보기 그리드
        prev_frame = ttk.Frame(self, padding=10); prev_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(prev_frame, highlightthickness=0)
        vbar = ttk.Scrollbar(prev_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")
        inner = ttk.Frame(canvas)
        cwin = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: self._on_preview_resize(e, cwin))
        bind_mousewheel(canvas)

        self.preview_canvas = canvas
        self.preview_inner = inner
        self.preview_urls = self.detail["urls"]
        self._layout_preview_grid()

    def _on_preview_resize(self, event, cwin):
        self.preview_canvas.itemconfig(cwin, width=event.width)
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
            cell = ttk.Frame(self.preview_inner, padding=4)
            cell.grid(row=r, column=c, sticky="n")
            lbl = ttk.Label(cell, text=f"#{i}")
            lbl.pack()
            self._load_preview(u, lbl)

    def _load_preview(self, url, label):
        cached = self.preview_cache.get(url)
        if cached is not None:
            label.configure(image=cached, text="")
            return

        def task():
            try:
                data = self.master_app.api.fetch_thumb(url)
                im = Image.open(io.BytesIO(data))
                im.thumbnail((100, 100))
                tkim = ImageTk.PhotoImage(im)
                self.image_refs.append(tkim)
                self.preview_cache[url] = tkim
                self.after(0, lambda: label.winfo_exists() and label.configure(image=tkim, text=""))
            except Exception:
                pass
        self.master_app.executor.submit(task)

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
        if failed:
            messagebox.showwarning("일부 실패",
                f"실패한 인덱스: {failed}\n저장 위치: {out}", parent=self)
        else:
            messagebox.showinfo("완료", f"{out}\n으로 저장되었습니다.", parent=self)
        self.master_app.set_status(f"완료: {out}")


# ---------- 진입점 ----------
if __name__ == "__main__":
    app = DcconApp()
    app.mainloop()