# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for DCcon Downloader GUI
# 사용법: pyinstaller dccon_gui.spec

block_cipher = None

a = Analysis(
    ['dccon_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # tkinter 관련 일부 환경에서 자동 인식 안 되는 모듈 보강
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 불필요한 모듈 제외 (.exe 크기 감소)
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
    upx=True,                # UPX가 있으면 자동으로 압축
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # GUI 앱이므로 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',       # 아이콘 파일이 있으면 주석 해제
)
