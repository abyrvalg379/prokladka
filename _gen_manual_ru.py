# -*- coding: utf-8 -*-
r"""PROKLADKA - Руководство пользователя (RU). Генератор DOCX на семейственном
шаблоне (_docstyle.py, «вариант C»). Запуск:  python _gen_manual_ru.py
Выход:   docs\PROKLADKA_Manual_RU.docx
"""

import json

import _docstyle as ds

OUT = r'D:\AI\ZCode\Project\prokladka\docs\PROKLADKA_Manual_RU.docx'


def h1(doc, text):
    return ds.h1(doc, text)


def h2(doc, text):
    return ds.h2(doc, text)


def p(doc, text, bullet=False, italic=False, grey=False):
    return ds.p(doc, text, bullet=bullet, italic=italic, grey=grey)


def kv_note(doc, text):
    return ds.kv(doc, text)


def add_table(doc, rows, widths, sev_col=None):
    return ds.add_table(doc, rows, widths, sev_col=sev_col)


def _save(doc, out):
    ds.footer(doc.sections[1], 'PROKLADKA')
    ds.strip_tail(doc)
    doc.save(out)
    h1s = [t for t in ds.H1_REGISTRY if t.lower() not in ('содержание', 'contents')]
    json.dump(h1s, open(out.replace('.docx', '.h1.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    print('saved:', out)


doc = ds.new_doc('PROKLADKA', 'Руководство пользователя', 'V1.10.0  -  WINDOWS')

p(doc, 'PROKLADKA - FBX-мост между Blender, Maya, Houdini и Unreal Engine. Один и тот же '
       'ассет приезжает в каждое приложение правильного размера, с правильным неймингом и '
       'правильными UV - без ручных переменных окружения и танцев с масштабами. В комплекте: '
       'пресеты нейминга, Universal UV renamer, Rig Transfer, авто-адаптация масштаба и '
       'импорт в Unreal Engine со статик- и скелетными мешами.')

kv_note(doc, 'github.com/abyrvalg379/prokladka')

h1(doc, 'Содержание')
ds.toc_field(doc, 'Оглавление: откройте документ в Word/LibreOffice и обновите поле (F9), '
                  'чтобы заполнить номера страниц.')

# ════════════════════════════════════════════════════════════════════════════

h1(doc, '1. Философия и правило приёмника')
p(doc, 'Ассет адаптируется под принимающую сторону, а не наоборот. Отдающая сторона '
       'экспортирует в нейтральном формате - метры, Y-up, FBX. Принимающая конвертирует '
       'ассет под свои конвенции при импорте.')
add_table(doc, [
    ('Принимающая сторона', 'Единицы', 'Naming', 'Пример'),
    ('Blender', 'метры', 'lowercase + _geo', 'wing_main_geo'),
    ('Maya', 'метры', 'lowercase + _geo', 'wing_main_geo'),
    ('Houdini', 'метры', 'суффикс _geo / _vdb', 'wing_main_geo'),
    ('Unreal Engine', 'сантиметры (×100)', 'PascalCase + SM_', 'SM_WingMain'),
], [4.4, 3.4, 4.6, 4.6])
p(doc, 'Правило приёмника: импортированный ассет - всегда контейнер с нулевой позицией, '
       'нулевым поворотом и единичным масштабом. Правильные габариты запечены в вершины. '
       'Никаких компенсирующих скейлов на объекте: то, что вы видите в свойствах, - нули и '
       'единицы, а весь размер живёт в геометрии. Это правило действует и на экспорт: '
       'трансформы объекта запекаются при выгрузке.')

h1(doc, '2. Возможности')
for b in (
    'FBX-экспорт и импорт через общую очередь последних файлов (экспорт - бета-статус);',
    'пресеты нейминга: Default, Plain, Unreal, Dots, Rig - редактируемые и идемпотентные;',
    'рекурсивный нейминг: Apply Naming покрывает выделение и всю ветку детей;',
    'авто-нейминг при импорте в Blender (галка, включена по умолчанию);',
    'Universal UV renamer: конвенции Maya / Blender / Houdini / Unreal / Custom;',
    'Rig Transfer: перенос рига через FBX + recipe.json (constraints, control shapes);',
    'Houdini: мультиформат FBX / VDB / Alembic / USD, авто-проверка масштаба по bbox;',
    'Unreal: импорт Static/Skeletal Mesh, Material Instance из PBR-текстур, докаемая панель;',
    'Legacy scale: ручной выход для чужих ассетов с необычным масштабом;',
    'Maya: PBR Texture Assigner - авто-распознавание слотов, UDIM, ACES colorSpace;',
    'иерархия: Collection и Empty, MayaRotate, Loc -> Grp.',
):
    p(doc, b, bullet=True)

h1(doc, '3. Установка')
p(doc, 'Скачайте репозиторий (Code - Download ZIP) и распакуйте, затем - по приложению.')
h2(doc, '3.1 Blender 4.5+')
for b in (
    'Edit - Preferences - Get Extensions - меню в правом верхнем углу - Install from Disk;',
    'выберите out/blender/prokladka.zip и включите PROKLADKA;',
    'панель - в N-панели вьюпорта, вкладка PROKLADKA.',
):
    p(doc, b, bullet=True)
h2(doc, '3.2 Maya 2022+')
for b in (
    'перетащите out/maya/install_prokladka.py прямо во вьюпорт Maya;',
    'подтвердите установку и перезапустите Maya;',
    'на полке Custom появится кнопка PROKLADKA. Инсталлятор самодостаточен - всё нужное '
    'встроено в файл, drag-and-drop работает из любого расположения; изменения подхватываются '
    'при каждом запуске панели.',
):
    p(doc, b, bullet=True)
h2(doc, '3.3 Houdini 20.5+')
for b in (
    'способ 1: двойной клик по out/houdini/install_PROKLADKA.bat - установит файлы и пакет сам;',
    'способ 2: скопируйте out/houdini/package/prokladka/houdini/ в '
    'Documents/houdini20.5/prokladka/houdini/ и создайте packages/prokladka.json по образцу '
    'из README репозитория;',
    'вкладки нет на полке? Плюс в строке вкладок полок - галочка PROKLADKA (один раз).',
):
    p(doc, b, bullet=True)
h2(doc, '3.4 Unreal Engine 5.6+')
for b in (
    'скопируйте out/unreal/prokladka/ в Content/Python/ проекта;',
    'скопируйте out/unreal/init_unreal.py в Content/Python/;',
    'включите плагин Python Editor Script Plugin и перезапустите UE;',
    'кнопка PROKLADKA на тулбаре или Window - PROKLADKA - Open Panel.',
):
    p(doc, b, bullet=True)

h1(doc, '4. Быстрый старт: ассет из Blender в Maya')
for b in (
    'Blender: выделите ассет, нажмите Export на панели PROKLADKA - файл уедет в очередь экспортов.',
    'Maya: откройте панель PROKLADKA с полки Custom, нажмите Import Bridge - последний '
    'экспорт приедет контейнером в нулях с правильным масштабом.',
    'Нейминг: галка авто-нейминга в Blender ставит суффиксы при импорте сама; в Maya - '
    'кнопка Apply Naming по выделению с веткой детей.',
    'Готово: размер в метрах, имена по конвенции, пивоты на месте - можно отдавать валидатору.',
):
    p(doc, b, bullet=True)

h1(doc, '5. Blender: панель')
p(doc, 'Панель PROKLADKA в N-панели вьюпорта:')
for b in (
    'Import Bridge FBX - импорт последнего файла из очереди экспортов; после импорта '
    'прогоняется активный пресет нейминга (галка авто-нейминга);',
    'Recent FBX - список последних файлов с размером и временем; заголовок панели показывает, '
    'какой файл будет импортирован;',
    'Clear History - очистить очередь экспортов (с подтверждением);',
    'Apply Naming - применить активный пресет к выделению и всей ветке детей, идемпотентно: '
    'повторный прогон не плодит двойные суффиксы;',
    'Legacy scale - ручной множитель масштаба для чужих ассетов с нестандартным размером '
    '(по умолчанию выключен).',
):
    p(doc, b, bullet=True)

h1(doc, '6. Maya: панель и полка')
p(doc, 'Кнопка PROKLADKA на полке Custom открывает Qt-панель:')
for b in (
    'Export - экспорт выделения в FBX с нейтральными настройками (метры, Y-up);',
    'Import Bridge - импорт последнего файла очереди;',
    'Apply Naming - пресет нейминга по выделению с рекурсией по детям; чистка служебных '
    'последовательностей в именах после FBX-импорта;',
    'PBR Texture Assigner - авторазкладка PBR-текстур по слотам материала, UDIM и ACES colorSpace;',
    'иерархия: Collection и Empty, MayaRotate, Loc -> Grp (галка превращает импортированные '
    'EMPTY в локаторы - включайте, только если локаторы действительно нужны);',
    'History - журнал экспортов с размером и временем; Clear - очистка очереди.',
):
    p(doc, b, bullet=True)

h1(doc, '7. Houdini: полка и панель')
p(doc, 'Полка PROKLADKA - семь кнопок с иконками (панель, экспорт форматов, Import Bridge, '
       'нейминг, журнал, очистка):')
for b in (
    'Export FBX - экспорт по выделению или умному поиску активной геометрии; файл всегда '
    'бинарный, единицы - метры, трансформы объектов запекаются при выгрузке;',
    'VDB / Alembic / USD - одноимённые экспорты для объёмов, кэшей и сцен;',
    'Import Bridge - импорт последнего файла очереди; несколько файлов - выбор из списка. '
    'Импорт идёт в /obj/prokladka_imports: повторный импорт того же файла обновляет ноду '
    'вместо создания копии; гигантские файлы автоматически помечаются и масштабируются '
    '(auto-scaled /100);',
    'Apply Naming - пресет нейминга по выделению;',
    'History и Clear - журнал и очистка очереди.',
):
    p(doc, b, bullet=True)

h1(doc, '8. Houdini: HDA-ноды')
p(doc, 'Помимо полки, в Houdini доступны две ноды-генератора: prokladka::export и '
       'prokladka::import (TAB-меню внутри геометрии).')
h2(doc, '8.1 prokladka::export')
p(doc, 'Нода-обёртка над экспортом: укажите SOP to Export (перетащите ноду в поле или '
       'наберите путь), Output FBX - путь файла, диапазон кадров при необходимости - и '
       'EXPORT. Нода reference-driven: проводов к ней не нужно - это та же идиома, что у '
       'ROP-драйверов. Трансформы объекта уровня /obj запекаются при экспорте.')
h2(doc, '8.2 prokladka::import')
p(doc, 'Нода-генератор импорта: путь подставляется автоматически (кнопка USE LAST EXPORT '
       'берёт последний экспорт очереди). Провода к ноде не нужны - выход идёт дальше по '
       'сети, а свежая нода сразу указывает на последний экспорт. CHECK SCALE - '
       'диагностика масштаба; гигантские FBX автоматически помечаются и приводятся к метрам.')

h1(doc, '9. Unreal Engine')
for b in (
    'Window - PROKLADKA - Import Bridge FBX или кнопка на тулбаре;',
    'импорт Static и Skeletal Mesh с конвертацией метров в сантиметры (×100) - объекты '
    'приезжают правильного размера;',
    'нейминг по конвенции Unreal: префикс SM_ для статик-мешей;',
    'Material Instance собирается из PBR-текстур при наличии;',
    'докаемая панель: Open Panel на той же вкладке меню.',
):
    p(doc, b, bullet=True)

h1(doc, '10. Нейминг и UV')
h2(doc, '10.1 Пресеты нейминга')
p(doc, 'Пять встроенных пресетов, все редактируемые и идемпотентные:')
add_table(doc, [
    ('Пресет', 'Суффиксы и стиль'),
    ('Default', 'lowercase, _geo / _grp / _skel'),
    ('Plain lowercase', 'lowercase без суффиксов'),
    ('Unreal', '_Mesh / _SkelMesh'),
    ('Dots only', 'точки вместо подчёркиваний'),
    ('Rig', '_jnt / _ctl'),
], [4.4, 12.6])
p(doc, 'Apply Naming всегда рекурсивен: выделение плюс вся ветка детей. Идемпотентность '
       'защищает от двойных суффиксов при повторных прогонах. В Blender доступен чекбокс '
       'авто-нейминга при импорте (включён по умолчанию).')
h2(doc, '10.2 Universal UV renamer')
p(doc, 'Переименование UV-сетов под конвенцию принимающей стороны: Maya (map1), Blender '
       '(UVMap), Houdini (uv), Unreal (LightmassUV), Custom - своё имя.')

h1(doc, '11. Rig Transfer')
p(doc, 'Перенос рига делится на два носителя: FBX везёт геометрию, скелет и веса; '
       'recipe.json - логику связей (constraints, control shapes, парентинг). Формат рецепта '
       'DCC-агностичен и маппится на родные констреинты обеих сторон:')
add_table(doc, [
    ('Recipe', 'Maya', 'Blender'),
    ('parent', 'parentConstraint', 'CHILD_OF'),
    ('point', 'pointConstraint', 'COPY_LOCATION'),
    ('orient', 'orientConstraint', 'COPY_ROTATION'),
    ('scale', 'scaleConstraint', 'COPY_SCALE'),
    ('aim', 'aimConstraint (+ up)', 'TRACK_TO'),
    ('aim_no_up', 'aimConstraint (no up)', 'DAMPED_TRACK'),
], [3.6, 6.6, 6.8])
p(doc, 'Кастомные формы контролов переносятся как curve points - независимо от пакета.')

h1(doc, '12. Очередь экспортов')
p(doc, 'Все экспорты пишутся в общую очередь (файл в C:\\temp, имя вида <scene>_bridge.fbx) - '
       'её голова и есть то, что приедет по Import Bridge на любой стороне. Правила работы:')
for b in (
    'экспортнул из одного приложения - сразу Import Bridge в другом;',
    'несколько файлов в очереди: Houdini предложит выбор из списка, Blender и Maya берут голову;',
    'Clear History очищает очередь, когда не хотите импортировать чужое;',
    'сохраняйте сцену перед экспортом: несохранённый файл даёт имена вида untitled_*;',
    'Blender показывает в панели, какой файл уйдёт в импорт - проверяйте перед нажатием.',
):
    p(doc, b, bullet=True)

h1(doc, '13. Сценарии')
for t in (
    ('Приёмка ассета из Maya в Blender',
     'Maya: иерархия собрана локаторами, Export выделения. Blender: Import Bridge - иерархия '
     'приезжает 1:1 пустышками, авто-нейминг расставляет _grp по всей ветке. Ассет готов к '
     'валидации: ноль суффикс-ошибок.'),
    ('Blender - Houdini',
     'Export в Blender, в Houdini Import Bridge или нода prokladka::import с USE LAST '
     'EXPORT. Бинарный FBX в метрах приезжает контейнером в нулях; гигантский файл сам '
     'получит пометку auto-scaled.'),
    ('Отдача в Unreal',
     'Экспорт как обычно - на стороне UE импорт применяет ×100 и префиксы SM_. Материалы '
     'собираются в инстансы из PBR-текстур.'),
    ('Перенос рига',
     'Экспортируйте риг и рецепт: FBX понесёт геометрию и веса, recipe.json - констреинты и '
     'формы контролов. На принимающей стороне связи восстановятся родными констреинтами.'),
):
    h2(doc, t[0])
    p(doc, t[1])

h1(doc, '14. Решение проблем')
add_table(doc, [
    ('Симптом', 'Причина', 'Что делать'),
    ('Импорт приехал гигантом (×100)', 'экспорт в сантиметрах без юнит-фактора',
     'проверьте пометку auto-scaled на импорте; вручную - Legacy scale или масштаб 0.01'),
    ('Объекты микроскопические в UE', 'метры против сантиметров UE',
     'убедитесь, что импорт идёт через PROKLADKA: множитель ×100 ставится автоматически'),
    ('Приехал не тот файл', 'голова общей очереди - чужой последний экспорт',
     'Clear History; в Houdini выберите файл из списка; проверяйте подсказку панели'),
    ('Имена вида untitled_*', 'сцена не сохранена при экспорте',
     'сохраните сцену и экспортируйте заново'),
    ('EMPTY из Blender стали локаторами в Maya', 'штатное поведение FBX-импорта Maya',
     'включите галку Loc -> Grp на панели Maya перед следующим импортом'),
    ('Имена без суффиксов после импорта', 'авто-нейминг выключен',
     'включите галку авто-нейминга или нажмите Apply Naming - он рекурсивен и идемпотентен'),
    ('Houdini: полки PROKLADKA нет на вкладках', 'полка установлена, но не включена',
     'плюс в строке вкладок полок - галочка PROKLADKA'),
    ('Houdini: провода не подключаются к ноде Import', 'нода - генератор, reference-driven',
     'провода и не нужны: задайте путь или USE LAST EXPORT, выход идёт дальше по сети'),
    ('Blender падает на свете из FBX', 'известная несовместимость отдельных сборок Blender',
     'обновите сборку или удалите свет из FBX-файла перед импортом'),
    ('Экспорт из Houdini не читается в Blender', 'ASCII-формат FBX',
     'PROKLADKA всегда пишет бинарный FBX - проверьте, что экспорт шёл через полку или ноду'),
], [4.4, 4.6, 8.0])

_save(doc, OUT)
