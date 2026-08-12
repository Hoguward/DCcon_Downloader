"""데스크톱 전용 기능 — 설정 영속화, 클립보드 복사, 폴더 다이얼로그/열기.

원본 tkinter 앱(dccon_gui.py)에서 GUI 프레임워크와 무관한 순수 로직만
그대로 옮겨왔다. Tk에 의존하는 부분(filedialog.askdirectory 등)만
pywebview의 대응 API로 교체했다.
"""

import io
import json
import logging
import os
import re
import shutil
import struct
import sys
import tempfile
import threading
import traceback

from PIL import Image

try:
    import win32clipboard
    import win32con  # noqa: F401  (미사용이지만 win32clipboard와 함께 필요)
except ImportError:
    win32clipboard = None


def app_dir() -> str:
    """프로그램(스크립트 또는 .exe)이 실제 위치한 폴더를 반환.

    - Python 직접 실행: main.py 가 있는 폴더
    - PyInstaller .exe: DCcon-Downloader.exe 가 있는 폴더
        (sys.frozen 이 True 이면 sys.executable 의 디렉토리를 사용.
         __file__ 은 임시 압축해제 폴더를 가리키므로 부적절.)
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def config_dir() -> str:
    """config.json/crash.log 등 사용자별 영속 설정을 저장할 안정적인 폴더.

    exe를 어디로 옮기거나 새 버전으로 교체해도 항상 같은 위치를 가리키도록
    Windows 사용자 프로필 하위 APPDATA를 쓴다. APPDATA가 없는 비정상
    환경에서는 app_dir()로 폴백한다. (원본 tkinter 버전과 동일한 정책 —
    같은 %APPDATA%\\DCconDownloader\\ 를 공유하도록 앱 이름도 그대로 유지.)
    """
    base = os.getenv("APPDATA") or app_dir()
    path = os.path.join(base, "DCconDownloader")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        return app_dir()
    return path


def default_download_dir() -> str:
    """기본 다운로드 폴더를 결정.

    우선순위:
      1) <앱폴더>/../dccon_downloaded 가 이미 존재 → 그걸 사용
         (원본 tkinter 버전과 같은 곳을 가리켜 기존 콘 컬렉션과 합쳐짐)
      2) <앱폴더>/dccon_downloaded 를 사용
    """
    base = app_dir()
    parent_loc = os.path.abspath(os.path.join(base, "..", "dccon_downloaded"))
    if os.path.isdir(parent_loc):
        return parent_loc
    return os.path.abspath(os.path.join(base, "dccon_downloaded"))


CONFIG_PATH = os.path.join(config_dir(), "config.json")
CLIPBOARD_TMP_DIR = os.path.join(tempfile.gettempdir(), "dccon_clipboard_tmp")


def load_config() -> dict:
    """config.json을 읽어 dict로 반환. 없거나 손상됐으면 빈 dict."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(partial: dict) -> None:
    """기존 config.json에 partial을 병합해 저장. 실패해도 조용히 무시."""
    try:
        data = load_config()
        data.update(partial)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def setup_crash_logging():
    """예기치 않은 예외(메인 스레드/워커 스레드 공통)를 <설정폴더>/crash.log
    에 남긴다. tkinter report_callback_exception 훅은 없다(더 이상 tkinter를
    쓰지 않으므로) — 대신 pywebview 콜백 예외도 sys.excepthook/threading.
    excepthook 두 훅으로 충분히 잡힌다.
    """
    log_path = os.path.join(config_dir(), "crash.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.ERROR,
        format="%(asctime)s %(message)s",
        encoding="utf-8",
    )

    def log_exception(exc_type, exc_value, exc_tb):
        logging.error("Unhandled exception:\n%s",
                       "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    sys.excepthook = log_exception

    def thread_hook(args):
        log_exception(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_hook


def ensure_clipboard_tmp_dir() -> str:
    """CF_HDROP용 임시 폴더를 준비. 이전 세션 잔여물은 베스트 에포트로 정리."""
    try:
        shutil.rmtree(CLIPBOARD_TMP_DIR, ignore_errors=True)
    except Exception:
        pass
    os.makedirs(CLIPBOARD_TMP_DIR, exist_ok=True)
    return CLIPBOARD_TMP_DIR


def copy_bytes_as_dib(image_bytes: bytes) -> None:
    """정지 이미지 bytes를 Windows 클립보드에 CF_DIB(표준 이미지)로 복사.

    BMP로 저장한 뒤 14바이트 파일헤더(BITMAPFILEHEADER)를 제거하면
    남는 것이 곧 DIB(BITMAPINFOHEADER + 픽셀 데이터)다. CF_DIB는 알파
    채널을 지원하지 않으므로 RGB로 변환한다.
    """
    if win32clipboard is None:
        raise RuntimeError("win32clipboard is not available on this platform")
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


def copy_file_as_hdrop(file_path: str) -> None:
    """파일 자체를 Windows 클립보드에 CF_HDROP(파일 복사)으로 올린다.

    표준 이미지 포맷(CF_DIB)은 정지 프레임 한 장만 담을 수 있어 GIF
    애니메이션이 소실된다. CF_HDROP은 "파일 탐색기에서 파일을 복사한
    것"과 동일하게 동작해 대상 앱이 원본 파일을 그대로 읽으므로
    애니메이션이 보존된다. DROPFILES 구조체를 수동으로 조립해야 pywin32의
    SetClipboardData(CF_HDROP, ...)에 넘길 수 있다.
    """
    if win32clipboard is None:
        raise RuntimeError("win32clipboard is not available on this platform")
    file_list = (file_path + "\0").encode("utf-16-le") + "\0".encode("utf-16-le")
    header = struct.pack("<LLLLL", 20, 0, 0, 0, 1)  # DROPFILES: pFiles, pt, fNC, fWide
    data = header + file_list
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_HDROP, data)
    finally:
        win32clipboard.CloseClipboard()


def open_folder(path: str) -> None:
    """탐색기로 폴더를 연다."""
    os.startfile(path)  # type: ignore[attr-defined]


# ---------- 내 보관함 (로컬 저장 폴더 스캔) ----------
# 원본 tkinter 앱(dccon_gui.py)의 _scan_local_packages/_natural_sort_key를
# 그대로 이식 — GUI 프레임워크와 무관한 순수 로직이라 변경 없이 재사용된다.
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_NATSORT_RE = re.compile(r"(\d+)")


def natural_sort_key(filename: str):
    """'icon_10'이 'icon_2'보다 앞에 오는 사전식 정렬 오류를 막는 정렬 키."""
    return [int(p) if p.isdigit() else p.lower() for p in _NATSORT_RE.split(filename)]


def scan_local_packages(download_dir: str) -> list:
    """저장 폴더 하위의 <제목>/icon_*.* 구조를 스캔해 카드용 item 리스트로 변환.

    각 하위 폴더 = 다운로드된 디시콘 패키지 하나. 대표 썸네일은 폴더 안에
    main_img.*(다운로드 시 저장되는 디시인사이드 원본 대표 이미지, 원본
    tkinter 앱 download_image의 fallback_name="main_img")가 있으면 그것을
    우선 쓴다 — 실측 확인 결과 자연 정렬로는 "icon_1"이 "main_img"보다
    앞서(문자 비교상 'i' < 'm') 항상 icon_1이 골라졌는데, main_img.jpg가
    엄연히 진짜 대표 이미지로 저장되어 있어 그쪽이 더 정확한 썸네일이다.
    main_img가 없는(예: 구버전에서 받은) 폴더는 자연 정렬 첫 번째로
    폴백한다. 제목(폴더명) 가나다순 정렬로 반환한다. img 필드는 원격
    URL이 아니라 로컬 절대 경로이므로, 프론트엔드는 이 경로를
    /api/local_image?path=... 프록시로 감싸서 표시해야 한다(브라우저가
    file:// 를 직접 열지 못하는 보안 제약 때문).
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
        images.sort(key=natural_sort_key)
        main_img = next((f for f in images if f.lower().startswith("main_img")), None)
        thumb_path = os.path.join(entry.path, main_img or images[0])
        items.append({
            "title": entry.name,
            "nick_name": "",
            "img": thumb_path,
            "package_idx": "",
            "is_local": True,
            "folder_path": entry.path,
        })
    items.sort(key=lambda it: natural_sort_key(it["title"]))
    return items


def list_local_package_files(folder_path: str) -> list:
    """내 보관함 항목 하나(폴더)의 이미지 파일 절대 경로 목록. 자연 정렬."""
    files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(IMAGE_EXTS)
    ]
    files.sort(key=natural_sort_key)
    return [os.path.join(folder_path, f) for f in files]
