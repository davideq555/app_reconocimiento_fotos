# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Photo Recognition Windows build.

Build with: pyinstaller --noconfirm PhotoRecognition.spec
Produces a single dist/PhotoRecognition.exe with no console window.
"""
import sysconfig
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# ttkbootstrap ships its themes as data files that PyInstaller cannot detect.
datas, binaries, hiddenimports = collect_all('ttkbootstrap')

# ttkbootstrap renders theme elements through PIL.ImageTk, which needs the
# _imagingtk extension and Pillow's Tcl package to register 'PyImagingPhoto'.
pil_datas, pil_binaries, pil_hiddenimports = collect_all('PIL')
datas += pil_datas
binaries += pil_binaries
hiddenimports += pil_hiddenimports

# rapidocr ships its ONNX models as package data; onnxruntime and opencv carry
# native inference libraries the dependency scan can miss. Only rapidocr needs
# hidden imports: for onnxruntime/cv2 we keep datas+binaries but skip their
# collect_all hiddenimports (~200 tooling/training modules we never import)
# and cv2's Qt GUI plugins (only used by cv2.imshow).
ocr_datas, ocr_binaries, ocr_hiddenimports = collect_all('rapidocr')
datas += ocr_datas
binaries += ocr_binaries
hiddenimports += ocr_hiddenimports
for package in ('onnxruntime', 'cv2'):
    pkg_datas, pkg_binaries, _ = collect_all(package)
    datas += [entry for entry in pkg_datas if '/qt/' not in entry[0].replace('\\', '/')]
    binaries += pkg_binaries

# Standalone builds (uv, python-build-standalone) keep libtcl/libtk next to
# libpython instead of a standard lib path, so the dependency scan misses them
# and the bundled app fails with 'libtcl9.0.so: cannot open shared object'.
stdlib_lib = Path(sysconfig.get_config_var('LIBDIR') or '')
for pattern in ('libtcl*.so*', 'libtk*.so*', 'libtcl*.dylib', 'libtk*.dylib'):
    binaries += [(str(lib), '.') for lib in sorted(stdlib_lib.glob(pattern))]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='PhotoRecognition',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed exes trigger more antivirus false positives
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
