# -*- mode: python ; coding: utf-8 -*-

# Keep the spec portable: all inputs below are tracked paths relative to this
# file.  The old version embedded a developer's Windows checkout and pointed
# at resources that no longer exist in the repository.
from pathlib import Path

# PyInstaller executes a spec in a dedicated namespace; __file__ is not a
# reliable builtin there. SPECPATH is the documented directory of this spec.
ROOT = Path(SPECPATH).resolve()
add_files = [
    (str(ROOT / "app" / "data"), "app/data"),
    (str(ROOT / "app" / "ImageBox"), "app/ImageBox"),
    (str(ROOT / "app" / "resources"), "app/resources"),
    # pyecharts resolves these assets from its package namespace at runtime;
    # retaining the original destination avoids a valid build with missing
    # chart templates/data.
    (str(ROOT / "resource" / "datasets"), "pyecharts/datasets"),
    (str(ROOT / "resource" / "render" / "templates"), "pyecharts/render/templates"),
]
block_cipher = None

#("D:\\Project\\Python\\WeChatMsg\\sqlcipher-3.0.1",'.\\sqlcipher-3.0.1')

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=add_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'app' / 'data' / 'icon.png')
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main',
)
