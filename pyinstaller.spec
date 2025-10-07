"""Spec simplificado: solo modo visual (PyAutoGUI).

Build:
    pyinstaller --clean --onefile --name t3bot pyinstaller.spec

Salida: dist/t3bot(.exe)
"""

block_cipher = None

a = Analysis(
    ['src/scraper/cli.py'],
    pathex=['.'],
    binaries=[],
    datas=[('windows/README_WINDOWS.md', 'windows'), ('windows/run_t3bot.bat', 'windows')],
    hiddenimports=['pyautogui', 'PIL', 'pyscreeze'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='t3bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
