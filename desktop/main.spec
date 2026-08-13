# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for DCcon Downloader (PyWebView 버전)
# 사용법: pyinstaller main.spec

block_cipher = None

a = Analysis(
    ['main.py'],
    # api/ 를 pathex에 추가해 main.py가 하는 sys.path.insert(0, ".../api")와
    # 동일한 효과를 PyInstaller의 모듈 탐색 단계에서도 얻는다 — 이렇게 해야
    # `from index import app`(main.py 내부)이 빌드 시점에 정적으로 발견되어
    # index.py/_dccon_api.py가 pyz 안에 소스로 포함된다.
    pathex=['api'],
    binaries=[],
    datas=[
        # public/(HTML/JS)은 순수 데이터라 datas로 포함해야 한다. main.py의
        # _static_dir()가 sys._MEIPASS/public 을 참조하므로 대상 경로도
        # 'public'으로 맞춘다.
        ('public', 'public'),
    ],
    hiddenimports=[
        # pywebview는 플랫폼별 백엔드를 런타임에 동적으로 import하므로
        # PyInstaller의 정적 분석이 놓치기 쉽다. Windows에서는 EdgeChromium
        # (WebView2, pythonnet 기반)이 기본 백엔드다.
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
        # uvicorn/fastapi도 일부 하위 모듈이 동적 import라 보강 필요
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # 클립보드 이미지/파일 복사 기능(win32clipboard)에 필요
        'win32clipboard',
        'win32con',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'pandas', 'matplotlib', 'scipy',
        'IPython', 'jupyter', 'pytest', 'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DCcon-Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 압축은 실행 파일을 스스로 압축 해제하는 형태로 바꾸는데, 이
    # 패턴 자체가 일부 백신의 휴리스틱/ML 탐지(Wacatac.B!ml 등)를
    # 자극하는 것으로 알려져 있다 — 꺼서 오탐률을 낮춘다(실측 비교 예정).
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # GUI 앱이므로 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
