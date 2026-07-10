# 버전 관리 규칙

이 프로젝트는 [Semantic Versioning](https://semver.org/lang/ko/) (`MAJOR.MINOR.PATCH`)을 따릅니다.

## 버전 올리는 기준

| 항목 | 의미 | 예시 |
| --- | --- | --- |
| MAJOR | 기존 사용법이 깨지는 큰 변경 (저장 폴더 구조 변경, 설정 파일 비호환 등) | 1.x.x → 2.0.0 |
| MINOR | 새 기능 추가 (기존 기능은 그대로 동작) | 1.0.x → 1.1.0 |
| PATCH | 버그 수정, UI 다듬기, 성능 개선 등 기능 변화 없는 수정 | 1.0.0 → 1.0.1 |

디시인사이드 사이트 개편으로 인한 대응(파싱 로직 수정 등)은 사용자 입장에서 "고장난 걸 고친 것"이므로 PATCH로 취급합니다.

## Release 절차

1. `dccon_gui.py` 등 소스 수정 후 커밋 & `git push`
2. `Build-exe.bat` 실행 (또는 `python -m PyInstaller dccon_gui.spec --noconfirm`)로 `dist/DCcon-Downloader.exe` 생성
3. 실행해서 정상 동작 확인 (스크린샷 또는 직접 구동)
4. 바이러스토탈 등에서 안전성 확인 (선택, 권장)
5. `gh release create vX.Y.Z dist/DCcon-Downloader.exe --title "..." --notes "..."` 로 GitHub Release 게시
   - Release 노트에는 SHA-256 해시와 이전 버전 대비 변경 사항을 명시
6. 오래된 Release는 삭제하지 않고 유지 (구버전이 필요한 사용자 대비)

## 버전 이력

| 버전 | 날짜 | 요약 |
| --- | --- | --- |
| v1.0.0 | 2026-05-28 | 최초 배포 |
| v1.0.1 | 2026-07-11 | 저장폴더 UI 가시성, 테마 버그(주요 버튼 텍스트 안 보이던 문제), 카드 제목 한글 볼드 렌더링 수정 |
