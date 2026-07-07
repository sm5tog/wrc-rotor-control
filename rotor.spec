# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['rotor_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SM5K-Rotor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['compass.ico'],
)

import shutil, os
_dst = r"C:\claude\aktiv\rotor"
os.makedirs(_dst, exist_ok=True)
shutil.copy(os.path.join(DISTPATH, "SM5K-Rotor.exe"), os.path.join(_dst, "SM5K-Rotor.exe"))
