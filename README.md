# DCcon Downloader (Python GUI)

디시인사이드 디시콘을 일괄 다운로드하는 한글 데스크톱 프로그램입니다.
[base4base/DCcon-Downloader](https://github.com/base4base/DCcon-Downloader)에서 영감을 받아 Python으로 다시 작성했으며, 원본의 GIF 다운로드 버그를 비롯한 여러 문제를 수정했습니다.

> ⚠️ 다운로드 받은 디시콘은 **개인 소장 용도로만** 사용해 주세요. 디시콘 자체의 저작권은 각 제작자에게 있습니다.

---

## 빠른 시작

### exe로 바로 실행 (Python 설치 불필요)

1. [Releases](../../releases) 페이지에서 최신 `DCcon-Downloader.exe` 다운로드
2. 더블클릭 실행 — 설치나 압축 해제 과정 없음
3. Windows Defender/백신에서 경고가 뜰 수 있는데, PyInstaller로 빌드된 파이썬 실행 파일에서 흔한 오탐(false positive)입니다. 각 릴리스 노트에 바이러스토탈 검사 결과를 함께 남깁니다.

### Python 직접 실행 (개발/커스터마이징 시)

1. [Python 3.10+](https://www.python.org/downloads/) 설치 (설치 시 **"Add Python to PATH" 체크 필수**)
2. `dccon_gui.py` 더블클릭
3. 최초 실행 시 필요한 패키지(`requests`, `beautifulsoup4`, `pillow`, `ttkbootstrap`)가 없으면 안내가 뜹니다. `pip install requests beautifulsoup4 pillow ttkbootstrap` 후 다시 실행하세요.


---

## 원본 대비 개선점

| 항목 | 원본 (base4base) | 이 버전 |
| --- | --- | --- |
| GIF 콘 다운로드 | ❌ ENOENT 오류 발생 | ✅ 정상 |
| 한글 검색 | ❌ URL 인코딩 누락으로 결과 부정확 | ✅ 정상 |
| 한글 파일명 | 따옴표/특수문자 처리 미흡 | ✅ Windows 금지 문자 자동 치환 |
| 저장 폴더 선택 | 텍스트 입력 | ✅ 폴더 선택 대화상자 |
| 인기 디시콘 목록 | HOT 페이지(디시인사이드 개편으로 무력화됨) | ✅ 일간/주간 인기 + 신상(NEW) |
| 창 크기 대응 | 고정 레이아웃 | ✅ 창 크기에 따라 카드 열 수 자동 조정 |
| 개별 다운로드 | 전체 다운로드만 가능 | ✅ 상세창에서 이미지 우클릭 → 개별 저장 |
| 움짤 미리보기 | 정지 이미지만 표시 | ✅ GIF 애니메이션 그대로 재생 |
| 마지막 업데이트 | 2019년 12월 | 진행 중 |

원본의 핵심 버그는 `Content-Disposition` 헤더에서 파일명을 추출할 때 양쪽 따옴표(`"`를 제거하지 않은 것입니다. 서버가 `filename="icon_31.gif"` 형식으로 응답할 때 따옴표까지 파일명에 포함되어 Windows에서 ENOENT가 발생했습니다 (Windows는 `"`를 파일명에 허용하지 않음).


---

## 사용법

상단 브랜드 바:
- **저장 폴더** — 현재 저장 경로 표시, **[📁 변경]**으로 폴더 선택 대화상자 열기, **[열기]**로 탐색기에서 바로 확인

탐색·검색 줄:
- **일간 인기 / 주간 인기** — 디시인사이드 인기 TOP5
- **NEW** — 신상 디시콘 목록 (페이지네이션 지원)
- **⟳ 새로고침** (또는 `F5`) — 현재 보던 화면 다시 불러오기
- **검색** (또는 `Ctrl+F`로 검색창 포커스) — 디시콘 이름 키워드 검색 (한글 정상 지원)
- **◀ 이전 / 다음 ▶** — 페이지 이동

본문:
- 카드(썸네일)를 클릭하면 상세 화면 열림 (부모 창과 같은 모니터에 중앙 정렬로 표시)
- 상세 화면에서 각 이미지를 마우스 우클릭하면 그 이미지만 개별 저장 가능
- 움짤(GIF)은 정지 이미지가 아니라 애니메이션 그대로 미리보기 재생
- 전체 일괄 다운로드 버튼으로 한 번에 모두 저장 가능
- 저장 위치: `<저장 폴더>\<디시콘 제목>\` (예: `dccon_downloaded\말딸 만화콘 5\icon_1.png`)

---

## 기본 저장 폴더 결정 규칙

1. 프로그램이 있는 폴더의 **상위 폴더에 `dccon_downloaded/`가 이미 존재**하면 그곳을 사용 (원본 DCcon-Downloader 사용자의 기존 컬렉션과 자동 합쳐짐)
2. 그렇지 않으면 프로그램이 있는 폴더 안에 `dccon_downloaded/`를 새로 생성
3. 어느 경우든 [📁 변경] 버튼으로 언제든 다른 경로로 바꿀 수 있음

PyInstaller로 빌드된 .exe에서도 정상 동작하도록 `sys.frozen` 체크를 통해 .exe 실제 위치(`sys.executable`)를 우선 사용합니다.

---

## 의존성

| 패키지 | 용도 |
| --- | --- |
| `requests` | HTTP 요청 |
| `beautifulsoup4` | 디시콘 페이지 HTML 파싱 |
| `pillow` | 썸네일/미리보기 이미지 렌더링 |
| `ttkbootstrap` | 현대적 테마·색상 (DCinside 계열 블루) |
| `tkinter` | GUI (Python 표준 라이브러리) |

---

## 직접 exe 빌드하기

Releases에 올라온 exe를 신뢰하기 어렵거나, 소스를 수정해서 직접 빌드하고 싶다면:

```
Build-exe.bat
```

더블클릭하면 필요한 패키지(`pyinstaller` 포함)를 자동 설치하고 `dccon_gui.spec` 설정으로 빌드해 `dist\DCcon-Downloader.exe`를 생성합니다. 소스를 직접 읽고 눈으로 확인한 뒤 스스로 빌드하는 것이 실행 파일의 안전성을 가장 확실하게 검증하는 방법입니다.

---

## 기술 노트

### DCInside API 엔드포인트

| 용도 | 메소드 | URL |
| --- | --- | --- |
| 일간/주간 TOP5 | GET | `https://json2.dcinside.com/json1/dccon_{day\|week}_top5.php?jsoncallback=...` |
| 신상(NEW) 목록 | GET | `https://dccon.dcinside.com/new/{page}` |
| 검색 | GET | `https://dccon.dcinside.com/{sort}/{page}/title/{encoded_keyword}` |
| 패키지 상세 | POST | `https://dccon.dcinside.com/index/package_detail` (body: `package_idx=N`) |
| 이미지 | GET | `https://dcimg5.dcinside.com/dccon.php?no={path}` |

> `/hot/{page}` 목록 페이지는 디시인사이드 개편으로 정적 페이지네이션이 사라지고 JS 기반 TOP100 위젯으로 바뀌어, 이 앱에서는 더 이상 목록 소스로 사용하지 않습니다(검색 정렬 기준 파라미터로는 여전히 내부적으로 남아있음). 인기 디시콘은 대신 일간/주간 TOP5 API로 제공합니다.

호출 시 필수 헤더:
```
Referer: https://dccon.dcinside.com/
X-Requested-With: XMLHttpRequest
```

---

## 원본 프로젝트와의 관계

이 프로젝트는 [base4base/DCcon-Downloader](https://github.com/base4base/DCcon-Downloader)의 기능을 참고하여 Python으로 **새로 작성한 독자적인 구현**입니다. 원본의 소스 코드를 직접 포함하거나 수정하지 않았으며, 디시인사이드의 공개 API/페이지 구조를 호출하는 클라이언트를 처음부터 다시 만들었습니다.

원본 제작자 **base4base**님께 감사드립니다.

---

## 라이선스

[MIT License](./LICENSE) — 이 저장소의 모든 코드.

다운로드되는 디시콘 이미지는 각 제작자의 저작물이며 이 라이선스에 포함되지 않습니다. 개인 소장 용도로만 사용해 주세요.
