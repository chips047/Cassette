# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None
is_darwin = sys.platform == 'darwin'

if sys.platform == 'win32':
    icon_file = 'System/Icons/Icon256.ico'

elif is_darwin:
    icon_file = 'System/Icons/Icon256.icns'

else:
    icon_file = 'System/Icons/Icon256.png'

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
    upx=True,
    console=False,
    icon=icon_file,
)

if not is_darwin:
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
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