# -*- coding: utf-8 -*-
"""
PROKLADKA Houdini Installer — установка через Houdini Packages (как SideFX Labs).

Запуск (любой из способов):
  1. Головной режим:
       "C:/Program Files/Side Effects Software/Houdini 20.5.278/bin/hython.exe" install_prokladka_hou.py
  2. Python Source Editor в GUI:
       exec(open(r'<путь>/install_prokladka_hou.py').read())

Что делает:
  1. Копирует package/prokladka/houdini → <pref>/prokladka/houdini
  2. Создаёт <pref>/packages/prokladka.json (Houdini Package)
  3. Чистит legacy-установку scripts/prokladka/ (если была)

После установки: запусти Houdini -> '+' в строке вкладок полок ->
галка PROKLADKA (один раз, Houdini запомнит).
"""
import os
import json
import shutil

try:
    import hou
except ImportError:
    hou = None  # допускаем запуск без hou (не должен случиться — hython его даёт)


# ── Конфигурация ─────────────────────────────────────────────────────────────

def _pref_dir():
    """Реальная папка префов Houdini ($HOUDINI_USER_PREF_DIR).

    hou.getenv() — авторитетный источник: Houdini вычисляет папку сам
    (HOME → Documents\houdiniXX.Y на Windows 20.5+) и ПЕРЕЗАПИСЫВАЕТ
    os.environ при старте, поэтому env-переменная врёт.
    """
    if hou is not None:
        try:
            v = hou.getenv('HOUDINI_USER_PREF_DIR')
            if v:
                return v
        except Exception:
            pass
    env = os.environ.get('HOUDINI_USER_PREF_DIR')
    if env:
        return env
    return os.path.join(os.path.expanduser('~'), 'houdini20.5')


# Источник: package/ рядом с этим файлом
try:
    _SRC = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # exec() контекст — искать по известным путям
    _SRC = None
    for candidate in (
        r'D:\AI\ZCode\Project\prokladka\out\houdini',
        os.path.join(os.path.expanduser('~'), 'Downloads'),
    ):
        if os.path.isfile(os.path.join(candidate, 'install_prokladka_hou.py')):
            _SRC = candidate
            break

PACKAGE_SRC = os.path.join(_SRC, 'package', 'prokladka', 'houdini') if _SRC else None

PREF_DIR = _pref_dir()
DEST_DIR = os.path.join(PREF_DIR, 'prokladka', 'houdini')
PACKAGES_DIR = os.path.join(PREF_DIR, 'packages')
JSON_PATH = os.path.join(PACKAGES_DIR, 'prokladka.json')
LEGACY_SCRIPTS = os.path.join(PREF_DIR, 'scripts', 'prokladka')


# ── Шаги ─────────────────────────────────────────────────────────────────────

def step_copy_package():
    """Копировать package/prokladka/houdini → <pref>/prokladka/houdini."""
    if not PACKAGE_SRC or not os.path.isdir(PACKAGE_SRC):
        return False, "Package source not found: {}".format(PACKAGE_SRC)
    shutil.copytree(PACKAGE_SRC, DEST_DIR, dirs_exist_ok=True)
    n = sum(len(f) for _, _, f in os.walk(DEST_DIR))
    return True, "{} files -> {}".format(n, DEST_DIR)


def step_write_package_json():
    """Создать packages/prokladka.json."""
    os.makedirs(PACKAGES_DIR, exist_ok=True)
    data = {
        "env": [
            {"PROKLADKA": DEST_DIR.replace('\\', '/')}
        ],
        "path": ["$PROKLADKA"],
    }
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return True, JSON_PATH


def step_cleanup_legacy():
    """Удалить legacy-установку scripts/prokladka/ (до-packages схема)."""
    marker = os.path.join(LEGACY_SCRIPTS, 'prokladka_hou.py')
    if os.path.isfile(marker):
        shutil.rmtree(LEGACY_SCRIPTS)
        return True, "removed {}".format(LEGACY_SCRIPTS)
    return True, "no legacy install"


def main():
    print("=" * 60)
    print("PROKLADKA Houdini Installer (packages, hython-compatible)")
    print("=" * 60)
    print("Pref dir: {}".format(PREF_DIR))

    steps = (
        ("Package copy", step_copy_package),
        ("Package json", step_write_package_json),
        ("Legacy cleanup", step_cleanup_legacy),
    )
    failed = False
    for name, fn in steps:
        try:
            result, msg = fn()
        except Exception as e:
            result, msg = False, repr(e)
        if result is False:
            failed = True
        status = "OK  " if result else ("SKIP" if result is None else "FAIL")
        print("[{}] {}: {}".format(status, name, msg))

    print()
    if failed:
        print("INSTALLATION FAILED — исправь ошибку выше и перезапусти.")
    else:
        print("INSTALLATION COMPLETE")
        print()
        print("Дальше: запусти/перезапусти Houdini ->")
        print("  '+' в строке вкладок полок -> галка PROKLADKA (один раз).")


if __name__ == '__main__':
    main()
elif '__file__' not in dir():
    # exec() контекст — авто-запуск
    main()
