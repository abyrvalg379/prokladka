# -*- coding: utf-8 -*-
"""
PROKLADKA Houdini Installer — установка через Houdini Packages (как SideFX Labs).

Запуск (любой из способов):
  1. Головной режим (Houdini ЗАКРЫТ):
       "C:/Program Files/Side Effects Software/Houdini 20.5.278/bin/hython.exe" install_prokladka_hou.py
     → полная установка, включая видимость полки. Ноль ручных действий.
  2. Python Source Editor в GUI:
       exec(open(r'<путь>/install_prokladka_hou.py').read())
     → установка файлов; видимость полки — галка в '+' меню (один раз).

Что делает:
  1. Копирует package/prokladka/houdini → <pref>/prokladka/houdini
  2. Создаёт <pref>/packages/prokladka.json (Houdini Package)
  3. Если Houdini закрыт — добавляет полку в видимый набор (default.shelf)
  4. Чистит legacy-установку scripts/prokladka/ (если была)

После установки: перезапустить Houdini → вкладка PROKLADKA на полке.
Полка и кнопка переживают любые обновления — грузятся из toolbar XML.
"""
import os
import json
import shutil
import subprocess

try:
    import hou
except ImportError:
    hou = None  # допускаем запуск без hou (не должен случиться — hython его даёт)


# ── Конфигурация ─────────────────────────────────────────────────────────────

def _pref_dir():
    """Реальная папка префов Houdini ($HOUDINI_USER_PREF_DIR).

    Не всегда ~/houdiniXX.Y: на основном ПК это Documents/houdini20.5.
    """
    env = os.environ.get('HOUDINI_USER_PREF_DIR')
    if env:
        return env
    if hou is not None:
        try:
            v = hou.getenv('HOUDINI_USER_PREF_DIR')
            if v:
                return v
        except Exception:
            pass
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
DEFAULT_SHELF = os.path.join(PREF_DIR, 'toolbar', 'default.shelf')
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


def houdini_gui_running():
    """Запущен ли GUI Houdini (houdini.exe)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq houdini.exe"],
            capture_output=True, timeout=15).stdout
        # Русская Windows отдаёт cp866 — декодируем с ignore, имя процесса ASCII
        return "houdini.exe" in out.decode("utf-8", "ignore")
    except Exception:
        return True  # не смогли проверить — считаем что запущен (безопаснее)


def step_shelf_visibility():
    """
    Добавить полку PROKLADKA в видимый набор (default.shelf).

    Правка возможна ТОЛЬКО при закрытом GUI — иначе Houdini перезапишет
    файл из памяти при выходе (как Maya с shelf_Custom.mel).
    """
    if houdini_gui_running():
        return None, ("Houdini GUI is running — skip default.shelf edit. "
                      "После старта: '+' на панели полок -> галка PROKLADKA (один раз)")
    if not os.path.isfile(DEFAULT_SHELF):
        # Чистая машина: default.shelf ещё не создан Houdini — создаём сами
        # с готовым shelfSetEdit, чтобы полка была видна с первого старта.
        os.makedirs(os.path.dirname(DEFAULT_SHELF), exist_ok=True)
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<shelfDocument>\n'
            '  <shelfSetEdit name="shelf_set_prokladka" fileLocation="{loc}">\n'
            '    <addMemberToolshelf name="prokladka" inPosition="15"/>\n'
            '  </shelfSetEdit>\n'
            '</shelfDocument>\n'
        ).format(loc=DEST_DIR.replace('\\', '/'))
        with open(DEFAULT_SHELF, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, "default.shelf created with shelfSetEdit"

    with open(DEFAULT_SHELF, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'prokladka.shelf' in content:
        return True, "shelfSetEdit уже есть"

    edit = (
        '  <shelfSetEdit name="shelf_set_prokladka" fileLocation="{loc}">\n'
        '    <addMemberToolshelf name="prokladka" inPosition="15"/>\n'
        '  </shelfSetEdit>\n'
    ).format(loc=DEST_DIR.replace('\\', '/'))

    backup = DEFAULT_SHELF + '.bak_prokladka'
    shutil.copy2(DEFAULT_SHELF, backup)
    content = content.replace('</shelfDocument>', edit + '</shelfDocument>')
    with open(DEFAULT_SHELF, 'w', encoding='utf-8') as f:
        f.write(content)
    return True, "shelfSetEdit added (backup: {})".format(os.path.basename(backup))


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
        ("Shelf visibility", step_shelf_visibility),
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
        print("Дальше:")
        print("  1. Перезапустить Houdini")
        print("  2. Вкладка PROKLADKA на панели полок (кнопка PROKLADKA)")
        print("  Если вкладки нет: '+' на панели полок -> галка PROKLADKA")


if __name__ == '__main__':
    main()
elif '__file__' not in dir():
    # exec() контекст — авто-запуск
    main()
