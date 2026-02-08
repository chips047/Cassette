# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

if sys.platform == 'win32':
    icon_file = 'System/Icons/Icon256.ico'
elif sys.platform == 'darwin':
    icon_file = 'System/Icons/Icon256.icns'
else:
    icon_file = 'System/Icons/Icon256.png'

if icon_file and not os.path.exists(icon_file):
    icon_file = None

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
        'av.sidedata.sidedata',
        'av'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

ignore = ('libstdc++.so.6', 'libgcc_s.so.1', 'libglib-2.0.so.0')
a.binaries = [b for b in a.binaries if not any(n in os.path.basename(b[0]) for n in ignore)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Cassette',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    name='Cassette',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Cassette.app',
        icon=icon_file,
        bundle_identifier='com.cassette.app',
        info_plist={
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': 'True',
        },
    )