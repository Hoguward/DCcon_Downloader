# DCcon Downloader — Web

데스크톱 앱(`dccon_gui.py`)의 웹 버전. 디시인사이드 API가 CORS를 지원하지
않아 브라우저가 직접 호출할 수 없으므로, Vercel의 단일 FastAPI 앱이 대신
호출하고 CORS 헤더를 붙여 돌려주는 얇은 프록시 역할을 한다.

**배포된 프록시**: https://web-nu-taupe-90.vercel.app

## 구조

```
web/
  api/
    _dccon_api.py   데스크톱 앱의 DcconAPI를 그대로 이식(파싱 로직 원본)
    index.py        FastAPI 앱 — /api/top5, /api/list, /api/search,
                     /api/detail, /api/image 라우트 전부 이 파일 하나에 정의
  public/
    index.html      정적 프론트엔드 (GitHub Pages에 배포)
  requirements.txt
```

Vercel Python 런타임은 (2026년 8월 기준) **프로젝트당 단일 진입점**만
지원한다 — `api/*.py` 파일마다 개별 함수로 자동 라우팅되던 예전 방식은
더 이상 동작하지 않는다("No python entrypoint found" 로 배포 실패). 그래서
5개 엔드포인트를 각각 파일로 쪼개지 않고 `api/index.py` 하나의 FastAPI
앱으로 통합했다.

`_` 로 시작하는 파일은 라우트가 아닌 내부 헬퍼 모듈이다.

## 왜 이미지도 프록시를 거치나

`dcimg5.dcinside.com`은 `Referer: https://dccon.dcinside.com/` 가 정확히
일치하는 요청만 허용하고 그 외엔 403을 반환한다(실측 확인). 브라우저의
`<img src="원본URL">` 는 이 페이지 자신의 주소를 Referer로 보내므로 이미지이
전부 깨진다 — 그래서 `index.html`의 모든 이미지는 `/api/image?url=...` 를
거친다(`proxiedImage()` 헬퍼). 실제로 이 문제 때문에 첫 로컬 검증에서
썸네일이 전부 깨졌던 것을 확인하고 고쳤다.

## 로컬 개발

```bash
cd web
pip install -r requirements.txt
ALLOWED_ORIGIN=http://127.0.0.1:8080 uvicorn api.index:app --app-dir . --port 8933
```

별도 터미널에서 정적 프론트엔드도 띄운다:

```bash
cd web/public
python -m http.server 8080
```

`public/index.html` 상단 스크립트의 `window.DCCON_API_BASE` 를 설정하면
기본 프록시 주소(`API_BASE`)를 오버라이드할 수 있다(로컬 프록시를 가리키게
할 때 사용).

## 배포

1. **프록시 (Vercel)**
   ```bash
   cd web
   vercel login       # 최초 1회, 브라우저 인증 필요
   vercel deploy --prod
   ```
   배포 후 Vercel 프로젝트 설정 → Environment Variables 에 `ALLOWED_ORIGIN`을
   실제 GitHub Pages 주소(예: `https://hoguward.github.io`)로 등록하고 재배포한다.
   (`api/index.py` 가 이 값을 읽어 `Access-Control-Allow-Origin`에 반영한다.
   미설정 시 기본값은 `https://hoguward.github.io`.)

2. **프론트엔드 (GitHub Pages)**
   저장소 Settings → Pages → `web/public` 를 소스로 지정하거나, 별도 브랜치에
   `public/` 내용을 배포한다. `index.html`의 `API_BASE` 기본값이 실제 배포된
   프록시 주소(위 링크)를 가리키고 있는지 확인한다.

## 데스크톱 앱과의 관계

`api/_dccon_api.py`는 `dccon_gui.py`의 `DcconAPI` 클래스를 그대로 옮긴
것이다. 디시인사이드 페이지 구조가 개편되어 파싱이 깨지면, 두 파일을 각각
고치는 대신 이 로직을 하나로 합치는 리팩터링을 고려한다(현재는 동기화 목적의
수동 복제 상태).

## 알려진 제약 (v1)

- **내 보관함**: 로컬 폴더 스캔 개념이 없어, 다운로드에 성공한
  `package_idx`를 `localStorage`에 적립해 재방문 시 카드에 "저장됨" 표시만 한다.
- **일괄 다운로드**: zip으로 묶지 않고 이미지를 순차적으로 개별
  다운로드한다(브라우저 다운로드 다이얼로그가 여러 번 뜰 수 있음). 클라이언트
  zip 라이브러리 도입은 다음 단계.
- **클립보드 GIF 복사**: 브라우저 Clipboard API가 애니메이션 GIF를 복사하는
  경로를 제공하지 않아 미지원 — "저장"으로 대체.
