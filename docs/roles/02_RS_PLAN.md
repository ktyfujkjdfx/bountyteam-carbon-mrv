# BountyTeam — окончательный план RS-специалиста

> Обязательный контекст: `00_BOUNTYTEAM_MANIFEST.md`,
> `01_ARCHITECTURE_AND_FLOW.md`, `02_JSON_API_ABI_CONTRACTS.md` и этот файл.
> Нельзя самостоятельно менять schema, enum, единицы или смысл полей.

## 1. Твоя роль и конечный результат

Ты создаёшь воспроизводимое спутниковое доказательство. Ты отвечаешь за данные,
маски, индексы, геометрию, площадь, артефакты и ограничения метода. Ты не
принимаешь финансовое решение и не управляешь токенами.

Твой P0-результат — evidence bundle реального исторического пожара, который:

- получен из реальных Sentinel-2 L2A сцен;
- проходит shared JSON Schema и semantic validation backend;
- содержит источник, transform отражательной способности, grid, thresholds,
  hashes и web-превью;
- выдаёт только `NO_CHANGE`, `DISTURBANCE_DETECTED` или `INSUFFICIENT_DATA`;
- может быть повторно импортирован и показан без интернета.

## 2. Граница ответственности

### На входе

- `request.json`: AOI GeoJSON EPSG:4326, `plot_id`, даты/окна наблюдений,
  идентификатор режима.
- Общая `verification.schema.json` и golden fixtures.
- Primary и reserve AOI, утверждённые тимлидом.

### На выходе

Команда запуска:

```bash
python -m rs.verify --request request.json --output bundle_dir
```

Обязательный bundle:

- `verification.json` — без `evidence_hash` и без токен-статусов;
- `source-index.json` — provider, scene IDs, acquisition time, processing
  baseline, scale/offset, MGRS tile, bands и hashes исходных окон;
- `affected_area.geojson` — EPSG:4326, `[lon, lat]`;
- `dnbr.tif` — аналитический растр на metric grid;
- `before.webp`/`before.png` и `after.webp`/`after.png` — одинаковые bounds/size;
- `dnbr.webp`/`dnbr.png` с легендой;
- `firms.geojson`, если FIRMS использован;
- `artifact-manifest.json` с SHA-256 файлов.

Backend импортирует результат командой:

```bash
python -m backend.tools.import_bundle --bundle bundle_dir
```

## 3. Что ты никогда не отправляешь

- `FROZEN`, `ACTIVE`, `REVOKED`, `FREEZE_REQUESTED`.
- `evidence_hash`: его считает backend по каноническому JSON.
- Выдуманные цифры, scene IDs, площади или «confidence».
- Формулировку «пожар доказан только dNBR».
- Данные из разных режимов без маркировки.

Разрешённые `outcome`:

- `NO_CHANGE`;
- `DISTURBANCE_DETECTED`;
- `INSUFFICIENT_DATA`.

## 4. Приоритеты

### P0

- Primary и reserve AOI.
- Реальные T0/T1/T2 при наличии сопоставимых сцен: T0→T1 без значимого
  изменения, T1→T2 с пожаром.
- Если три даты научно непригодны — отдельный negative-control AOI/пара дат по
  решению тимлида; не называть это additionality или synthetic control.
- Корректный scale/offset, облачная/снежная маска, alignment, dNBR и площадь.
- FIRMS support для атрибуции fire reversal.
- `INSUFFICIENT_DATA` branch.
- Весь bundle и hashes; локальная копия.

### P1

- SWIR-композит B12/B8A/B04.
- Аккуратная dNBR-карта со шкалой и точками FIRMS.
- Более удобный report/preview и speed optimization.

### P2

- Контрольный участок, дополнительные индексы/источники, второй проект — только
  после разрешения тимлида и стабильного P0.

### CUT

Собственная ML-модель, оценка точного CO2/биомассы, leakage, additionality,
прогноз пожара, Sentinel-1 как незаявленная «готовая» интеграция.

## 5. Зафиксированная методика

### 5.1. Данные и отражательная способность

- Основной источник выбирается после реального теста поиска **и скачивания**
  одного канала. Каталог, который возвращает item, ещё не доказывает доступность
  asset.
- Резерв: Earth Search `sentinel-2-c1-l2a` COG или другой заранее проверенный
  источник. Скачивать только нужные bands и окно AOI.
- Нельзя безусловно «вычитать 1000». Используй метаданные продукта:

```text
reflectance = (DN + BOA_ADD_OFFSET_i) / QUANTIFICATION_VALUE
```

  Конкретный provider может уже гармонизировать значения. Запиши provider,
  processing baseline, исходный scale/offset и применённый transform.

### 5.2. Даты и сопоставимость

- Сцены должны быть из сопоставимого сезонного окна; учитывай фенологию, снег,
  дым, тени и солнечную геометрию.
- Предпочтительна одна MGRS tile; в любом случае обе даты явно перепроецируются
  на один reference grid.
- Не называй сезонное падение NDVI пожаром.
- Historical replay маркируется как historical, а cached computation — как
  `CACHED_REPLAY`.

### 5.3. Сетка, bands и resampling

- Аналитическая сетка: 20 м в подходящей UTM/metric CRS.
- NBR: B8A и B12 на 20 м.
- NDVI: B08 и B04; continuous raster можно агрегировать на 20 м усреднением.
- Категориальные маски/SCL — только nearest-neighbour.
- Площадь считается по валидным 20-метровым пикселям: один пиксель = 0,04 га,
  а не по градусам и не по упрощённому GeoJSON.

### 5.4. Маски и forest mask

- AOI cloud ratio считай внутри AOI, а не по всей плитке.
- SCL консервативно исключает 0, 1, 2, 3, 6, 7, 8, 9, 10, 11.
- Класс 5 сохраняй: post-fire bare ground может быть сигналом.
- Маску обязательно просмотри визуально; shadow-классы не должны превращаться в
  «пожар» или вырезать весь сигнал.
- Для обеих дат используй одну baseline forest mask. Укажи источник и год,
  например ESA WorldCover, и его ограничения. Не применяй post-event маску как
  исходный лес.
- Индексы сравнивай только там, где обе даты валидны и входит baseline forest.

### 5.5. dNBR и компоненты

```text
NBR = (B8A - B12) / (B8A + B12)
dNBR = NBR_before - NBR_after
```

Единая шкала в продукте:

| dNBR | Класс для визуализации |
|---:|---|
| < 0.10 | unburned/regrowth signal |
| 0.10–0.27 | low |
| 0.27–0.44 | moderate-low |
| 0.44–0.66 | moderate-high |
| ≥ 0.66 | high |

- Кандидат disturbance: `dNBR >= 0.27`.
- 8-connectivity; удалить компоненты меньше 1 га, то есть меньше 25 пикселей
  20×20 м.
- `DISTURBANCE_DETECTED`, если при достаточных данных остался хотя бы один такой
  компонент. Финансовый порог применяет backend, а не RS.
- Общая policy backend для fire action: площадь не менее 5 га и не менее 1% от
  baseline forest area, FIRMS support и достаточное качество.

### 5.6. FIRMS и атрибуция

- FIRMS — активные fire/thermal anomaly points, не граница пожара и не ground truth.
- В demo допускается зафиксированное spatial tolerance 500 м — маркируй как
  `DEMO LOGIC`.
- Отсутствие FIRMS не доказывает отсутствие пожара. В таком случае backend должен
  выбрать review, а не автоматическую заморозку.
- Для проверки согласованности можно использовать дополнительный независимый
  источник, но не называй это полноценной оценкой точности без ground truth.

### 5.7. Evidence Quality Score

RS отдаёт измеримые компоненты: pair-valid ratio, AOI cloud ratio, signal extent,
source agreement и ограничения. Backend рассчитывает gates/score. Это индикатор
полноты доказательства, а не статистическая вероятность истинности.

## 6. До старта: 16–17 сентября

### Блок A — снять риск доступа, 2–3 часа

- Проверь, разрешены ли заготовки и заранее скачанные данные.
- Протестируй STAC/catalog, затем физически прочитай один band window через
  rasterio.
- Проверь основной и резервный provider.
- Зафиксируй версии rasterio, pyproj, geopandas/shapely, numpy и STAC client.

Результат: минимальный read script, provider decision и локальный test window.

### Блок B — выбрать событие, 3–4 часа

- Найди primary и reserve fire event.
- Зафиксируй AOI, acquisition dates, реальные scene IDs, tile, season rationale.
- Проверь FIRMS в интервале событий.
- Визуально проверь до/после и SCL.

Результат: `configs/primary.json`, `configs/reserve.json`, список сцен и локально
закэшированные необходимые окна.

### Блок C — contract rehearsal, 2–3 часа

- Возьми golden fixtures и shared schema.
- Реализуй/отрепетируй формирование bundle в разрешённых правилами пределах.
- Передай backend пример bundle и получи подтверждение импорта.

Результат: schema-valid sample без токен-статусов и без evidence hash.

## 7. Почасовой план хакатона

### Пятница, 18:30–19:00

Спроси кейсодержателя: достаточно ли detection/reversal verification без точного
CO2; разрешены ли cached scenes; есть ли рекомендованные AOI/данные; какой уровень
валидации ожидается. Передай ответы тимлиду.

### 19:00–19:30

- Подтверди primary/reserve AOI и режим данных.
- Проверь contract version и CLI.
- Отдай backend schema-valid fixture немедленно, не дожидаясь real computation.

Результат: backend может разрабатывать независимо от долгой обработки.

### 19:30–22:00

- Запусти real pipeline: source lookup/download → calibration → masks → common grid.
- К 21:00 отдай `source-index.json` и первый preview.
- К 22:00 передай первый bundle или честный incomplete/insufficient bundle.
- Вместе с backend прогони import и исправь только границу данных.

Checkpoint 22:00: fixture и первый RS output принимаются одной схемой; enum и
единицы совпадают; RS нигде не посылает `FROZEN`.

### 22:00–02:00

- Заверши dNBR, component filtering, area и FIRMS support.
- Подготовь negative/no-change и insufficient ветки.
- Сделай web previews одинакового размера/bounds.
- Сформируй artifact manifest и hashes.
- Передай backend bundle до 01:00, оставив час на интеграцию.

Checkpoint 02:00: backend импортировал bundle; UI показывает артефакты; есть
локальная копия и короткий скринкаст. Затем handoff и сон.

### 02:15–07:45 — сон

Минимум 5 часов. Перед сном оставь README, точную команду запуска и путь к cache.

### 07:45–08:15

- Холодный запуск documented command.
- Проверь hashes и доступность всех локальных assets.
- Выбери один утренний P0-дефект.

### 08:15–11:30

- Финализируй real T0/T1/T2 либо согласованный negative-control сценарий.
- Добавь реальный `affected_area.geojson`, dNBR raster/map, before/after и FIRMS.
- Передай финальный real bundle backend не позже 10:00.
- Помоги backend повторить import/run без ручного редактирования JSON.
- Проверь все отображаемые числа: только результат реального запуска.

Checkpoint 11:30: другой человек может назвать provider, scene IDs, transform,
valid ratio, площадь, thresholds и ограничения.

### 12:00–14:30

- Покажи метод эксперту; особенно dates/phenology, SCL, grid, forest mask, FIRMS.
- Исправляй только научную корректность P0.
- Если эксперт не подтверждает автоматическую атрибуцию — выход становится review,
  а не fake freeze.

### 14:30–16:30

- P1-визуализации только после стабильного real bundle.
- Подготовь reserve AOI bundle или хотя бы проверенные source windows.
- Научи backend/тимлида повторить cached replay.

Checkpoint 16:30: интернет можно отключить; primary и reserve данные доступны;
изменённый файл ломает hash validation.

### 16:30–18:00

- Проверка offline, restart, corrupted artifact и insufficient branch.
- В 18:00 feature freeze; после этого не меняй алгоритм/thresholds.

### 18:00–20:00

- Regression на primary, no-change и insufficient.
- Зафиксируй versions/config/data manifest/git commit.
- Участвуй в финальном видео и release candidate.

### 20:00–23:30

- Помоги второму участнику запустить pipeline/import по README.
- Упакуй только необходимые assets, не весь SAFE.
- Проверь загруженный release и scene/source manifest.

## 8. Точки интеграции

| Время | Что передаёшь | Кому | Проверка приёмки |
|---|---|---|---|
| Пт 19:30 | golden-compatible sample | Backend | schema passes |
| Пт 22:00 | first bundle/source index | Backend/Frontend | import + previews open |
| Сб 01:00 | complete computed bundle | Backend | policy can run |
| Сб 10:00 | final real bundle | Backend/Frontend | E2E unchanged |
| Сб 16:30 | offline + reserve assets | Тимлид | no internet smoke |
| Сб 18:00 | frozen data/config manifest | Release Owner | checksum recorded |

Если handoff задерживается более чем на 20 минут, отправь тимлиду exact error,
repro и fallback. Не молчи, пытаясь три часа победить provider.

## 9. Acceptance criteria RS

- [ ] Реальные scene IDs/provider/acquisition times записаны.
- [ ] Scale/offset взяты из metadata/provider semantics и сохранены.
- [ ] Даты сезонно сопоставимы; smoke/snow/cloud ограничения описаны.
- [ ] Одна 20m metric grid; B8A/B12 для NBR; правильный resampling.
- [ ] Pair-valid mask и baseline forest mask воспроизводимы.
- [ ] AOI cloud ratio считается внутри AOI.
- [ ] Площадь считается по metric pixels; GeoJSON EPSG:4326 `[lon,lat]`.
- [ ] Компоненты <1 га удалены; dNBR thresholds едины.
- [ ] FIRMS не назван периметром/ground truth.
- [ ] `verification.json` проходит schema и semantic checks backend.
- [ ] Нет `evidence_hash`, `FROZEN` и финансовых решений от RS.
- [ ] Есть no-change/negative и insufficient scenarios.
- [ ] Артефакты открываются локально; manifest hashes сходятся.
- [ ] Backend-разработчик повторил import/run по README.

## 10. Fallbacks

- Provider недоступен → проверенный резервный COG provider.
- Интернет отсутствует → локальные AOI windows и `CACHED_REPLAY` с честной меткой.
- Primary AOI облачный/слабый → reserve AOI.
- Нет подходящего T0/T1/T2 → согласованный negative-control AOI, без ложного
  названия «синтетический контроль».
- FIRMS не подтверждает событие → `DISTURBANCE_DETECTED`, backend отправляет на
  `REVIEW_REQUIRED`, не автоматический freeze.
- Расчёт падает → отдать последний hash-verified bundle и показать сохранённые
  промежуточные артефакты; не подделывать live computation.

## 11. Что говорить на защите, 40–60 секунд

> Мы используем реальные Sentinel-2 L2A сцены и приводим их к общей 20-метровой
> метрической сетке. NBR считаем по B8A и B12, сравниваем только попарно валидные
> пиксели исходного леса и удаляем компоненты меньше одного гектара. Площадь
> берём по пикселям, а не по градусному GeoJSON. dNBR обнаруживает изменение, а
> поддержку гипотезы пожара даёт FIRMS; точки FIRMS не считаются периметром или
> ground truth. RS-модуль сообщает только наблюдение и ограничения данных.
> Решение о временной блокировке принимает backend по общей policy.

## 12. Что запрещено менять самостоятельно

- JSON Schema, enum, названия/единицы полей, API и ABI.
- Пороги dNBR, minimum component и action thresholds после contract freeze.
- Outcome на `FROZEN` или любое token state.
- Методику так, чтобы cached/synthetic данные выглядели как live/real.
- Числа в демо вручную.

## 13. Формат отчёта на sync

```text
RS <время>
Artifact: <bundle/config/commit>
Mode: REAL|SYNTHETIC / COMPUTED|CACHED_REPLAY
Scenes: <IDs>
Schema: PASS|FAIL
Blocker: <exact error or none>
Next handoff: <кому, что, время>
```
