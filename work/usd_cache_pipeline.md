# Кэши анимации: Блендер → Гудини (рабочий рецепт PROKLADKA)

Проверено на реальной задаче (FreeRide, 5 персонажей × 4 анимации, 2026-09-08).
Автор: Maksim Kovalev.

## Формат: usdc point cache БЕЗ скелета

Гудини корректно читает из Блендера только **pure point cache**: деформированный
меш покадрово точками. USD-скелет (UsdSkel), который пишет штатный USD-экспортёр
Блендера, **не проигрывает** на уровне SOP-импорта — приходит Т-поза/бинд.
FBX с анимацией скелета в Гудини тоже не вариант (T-поза; исторически в студии
FBX выгнали статичным референсом, анимация жила только в usdc — artur.usdc).

Структура рабочего файла (сверяно с artur.usdc):
- Корневой Xform `/asset_name`
- Тело: `UsdGeomMesh`, статичные faceVertexCounts/Indices + `points` сэмплы
  на каждый кадр (мировые координаты)
- Оружие: Xform с покадровой мировой матрицей (transform op) + внутрь статичный
  Mesh (точки 0 сэмплов — локальные)
- Никаких Skeleton/SkelRoot/SkelAnimation

## Оси

- Координаты пишутся **сырыми Z-up из Блендера**, метаданные `upAxis = Z`
  (Гудини — Z-up пакет, честный Z убирает любые повороты импортёра).
- `upAxis = Y` при сырых Z-up координатах = персонаж ляжет мордой вниз.
- Формально «правильный» Y-up (с конвертацией x,−z,y) тоже кладёт персa —
  конвертация в этой паре не нужна вовсе.

## FPS

`TimeCodesPerSecond` кэша = fps сцены Гудини, иначе скорость анимации
плывёт (кэш 30fps в сцене 24fps = ×1.25 быстрее). Перед выгоном узнай fps
приёмной сцены. Диапазон сэмплов = диапазон тейка (f1..fN, циклы замкнуты).

## Экспорт из Блендера (pxr внутри Blender Python)

- Деформированный меш снимать через evaluated depsgraph:
  `dg = bpy.context.evaluated_depsgraph_get(); ev = obj.evaluated_get(dg);
  me = ev.to_mesh()` → точки `mw @ v.co` по кадрам, `ev.to_mesh_clear()`.
- Stage собирать в памяти: `Usd.Stage.CreateInMemory()` +
  `stage.GetRootLayer().Export(path)` — CreateNew на существующий путь падает
  (кэш слоёв pxr держит идентификаторы).
- Оружие: статичная топология локально + `xform.AddTransformOp()`,
  `op.Set(Gf.Matrix4d(мировая матрица), f)`. Матрицу Блендера конвертировать:
  `Gf.Matrix4d([[float(x) for x in row] for row in mw])`.
- Батч-экспортёр: сцена `omon_rus_animation`, результат в
  `E:\0.Project\Work\FreeRide\99y\assets\omon0X\work\cache\`.

## Импорт в Гудини

- SOP-уровень: нода **USD Import** (`usdimport`): `filepath1` = путь,
  `primpattern` = `/имя_ассета`, **`importtime` = `$FF`** (иначе статичный кадр).
- File → Import → Geometry (File SOP) тоже читает .usdc.
- LOPs/Solaris: Sublayer/Reference — для композиции сцены.

## Грабли (всё проверено болью)

1. **Скрытые объекты не оцениваются депсграфом** — скрытый источник/меш даёт
   статичную выборку и ровные нули в замерах. Перед сэмплированием/бейком
   расконсервировать (hide_get/hide_set, layer hide_viewport, collection
   datablock hide_viewport — флаги на ВСЕХ уровнях, родитель не покрывает детей).
2. **Скелетный импорт аддона Mixamo в Блендере** даёт статичные слепки поз
   (ключи-константы на Ctrl-костях) — живая анимация только в тейках; фикс =
   mute констрейнтов mixamorig-костей + покадровый перенос поз (см. сессию
   FreeRide) либо сразу point cache.
3. **pxr API из Blender-сборки**: классы через `UsdGeom.Mesh` (не UsdGeomMesh);
   `stage.GetTimeSamples()` нет — пер-атрибутно `attr.GetTimeSamples()`;
   `SdfPath` без GetDepth — считать по строке; `XformCommonAPI.SetMatrix` нет —
   `AddTransformOp().Set(Gf.Matrix4d, f)`; IDPropertyArray без tolist.
4. **hrpyc (пульт в Гудини)**: сервер `import hrpyc; hrpyc.start_server()` —
   порт **18811**; клиенту нужны модули `rpyc==4.1.0` (версия Гудини) и
   `future`; пути клиента — `python311libs` установки Гудини. Ноды создавать с
   `run_init_scripts=False` (иначе «Invalid node type name» из потока);
   `hou.ui.queueToMainThread` в 20.5 нет — код исполнять прямо в потоке
   сервера; вызовы `hou.ui.*` из потока роняют сервер.
5. **MCP-мост для ZCode**: `PROKLADKA/work/houdini_mcp_server.py` — TCP 9877,
   протокол blender-mcp (JSON: ping / get_scene_info / execute_code), исполнение
   в потоке сервера. Консоль Гудини показывает лог подключений.

## Вердикт по осям (A/B тест в живом Гудини)

usdimport SOP читает .usdc КАК ЕСТЬ — метаданные upAxis игнорируются.
- Сырые Z-up координаты + upAxis=Z = персонаж СТОИТ вертикально (Z 0..1.17) ✓✓✓
- Y-up конвертация (x, z, -y) + upAxis=Y = лежит на глубине ✗
Правило: пишем сырые мировые координаты Блендера, upAxis=Z. Ничего не конвертировать.
A/B замер: zup Z 0..1.17 vs yup Y 0..1.17 (лежит) — живой Гудини 20.5.278.

## Статус FreeRide (2026-09-08)

20/20 персонажей анимированы и выгнаны: `assets\omon0X\work\cache\` —
`.abc` + `.usdc` + `.fbx` на каждую анимацию. Эталон импорта в Гудини:
`/obj/omon01_seat` (usd_import, $FF, fps 30) — проверен вживую.
