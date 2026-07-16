# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None
is_darwin = sys.platform == 'darwin'

if sys.platform == 'win32':
    icon_file = 'System/Assets/Icons/Cassette/AppIcon.ico'

elif is_darwin:
    icon_file = 'System/Assets/Icons/Cassette/AppIcon.icns'

else:
    icon_file = 'System/Assets/Icons/Cassette/AppIcon/Icon256.png'

a = Analysis(
    ['Cassette.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('version', '.'),
        ('System', 'System'),
    ],
    hiddenimports=[
        'OpenGL',
        'OpenGL.platform.egl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6.QtSql',
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtMultimedia',
        'PyQt6.QtTest',
        'PyQt6.QtPdf',
        
        'tkinter',
        'sqlite3',
        'distutils',
        
        'numpy.tests',

        'PyQt6.QtWebEngine',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtBluetooth',
        'PyQt6.QtDBus',
        'PyQt6.QtNfc',
        'PyQt6.QtPositioning',
        'PyQt6.QtSensors',
        'PyQt6.QtSvg',
        'PyQt6.QtXml',
        'PyQt6.QtWebSockets',
        'PyQt6.QtPrintSupport',
        'PyQt6.QtTextToSpeech',
        'PyQt6.QtNetworkAuth',

        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'PIL',

        'unittest',
        'pydoc',
        'curses',
        'lib2to3',
        'xmlrpc',
        'http.server',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

binaries_clean = []
seen_basenames = set()

for name, path, typecode in a.binaries:
    if "PyQt6" in name or "numpy" in name:
        binaries_clean.append((name, path, typecode))
        seen_basenames.add(os.path.basename(name))

for name, path, typecode in a.binaries:
    basename = os.path.basename(name)
    if basename not in seen_basenames:
        binaries_clean.append((name, path, typecode))
        seen_basenames.add(basename)

a.binaries = binaries_clean

if sys.platform == "linux":
    ignore = ('libstdc++.so.6',)
    a.binaries = [b for b in a.binaries if not any(n in os.path.basename(b[0]) for n in ignore)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries if is_darwin else [],
    a.zipfiles if is_darwin else [],
    a.datas if is_darwin else [],
    exclude_binaries=not is_darwin,
    name='Cassette',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_file
)

if not is_darwin:
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=True,
        upx=False,
        name='Cassette',
    )

if is_darwin:
    app = BUNDLE(
        exe,
        name='Cassette.app',
        icon=icon_file,
        bundle_identifier='com.cassette.app',
        info_plist={
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': 'True',
        },
    )