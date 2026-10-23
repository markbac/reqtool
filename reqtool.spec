# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None

src_dir = Path("src/reqtool").resolve()
defaults_dir = src_dir / "defaults"
ui_dist_dir = src_dir / "ui" / "dist"

datas = []
if defaults_dir.exists():
    datas.append((str(defaults_dir), "reqtool/defaults"))
if ui_dist_dir.exists():
    datas.append((str(ui_dist_dir), "reqtool/ui/dist"))

hiddenimports = [
    'reqtool',
    'reqtool.main',
    'reqtool.cli',
    'reqtool.api',
    'reqtool.auth',
    'reqtool.store',
    'reqtool.validation',
    'reqtool.exports',
    'reqtool.fileio',
    'reqtool.models',
    'reqtool.routers',
    'reqtool.routers.auth',
    'reqtool.routers.system',
    'reqtool.routers.requirements',
    'reqtool.routers.principles',
    'reqtool.routers.tbds',
    'reqtool.routers.modules',
    'reqtool.routers.comments',
    'reqtool.routers.attachments',
    'reqtool.routers.analysis',
    'reqtool.routers.exports',
    'reqtool.routers.git_ops',
    'reqtool.routers.imports',
    'reqtool.routers.ws',
    'reqtool.stores',
    'reqtool.stores.attachment_store',
    'reqtool.stores.comment_store',
    'reqtool.stores.hierarchy_store',
    'reqtool.logconfig',
    'ctxlogkit',
    'ctxlogkit.log_setup',
    'colorlog',
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
]

# 1. reqtool-web executable (auto-launches browser web interface)
a_web = Analysis(
    ['src/reqtool/__main_web__.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_web = PYZ(a_web.pure, a_web.zipped_data, cipher=block_cipher)

exe_web = EXE(
    pyz_web,
    a_web.scripts,
    a_web.binaries,
    a_web.zipfiles,
    a_web.datas,
    [],
    name='reqtool-web',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 2. reqtool-app executable (auto-launches desktop app interface)
a_app = Analysis(
    ['src/reqtool/__main_app__.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_app = PYZ(a_app.pure, a_app.zipped_data, cipher=block_cipher)

exe_app = EXE(
    pyz_app,
    a_app.scripts,
    a_app.binaries,
    a_app.zipfiles,
    a_app.datas,
    [],
    name='reqtool-app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 3. reqtool-server executable (auto-launches central multi-user backend server on 0.0.0.0:8765)
a_server = Analysis(
    ['src/reqtool/__main_server__.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_server = PYZ(a_server.pure, a_server.zipped_data, cipher=block_cipher)

exe_server = EXE(
    pyz_server,
    a_server.scripts,
    a_server.binaries,
    a_server.zipfiles,
    a_server.datas,
    [],
    name='reqtool-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 4. reqtool-client executable (auto-launches desktop client application interface)
a_client = Analysis(
    ['src/reqtool/__main_client__.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_client = PYZ(a_client.pure, a_client.zipped_data, cipher=block_cipher)

exe_client = EXE(
    pyz_client,
    a_client.scripts,
    a_client.binaries,
    a_client.zipfiles,
    a_client.datas,
    [],
    name='reqtool-client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 5. reqtool CLI executable
a_cli = Analysis(
    ['src/reqtool/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    [],
    name='reqtool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
