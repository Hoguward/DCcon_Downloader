"""DCcon Downloader — PyWebView 진입점.

구조:
  1) FastAPI 서버(api/index.py)를 로컬호스트의 임의 빈 포트에서 uvicorn으로
     백그라운드 스레드에 띄운다. 이 서버가 프론트엔드(public/index.html)와
     API(/api/*)를 모두 서빙한다.
  2) pywebview 창을 열어 그 로컬 서버를 보여준다.
  3) 원본 tkinter 앱에 있던 데스크톱 전용 기능(폴더 선택, 폴더 열기,
     클립보드 복사, 설정 저장/불러오기)은 DesktopBridge 클래스로 노출해
     프론트엔드 JS에서 window.pywebview.api.<메서드명>()으로 호출한다.
"""

import os
import socket
import sys
import threading

import webview

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))

import desktop


def _find_free_port() -> int:
    """127.0.0.1의 임의 빈 포트를 하나 찾아 반환.

    고정 포트를 쓰면 다른 프로그램이 먼저 그 포트를 점유했을 때 실행이
    실패한다 — OS가 배정하는 임시 포트(0번 요청 시 커널이 골라줌)를 쓰면
    이 문제 자체가 생기지 않는다.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _static_dir() -> str:
    """PyInstaller 번들(sys._MEIPASS)과 개발 실행 모두에서 public/ 폴더를
    올바르게 찾는다."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "public")


def _run_server(port: int):
    # api/index.py가 os.environ["DCCON_STATIC_DIR"]로 정적 폴더 위치를
    # 읽으므로, uvicorn을 띄우기 전에 먼저 설정한다.
    os.environ["DCCON_STATIC_DIR"] = _static_dir()
    import uvicorn
    from index import app  # api/index.py

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


class DesktopBridge:
    """pywebview js_api로 노출되는 데스크톱 전용 기능.

    프론트엔드에서 window.pywebview.api.<메서드명>(...)으로 호출한다.
    모든 메서드는 JSON 직렬화 가능한 값만 반환해야 한다(pywebview 제약).

    create_window(js_api=...)는 window 객체가 만들어지기 전에 js_api
    인스턴스를 요구하는 순환 의존이 있어, 생성자로 window를 주입하는 대신
    webview.windows[0]으로 현재 창에 접근한다(창이 하나뿐인 이 앱에서는
    항상 유효).
    """

    @property
    def _window(self) -> webview.Window:
        return webview.windows[0]

    def get_config(self) -> dict:
        return desktop.load_config()

    def save_config(self, partial: dict) -> dict:
        desktop.save_config(partial)
        return {"ok": True}

    def get_default_download_dir(self) -> str:
        return desktop.default_download_dir()

    def pick_download_dir(self) -> str | None:
        """폴더 선택 다이얼로그. 사용자가 취소하면 None 반환."""
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def open_folder(self, path: str) -> dict:
        try:
            desktop.open_folder(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def copy_image_to_clipboard(self, image_bytes_b64: str) -> dict:
        """정지 이미지를 CF_DIB로 클립보드 복사. image_bytes_b64는 base64
        인코딩된 원본 이미지 bytes(JS에서 fetch 후 base64 변환해 전달)."""
        import base64
        try:
            data = base64.b64decode(image_bytes_b64)
            desktop.copy_bytes_as_dib(data)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def copy_file_to_clipboard(self, image_bytes_b64: str, filename: str) -> dict:
        """움짤(GIF) 등 애니메이션 보존이 필요한 경우 임시 파일로 저장한
        뒤 CF_HDROP으로 복사(파일 탐색기에서 복사한 것과 동일하게 동작)."""
        import base64
        try:
            data = base64.b64decode(image_bytes_b64)
            tmp_dir = desktop.ensure_clipboard_tmp_dir()
            tmp_path = os.path.join(tmp_dir, filename)
            with open(tmp_path, "wb") as f:
                f.write(data)
            desktop.copy_file_as_hdrop(os.path.abspath(tmp_path))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def download_images(self, package_title: str, urls: list, out_dir: str) -> dict:
        """urls를 out_dir/<sanitize(package_title)>/ 에 개별 저장.

        원본 tkinter 앱과 동일하게 서버(Python) 쪽에서 직접 파일을 쓴다 —
        브라우저 다운로드 매니저를 거치지 않으므로 저장 폴더 설정이 실제로
        의미를 갖는다. api/index.py의 DcconAPI 인스턴스를 그대로 재사용해
        커넥션 풀(keep-alive)을 공유한다.
        """
        from index import api as dccon_api  # api/index.py의 전역 DcconAPI 인스턴스
        from _dccon_api import sanitize_filename

        title = sanitize_filename(package_title) or "package"
        target_dir = os.path.join(out_dir, title)
        try:
            os.makedirs(target_dir, exist_ok=True)
            saved = []
            failed = []
            for i, url in enumerate(urls):
                fallback = "main_img" if i == 0 else f"icon_{i}"
                try:
                    fn = dccon_api.download_image(url, fallback, target_dir)
                    saved.append(fn)
                except Exception:
                    failed.append(i)
            return {"ok": True, "dir": target_dir, "saved": saved, "failed": failed}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def main():
    desktop.setup_crash_logging()
    port = _find_free_port()

    server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    server_thread.start()

    config = desktop.load_config()
    geometry = config.get("window_geometry")  # "WIDTHxHEIGHT+X+Y" (원본 tkinter 형식 재사용)
    width, height = 1100, 720
    if geometry:
        try:
            size_part = geometry.split("+")[0]
            width, height = (int(v) for v in size_part.split("x"))
        except Exception:
            pass

    window = webview.create_window(
        "DCcon Downloader",
        url=f"http://127.0.0.1:{port}/",
        width=width,
        height=height,
        min_size=(900, 600),
        js_api=DesktopBridge(),
    )

    def on_closed():
        try:
            w, h = window.width, window.height
            desktop.save_config({"window_geometry": f"{w}x{h}+0+0"})
        except Exception:
            pass

    window.events.closed += on_closed

    webview.start(debug=False)


if __name__ == "__main__":
    main()
