# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None
icon_file = None

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
    pathex = [],
    binaries = [],
    datas = [
        ('version', '.'),
        ('System', 'System'),
    ],
    hiddenimports = [
        'OpenGL',
        'OpenGL.platform.egl',
        'av.sidedata.sidedata',
        'av'
    ],
    hookspath = [],
    hooksconfig = {},
    runtime_hooks = [],
    excludes = [],
    win_no_prefer_redirects = False,
    win_private_assemblies = False,
    cipher = block_cipher,
    noarchive = False,
)

ignore = ('libstdc++.so.6', 'libgcc_s.so.1', 'libglib-2.0.so.0')
filtered_binaries = []

for b in a.binaries:
    names = []
    if isinstance(b, (list, tuple)):
        if b and b[0]:
            names.append(os.path.basename(b[0]))
        
        if len(b) > 1 and b[1]:
            names.append(os.path.basename(b[1]))
    
    else:
        names.append(os.path.basename(b))
    
    if not any(n in ignore for n in names):
        filtered_binaries.append(b)

a.binaries = filtered_binaries

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries = True,
    name = 'Cassette',
    debug = False,
    bootloader_ignore_signals = False,
    strip = False,
    upx = True,
    console = False,
    disable_windowed_traceback = False,
    argv_emulation = False,
    target_arch = None,
    codesign_identity = None,
    entitlements_file = None,
    icon = icon_file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip = False,
    upx = True,
    upx_exclude = [],
    name = 'Cassette',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name = 'Cassette.app',
        icon = icon_file,
        bundle_identifier = None,
    )