# DCcon Downloader (Python GUI)

디시인사이드 디시콘을 일괄 다운로드하는 한글 데스크톱 프로그램입니다.
[base4base/DCcon-Downloader](https://github.com/base4base/DCcon-Downloader)에서 영감을 받아 Python으로 다시 작성했으며, 원본의 GIF 다운로드 버그를 비롯한 여러 문제를 수정했습니다.

> ⚠️ 다운로드 받은 디시콘은 **개인 소장 용도로만** 사용해 주세요. 디시콘 자체의 저작권은 각 제작자에게 있습니다.

---

## 원본 대비 개선점

| 항목 | 원본 (base4base) | 이 버전 |
| --- | --- | --- |
| GIF 콘 다운로드 | ❌ ENOENT 오류 발생 | ✅ 정상 |
| 한글 검색 | ❌ URL 인코딩 누락으로 결과 부정확 | ✅ 정상 |
| 한글 파일명 | 따옴표/특수문자 처리 미흡 | ✅ Windows 금지 문자 자동 치환 |
| 저장 폴더 선택 | 텍스트 입력 | ✅ 폴더 선택 대화상자 |
| 마지막 업데이트 | 2019년 12월 | 2026년 |

원본의 핵심 버그는 `Content-Disposition` 헤더에서 파일명을 추출할 때 양쪽 따옴표(`"`)를 제거하지 않은 것입니다. 서버가 `filename="icon_31.gif"` 형식으로 응답할 때 따옴표까지 파일명에 포함되어 Windows에서 ENOENT가 발생했습니다 (Windows는 `"`를 파일명에 허용하지 않음).

---

## 빠른 시작

### Python 직접 실행 (가장 간단)

1. [Python 3.10+](https://www.python.org/downloads/) 설치 (설치 시 **"Add Python to PATH" 체크 필수**)
2. `Run.bat` (또는 `실행.bat`) 더블클릭
3. 최초 실행 시 필요한 패키지(`requests`, `beautifulsoup4`, `pillow`)가 자동 설치되고 GUI가 뜹니다.

### 단일 .exe 빌드 (Python 없이 배포)

1. `Build-exe.bat` 더블클릭
2. 1~3분 후 `dist/DCcon-Downloader.exe` 생성
3. 이 .exe 파일 하나만 있으면 Python 미설치 PC에서도 그대로 실행 가능

> ⚠️ PyInstaller로 만든 서명되지 않은 .exe는 일부 백신/SmartScreen이 오탐할 수 있습니다.
> "추가 정보 → 실행" 또는 백신 예외 처리로 우회하실 수 있습니다.

### GitHub Release로 배포 (선택)

빌드된 .exe를 GitHub Releases 페이지에 자동으로 업로드합니다:

1. `Build-exe.bat`으로 .exe를 먼저 빌드
2. `release-exe.bat` 더블클릭
3. 버전 태그(예: `v1.0.0`)와 릴리스 제목을 입력
4. 자동으로 태그 생성 + .exe 업로드 + 브라우저에서 릴리스 페이지 열기

같은 태그가 이미 있으면 기존 릴리스에 덮어쓸지 묻습니다.

---

## 사용법

상단 툴바:
- **일간 인기 / 주간 인기** — 디시인사이드 인기 TOP5
- **HOT / NEW** — 인기/신상 디시콘 목록 (페이지네이션)
- **검색** — 디시콘 이름 키워드 검색 (한글 정상 지원)
- **📁 변경** — 저장 폴더 선택 대화상자 열기
- **열기** — 저장 폴더를 탐색기로 열기

본문:
- 카드(썸네일)를 클릭하면 상세 화면 열림
- 상세 화면에서 미리보기와 일괄 다운로드 가능
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
| `tkinter` | GUI (Python 표준 라이브러리) |
| `pyinstaller` | (선택) .exe 빌드 시에만 필요 |

---

## 기술 노트

### DCInside API 엔드포인트

| 용도 | 메소드 | URL |
| --- | --- | --- |
| 일간/주간 TOP5 | GET | `https://json2.dcinside.com/json1/dccon_{day\|week}_top5.php?jsoncallback=...` |
| 인기/신상 목록 | GET | `https://dccon.dcinside.com/{hot\|new}/{page}` |
| 검색 | GET | `https://dccon.dcinside.com/{hot\|new}/{page}/title/{encoded_keyword}` |
| 패키지 상세 | POST | `https://dccon.dcinside.com/index/package_detail` (body: `package_idx=N`) |
| 이미지 | GET | `https://dcimg5.dcinside.com/dccon.php?no={path}` |

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
