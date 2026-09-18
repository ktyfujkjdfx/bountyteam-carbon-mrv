## Обязательное правило источников данных

Единственными авторитетными входными данными для конкурсного расчёта, тестовых эталонов, демонстрационных результатов и итогового отчёта являются:
`data/` — распакованное содержимое предоставленного организаторами архива `data.zip`;
`doc/` — распакованное содержимое предоставленного организаторами архива `doc-1789730244.zip`, включая постановку задачи, критерии, описание данных, формулы и ограничения.

Запрещено:
- подменять выданные растры другими научными наборами;
- брать коэффициенты, baseline, цены, параметры или готовые результаты из сторонних GitHub-репозиториев;
- подключать сторонние предобученные модели без отдельного разрешения Team Lead;
- использовать внешние данные для улучшения конкурсных чисел;
- молча смешивать предоставленные данные с данными другой версии;
- считать GitHub-репозитории источником научной истины.

Указанные в roadmap GitHub-проекты разрешено использовать только как инженерные и архитектурные ориентиры: изучать структуру кода, обработку растров, организацию pipeline, визуализацию, тестирование и reproducibility. Перед заимствованием кода необходимо проверить лицензию и сохранить attribution.

Единственное разрешённое исключение — обязательная демонстрация получения данных из открытого источника по параметрам запроса, требуемая критериями кейса. Для неё разрешено загрузить тот же продукт и совместимую версию, которые описаны в `doc/` и реестре `data/sources.csv`.

Такое получение должно:
- выполняться отдельным adapter/retriever;
- сохранять URL запроса, продукт, версию, дату доступа, лицензию и checksum;
- использовать локальный cache и поддерживать offline replay;
- не подменять предоставленный организаторами набор в основных demo-расчётах;
- сопровождаться сравнением версии и совместимости;
- не изменять эталонные результаты без отдельного решения Team Lead.

Если внешний источник недоступен, основной сервис и демонстрация должны продолжать работать на сохранённых данных из `data/`.

Любое расширение данных, коэффициентов или моделей требует предварительного письменного одобрения Team Lead и отдельного PR с обоснованием влияния на результаты.

# BountyTeam Carbon Lens — Backend — API и интеграция

## Общая спецификация MVP — одинакова для всех пяти roadmap

Версия планов: Carbon Lens MVP v2, 18.09.2026. Эти файлы заменяют старые roadmap; при конфликте с официальной постановкой приоритет у `doc/`, спор фиксируется и передаётся Team Lead (TL). Не исправлять методику молча.

**Продукт:** инструмент верификатора для проверки лесного углеродного заявления; владелец задаёт контур и период, инвестор изучает результат. Изюминка: **«Заявлено → рассчитано по общей методике → раскрыто до зоны, источника и формулы → зафиксировано в паспорте»**. Существующий запас не выдаётся за заслугу проекта. Основной экран показывает Q, сценарную стоимость, ограничения и, при наличии сопоставимого заявления, разрыв с заявлением.

### На чём строим

- Репозиторий: https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv .
- Стабильная исходная точка: `p0-integrated-v1.0.0`, commit `5ba24ddb4b8f47099e7569613b9ce51ab16009e8`.
- Начинать от актуального `origin/main` после bootstrap TL с `data/`, `doc/` и этими roadmap. Не откатывать main на старый SHA.
- P0 описан в предыдущих интеграционных отчётах; текущий GitHub HEAD составитель roadmap заново не аудировал. Каждый Claude обязан проверить фактические файлы, AGENTS.md/CLAUDE.md, команды, схему БД и contracts перед кодом.
- Сохраняем API v1, frozen contracts, ABI, fixtures и все старые теги. P0 — регрессионный контур, а не готовый калькулятор углерода. Dadia/Evia и прежние synthetic flows не являются научными данными нового кейса.
- Переиспользуем jobs/polling, идемпотентность, artifacts integrity, карту/слайдер, error boundary, UNKNOWN fallback, журнал, proof. Новый UI — отдельный маршрут `/lens`; P0 остаётся доступным отдельно.
- Bootstrap TL может хранить выданные 178 файлов data (168 GeoTIFF) и 4 PDF doc в Git после проверки размеров/лицензий. Старое безусловное «GeoTIFF не коммитить» отменено. Не коммитить ZIP-дубликаты, runtime-cache, .env, dist, node_modules, .venv.
- Присланные data(2).zip и doc-1789730244(3).zip побайтово совпадают с предыдущими data(1).zip и doc-1789730244(2).zip. SHA-256 архивов: data `d8723225a1f66f1ff1890439e6e561f3a28a94f6a81b63b5db99a73579fc22a8`; doc `f1e471dc909800a827d194c6baebb5e46c915b92bdf9deae0e65761d744a3cf7`. Проверять распакованные файлы по file_catalog.csv; не менять их.

### Границы обещаний и исправления прежних примеров

1. Baseline из истории 2015–2019 задана на 2019–2029: это сценарий кейса, не доказательство действий владельца или истинной дополнительности. Исследовательские участки не объявлять зарегистрированными проектами.
2. Только живая надземная древесная биомасса; не полный баланс экосистемы. Положительное E — потеря этого пула, не мгновенный выброс всего углерода в атмосферу.
3. Облачность Sentinel ухудшает объяснение изменения. Она не делает автоматически неполным покрытие CCI. Отдельно хранить biomass/SD coverage, baseline coverage и optical paired-valid coverage.
4. Нет обязательных числовых входов/покрытия для Q → `q=null`, reason. Валидные входы, но R≤0 или H/R≥1 → `q=0`, reason. Не смешивать null и 0.
5. Заявления компаний отсутствуют в ZIP. Необязательное `claimed_units` — явно пользовательский/демонстрационный ввод, не научный факт. То же относится к заводу, покупателям и подпискам.
6. Разрыв × сценарная цена — «сценарная стоимость неподдержанной части заявления». Не называть это установленным ущербом, доходностью, вероятностным Value at Risk, доказанным мошенничеством или гарантированно сэкономленными деньгами.
7. Хеш выявляет изменение файла относительно доверенной фиксации. Один hash anchor НЕ предотвращает двойную продажу и НЕ удостоверяет истинность расчёта. Учёт уникального выпуска/передачи/погашения — отдельная система вне обязательного MVP.
8. Не обещать конкретный положительный Q, восстановление, «половина леса сгорела» или цифры 8 000→2 100: сначала вычислить. Если все реальные Q=0 — честно показать причины, положительную ветку тестировать официальным условным примером.
9. Старый пример R=7000,H=1200,Q=5355 неверен: по формуле кейса UNC≈0.07142857, Radj=6500,Q=5525. Не превращать старые примеры из переписки в эталоны.
10. Q нелинеен (общая uncertainty, пороги, floor): вклад зоны даётся в ΔC/E, а не как сумма «точных Q каждого пикселя». Контрфактический пересчёт допускается отдельно и не подменяет основной.
11. Сравнение разных периодов не даёт автоматическое «аннулировано N старых кредитов». Помечать как новое наблюдение/период; DOWNGRADED допускается лишь для сопоставимых оценок с явным правилом сравнения.

### Общие интерфейсы и владельцы

После G0 расположения фиксируются; до G0 это согласуемая архитектура, не уже существующие файлы.

| Владелец | Единственная зона записи | Отдаёт |
|---|---|---|
| RS | `rs/case2/`, `rs/tests/case2/`, role docs | RasterAnalysis: площади, годовые запасы, E, per-cell SD/weights, зоны, evidence, artifacts |
| Trust (бывший Blockchain) | `carbon/`, `carbon/tests/`, role docs | Interval + baseline + Q + claim comparison + report builder + integrity verifier |
| Backend | `backend/`; новые `contracts/v2/`, `fixtures/v2/` в G0 | API, jobs, persistence, adapters, artifact/report serving |
| Frontend | `frontend/` | UI /lens, generated v2 types, component/browser tests |
| TL | `docs/roadmaps/`, coordination docs; согласованные CI/config | метод freeze, approvals, merge, deploy, research/pitch |

Общие v1 файлы не менять. Новый v2 contract изменяет только Backend отдельным явно согласованным diff с consumer-review. Python package `carbon/` не импортирует FastAPI/web3/React. RS получает CF через параметры, но не вычисляет Q. Backend вызывает RS и carbon, не дублирует формулы. Frontend отображает числа API, не пересчитывает их.

### G0 — общий договор до расходящихся реализаций

Backend создаёт `feat/lens-g0-contracts`, рано открывает Draft PR. RS согласует raster schema, Trust — interval/Q/report, Frontend — поля экрана, TL — смысл. В G0 фиксируются:

- v2 request/result/error/RS/internal schemas и contract fixtures;
- `schema_version`, `method_version`, версия dataset, source manifest hash;
- контур WGS84 Polygon/MultiPolygon, 0<A≤2000 га, целые годы 2019≤start<end≤2024;
- model/observed year отдельно от даты Sentinel-снимка; AGB/углерод/CO₂e и единицы явно;
- независимые оси: job_state; calculation_status; evidence_status; claim_status; passport/anchor status;
- job: QUEUED/RUNNING/SUCCEEDED/FAILED; calculation: AVAILABLE/UNAVAILABLE; evidence: SUFFICIENT/REVIEW_REQUIRED/INSUFFICIENT;
- причины нулевого Q: NON_POSITIVE_RELATIVE_RESULT, UNCERTAINTY_TOO_HIGH, ROUNDED_TO_ZERO; отсутствие данных — отдельные причины unavailable;
- claim: NOT_PROVIDED/NOT_COMPARABLE/SUPPORTED_BY_CASE/PARTIALLY_SUPPORTED_BY_CASE/NOT_SUPPORTED_BY_CASE/UNASSESSABLE;
- никаких публичных INVESTABLE или «доказано мошенничество»; отрицательный E/положительный E показывается отдельной характеристикой изменения;
- artifact: id, role, sha256, media_type, bbox/crs, resolution, unit, provenance, API URL; browser не читает произвольные local paths;
- запрос результата включает snapshot параметров и версии входов; дата запуска отдельно от детерминированного scientific content hash;
- план method freeze: основной способ uncertainty и sensitivity варианты утверждает TL вместе с RS/Trust до выдачи реальных Q.

Не ждать G0 без дела: каждый изучает P0, пишет локальные чистые функции/тесты своей роли. Не сливать несовместимые интерфейсы и не копировать чужую незавершённую ветку. После G0 типизированные заглушки позволяют Backend/UI работать до merge RS/Trust.

### Сквозные сценарии приёмки

| ID | Вход | Обязательный смысл |
|---|---|---|
| S1 | RU_TVER_01, 2019–2024 | Контроль по GFC; отсутствие потерь GFC не гарантирует постоянную биомассу или положительный Q |
| S2 | RU_MORDOVIA_03, 2020–2022 | Изменение + свидетельства пожара августа 2021; площадь зоны и вклад, без выдуманных «50%» |
| S3 | RU_VOLOGDA_02, 2019–2024 | Потери покрова; причина не установлена без достаточных evidence |
| S4 | RU_MORDOVIA_04, 2019–2024 | История/последующая динамика; восстановление объявляется только по результатам |
| S5 | CHECK_TRANSFER_01, 2020–2024 | Подучасток ~808.85 га; baseline родителя на реальную площадь; новый нарисованный допустимый контур тоже работает |
| S6 | Облачная сцена сентября 2021 из data | Плохая оптика отдельно от CCI coverage; объяснение ограничений, подходящий альтернативный снимок |
| S7 | Контур, выходящий за доступное покрытие | Частичный результат и q=null; это проверка границ, а не подмена растра |
| S8 | Реальный анализ + user/demo claim | Сравнить одинаковые контур/период/пул/единицы; input label; не менять рассчитанный Q под заявление |
| S9 | Изменённая копия отчёта / искусственный сбой API | Явно тестовый негативный probe; источник data неизменён, hash mismatch или понятная ошибка |

Обязательные абстрактные unit-векторы (например NaN, граница H/R) — логические тесты, НЕ альтернативные научные данные. Помечать UNIT_TEST_VECTOR и не показывать как реальные AOI; основной числовой эталон Q=395 взят из doc.

### Git, PR и остановки Claude

Перед началом: `git status --porcelain`; если есть чужие правки — не удалять, согласовать или создать отдельный worktree. Не делать reset --hard, rebase, force push, прямой push main, перемещение тегов.
На чистом дереве:

```bash
git fetch origin --tags --prune
git switch main
git pull --ff-only origin main
git merge-base --is-ancestor p0-integrated-v1.0.0 HEAD
git rev-parse HEAD
git status -sb
```

Затем новая ветка этапа через git switch -c. Один этап = один содержательный PR, несколько тематических коммитов допустимы. Черновик PR публикуется после первого проверяемого результата; перед review обновить описание и дождаться checks актуального HEAD. Без прав GitHub — выдать ветку, HEAD и готовое тело PR, не утверждать, что PR создан.

После готовности этапа Claude выводит: ROLE/STAGE READY FOR REVIEW, полный SHA, PR, changed files, команды/результаты, что реально запускалось, provenance/frozen proof, ограничения, consumer и следующий шаг. Затем останавливается: «Этап завершён; после review/merge напишите ПРОДОЛЖАЙ <следующий этап>». Сам не запускает следующую стадию, не делает Ready/Approve/merge.

Reviewer проверяет отдельный временный worktree на точном SHA без изменений и выдаёт APPROVE или REQUEST CHANGES с file:line, эффектом и минимальным исправлением. Официальный GitHub review человек ставит вручную; автор не утверждает свой PR. Ready + squash merge — только TL. После замечаний review привязан к новому SHA.

Каждый этап проверяет свою suite, общий pytest, diff --check, scope и исходные hashes. Финальная интеграция явно запускает ВСЕ suite: root pytest не заменяет backend/rs/carbon tests. Исходные counts P0 (139 shared, 71 RS, 110 Frontend, Backend 123+3 skips Windows /124+2 при symlink) — ориентир для регрессии, не потолок: новые тесты увеличивают counts. Не требовать ровно прежних чисел после новых тестов. Нельзя лечить падение массовыми skips.

### GitHub-ориентиры — полный список

- [carbonplan/forest-offsets](https://github.com/carbonplan/forest-offsets): структура анализа offset-проектов, прозрачность допущений.
- [carbonplan/forest-risks](https://github.com/carbonplan/forest-risks): организация исследовательского кода и sensitivity; не переносить модели США.
- [carbonplan/forest-risks-web](https://github.com/carbonplan/forest-risks-web): карта, слои и объяснение показателей; не копировать брендинг.
- [developmentseed/titiler](https://github.com/developmentseed/titiler): растровая выдача, только если текущие PNG/GeoJSON не справляются.
- [sentinel-hub/eo-learn](https://github.com/sentinel-hub/eo-learn): организация масок и временных задач.
- [openforis/sepal](https://github.com/openforis/sepal): организация геообработки и источников.
- [moja-global/FLINT](https://github.com/moja-global/FLINT): модульный углеродный учёт.

Каждый разработчик выбирает 1–2 релевантных примера и за ограниченное время записывает «идея → наш модуль → лицензия/commit → что изменили → тест пользы». Не обязан заимствовать код: «не подходит, переиспользуем P0» — нормальный итог. При копировании нужны конкретные URL/commit/файлы и attribution в docs роли; нет явной лицензии — код не копировать. Не устанавливать все семь проектов, OpenCV, FLINT, TiTiler или ML ради названия.

## Личная миссия

Ты Backend Developer и Integration Owner: превращаешь контур+период в воспроизводимый расчёт, карту и паспорт. Владелец вычислений — RS/carbon, а не route handler. Ты отвечаешь за согласованность чисел, безопасную выдачу файлов, сохранность истории и понятные сбои.

Стек: действующий FastAPI/Pydantic и существующие DB/worker/jobs P0; не вводить Redis/Celery/Postgres/Docker как обязательные зависимости, если P0 достаточно. Сначала посмотри фактическую архитектуру.
Ориентиры: TiTiler для raster serving только при необходимости, SEPAL для job pattern, FLINT для границ модулей. Копирование чужого научного engine запрещено.

## B0 / G0 — общий v2 contract и первый вертикальный каркас

Ветка `feat/lens-g0-contracts`. Это первый shared PR и первая точка согласования всей команды.

1. Прочитай doc, P0 API/security/worker/schema. Запиши reuse/gap по каждому модулю.
2. Создай отдельные `contracts/v2/` и `fixtures/v2/`, не трогая frozen v1. Согласуй пути с CLAUDE.md владельцев.
3. В одном G0 определить JSON Schema/OpenAPI, внутренний RS result, per-cell uncertainty artifact, carbon result, artifact/report manifest. Не ограничиваться только HTTP schema.
4. Утвердить ownership `rs/case2` vs `carbon` vs backend; pipeline functions и места импорта. Чтобы Trust не ждал RS, вход определяется schema.
5. Fixtures scientific реальных результатов не выдумывать. Для wire-format использовать явно UNIT_TEST_VECTOR/CONTRACT_FIXTURE и официальный пример из doc; реальные AOI golden появятся после RS+Trust. Надпись fixture видна в UI.
6. Добавить минимальный v2 job skeleton и contract tests, сохраняя v1 guards.

### Минимальные маршруты для freeze G0

Предложение, которое в G0 можно уточнить один раз; после freeze все роли используют один согласованный набор:

- `GET /api/v2/catalog`: AOI geometry/coverage, доступные годы, source/method versions.
- `POST /api/v2/analyses`: geometry или catalog AOI, годы, optional claim+его metadata, Idempotency-Key → 202 analysis_id/status_url.
- `GET /api/v2/analyses/{id}`: job progress + typed result когда готов; polling без смешения job/evidence/calculation.
- `GET /api/v2/analyses/{id}/artifacts/{artifact_id}`: только manifest-listed.
- `GET /api/v2/analyses/{id}/report?format=json|html`: готовый отчёт.
- `GET /api/v2/analyses/{id}/proof`: hashes/version links; anchor поля nullable с честным статусом NOT_REQUESTED/PENDING/CONFIRMED/FAILED.
- история/сравнение версий может быть частью результата; лишние endpoints без потребности не добавлять.

Для каждой mutation перенеси P0 discipline headers/actor/session после проверки существующей модели; не изобретай ещё одну auth. Геометрии canonical, content limits, latitude/longitude validation. Path ids opaque.

### Обязательные поля

```text
request: geometry, year_start, year_end, claimed_units?, claim_scope?, claim_origin?
identity: analysis_id, input_hash, schema_version, method_version, dataset_hash, code_sha
areas: requested_ha, calculated_ha, missing_ha, parent_parts[]
coverage: biomass_fraction, uncertainty_fraction, baseline_fraction, optical_paired_valid_fraction
timeline[]: year, mean_agb_tdm_ha, mean_carbon_tc_ha, total_carbon_tc, area_ha, coverage, source_ref
change: delta_carbon_tc, eproj_tco2e, eproj_tco2e_ha_year, sign_convention, pool
uncertainty: lower, upper, method, interval_kind, assumptions, sensitivity_refs
units: ebase, lk, r, h, ratio?, unc?, radj?, buffer?, rounding_residual?, q?, reason_codes[]
claim: status, origin, comparable, gap_units?, supported_share?, scenario_gap_values?
scenario_values: price_parameters_ref, low?, base?, high?, unit=RUB
zones[]: area_ha, contribution_e_tco2e, cause, date_range, evidence_refs, geometry/artifact_ref
passport: content_hash, report_hash, previous_hash?, comparison_scope, created_at
sources[], limitations[], artifacts[]
```

Названия окончательно фиксируются G0; размеры больших arrays уходят в hash-verified artifact. У science status и money fields nullability заранее согласована.

### Ошибки

400/422 — invalid geometry/period/claim; 404 — unknown analysis/artifact; 409 — idempotency conflict; 503 — source unavailable или artifact integrity failure; точные code/status фиксирует OpenAPI.
Partial coverage — допустимый scientific outcome с result и q=null, не падение worker. Оптика низкого качества — evidence warning, не автоматический q=null.
Ошибки не содержат stack, secrets или локальные пути.

Draft PR публикуй после schema+примеров. Consumers: все три разработчика и TL. При согласовании правь только G0, не заставляй consumers самостоятельно менять shared файлы.
Merge gate: schema validates examples, v1 unchanged, fields вычислимы, tests и approvals. После merge останавливаться до B1.

## B1 — реальная асинхронная оркестрация и сохранение результатов

Ветка `feat/lens-backend-analysis`. Depends G0; можно разрабатывать на stubs, итоговый APPROVE только с merged RS-1/Trust-1.

1. Вызов RS→carbon interval→baseline/Q/claim; типизированные adapters, без научных формул в routes.
2. Snapshot geometry, years, source/parameter hashes, method/code version перед стартом. Отделить supplied computation от external retrieval proof/cache.
3. Job durability/restart/polling; timeout/failed причина; одинаковый key/body→тот же job, другой body→409. Canonical request hash и inputs hash не смешивать.
4. Параметры заявления входят в request identity, но не влияют на numerical science result; scientific caching может reuse geometry/period/manifest.
5. Сохранять immutable result; concurrent/stale worker не переписывает новый passport. Atomic file/result publish.
6. File delivery: allowlist root, path traversal/symlink escape rejection, sha256 перед выдачей, Content-Type, size limits, CORS.
7. Offline replay: явно COMPUTED_FROM_SUPPLIED_DATA vs CACHED_REPLAY; REAL dataset не называть SYNTHETIC из-за локального cache.
8. При отсутствии оптического evidence сохранять доступный carbon output и reasons; missing SD не подменять H=0.
9. Все 15 целочисленных пар 2019–2024 допускаются, если покрытие есть; отсутствие сцены нужного периода отражать честно.
10. Не принимать arbitrary source URL от клиента (SSRF), не разрешать arbitrary shell jobs.

Tests B1:
- POST→poll→result, persistence reload/restart, repeated key;
- invalid/new polygon, full/partial/outside/multi-parent with no double count;
- null vs 0, optical low vs biomass missing;
- concurrent requests, worker failure, timeout;
- CORS trusted/untrusted, actor/session, error JSON;
- path traversal/symlink/artifact corruption;
- actual RS+Trust payload equality.

Draft PR после сквозного typed fixture path. Перед review заменить acceptance evidence реальным анализом S1/S2/S5, без silent fallback.
Review: Frontend запускает API/browser; RS/Trust проверяют invariants payload. CI test commands явно включают backend, rs/case2, carbon.
Не менять workflows без разрешения TL: отдельный `.github/workflows/case2.yml` может быть поручен TL в B1, с явным scope. Existing CI не ослаблять.

## B2 — паспорт, история, уведомления внутри сервиса и deployment runbook

Ветка `feat/lens-backend-passports`. Depends B1, Trust-2, RS-2; skeleton report adapter можно готовить параллельно.

1. Подключить Trust report builder; JSON+HTML download, те же API values. Static HTML автономен, ссылки на истекающие session URLs не ломают архивный отчёт.
2. Manifest reference и API proof; предыдущие паспорта read-only. Запрос предыдущего анализа не мутирует его статус научного результата.
3. Реанализ в новом периоде — linked observation с явным different_period. Сопоставимые версии могут иметь comparison result DOWNGRADED по rule из G0; threshold не хардкодить в UI.
4. События: ANALYSIS_COMPLETED, EVIDENCE_REVIEW_REQUIRED, PASSPORT_SUPERSEDED, PASSPORT_TAMPER_DETECTED; downgrade только при сравнимости. In-app журнал и индикатор достаточно.
5. Реальный email/Telegram/Webhook не входит в core и требует отдельного разрешения TL, получателей/секретов/повторных доставок. Демо события помечены, не отправлять людям без разрешения.
6. Старые v1 credit states не переименовывать в passport status; новый пожарный сигнал не должен сам списать старые credits.
7. Основной сервис без chain. Если TL разрешил Trust-3, отдельный adapter с authentic receipt/readback; mock proof не выдавать за on-chain.
8. Дать точные команды install/start/worker/seed/stop для Windows и Linux из фактического repo; запустить их в clean clone, не изобретать entrypoints.
9. .env.example без secrets; demo session не запекать в JS bundle. Backend same-origin proxy или согласованный CORS; runtime config без доступа браузера к RPC.
10. Опубликовать измеренный runtime/memory/time для нового контурного запроса, report size и cache behavior.
11. Для TL deployment checklist: env, bind/ports, persistent runtime path, dataset availability, same-origin routing, health, доступность внешнего URL. Не требовать chain для открытия /lens.

Draft PR: первый настоящий скачиваемый паспорт S5 и история.
Review: Trust report hashes, Frontend live download/proof/errors, RS карту.
Секреты/деплой — только в рамках явно предоставленной конфигурации и разрешения TL.

## B3 — финальная интеграция и независимая проверка UI

Ветка `chore/lens-final-integration` только если нужны changes runbook/integration tests; пустой PR не создавать.
Depends обязательные RS-1..3, Trust-1..2, Frontend-1..3 и B2 merged.

1. Clean clone актуального main с tags, подтвердить dataset checksum.
2. Установить версии Python/Node по repo, root npm ci и frontend npm ci в соответствующих каталогах.
3. `python -m pytest -q`; `python -m pytest backend -q -rs`; `python -m pytest rs/tests -q`; `python -m pytest carbon/tests -q`; `npm run check:abi`; в frontend `npm run verify`.
4. Browser suites P0 и новая `e2e/lens.spec.ts` на реальном backend; фактический browser/channel записать. Не путать installation Chromium с channel Chrome/Edge.
5. Прогнать S1–S9; добавить сломанный payload, неизвестный enum, повреждённую копию runtime artifact, мобилку, reload, двойной click, CORS.
6. Числа UI=API=report; новый drawn polygon без code edits; process offline; online retrieval proof отдельный.
7. Если chain scope включён — Anvil actual receipts/readback, v1 regression; если выключен — явно NOT_RUN/OUT_OF_SCOPE, не «всё on-chain прошло».
8. Проверить main CI, но не выдавать отсутствие workflow за pass. Source retrieval outage — limitations и оставшийся gate.
9. Independent Frontend review exact HEAD: APPROVE или file:line+effect+minimal fix. Сам ничего не править в frontend.
10. TL получает матрицу, полный release SHA, проверенный runbook, no-secrets/clean tree, known limitations. Команда «готово» не заменяет фактических тестов.

Финал: `BACKEND INTEGRATION VERIFIED — READY FOR TEAM LEAD RELEASE CHECK`, не «100/100 гарантировано».

## Мини-промпты Claude

### Старт

```text
Ты Backend Developer и Integration Owner Carbon Lens. Прочитай ROADMAP_BACKEND.md, все doc и фактический P0. Начни только B0/G0: отдельный v2 contract/internal schemas и typed fixtures, сохрани frozen v1. Согласуй RS/Trust/Frontend поля и независимые статусы. Открой Draft PR рано, выдай URL/SHA и список вопросов consumers. После тестов и contract-ready отчёта остановись. Не Ready/merge и не реализуй чужую научную логику.
```

### Следующий этап

```text
ПРОДОЛЖАЙ B1 (либо B2/B3 — только явно указанный этап). Проверь merged зависимости и clean main, создай новую ветку roadmap. Используй RS/carbon как adapters, без дублирования формул. Выполни этап, реальные проверки, commit/push/Draft PR, дождись CI актуального HEAD. Остановись с dependency/evidence отчётом.
```

### Consumer-review

```text
Независимо проверь Frontend PR на переданном полном SHA в отдельном временном worktree. Ничего не меняй. Запусти настоящий Backend из main и /lens: S1–S9, API/report/UI equality, неизвестные enums, ошибки, CORS, polling, reload, double-click, mobile. Не принимай fixture E2E за live integration. Выдай APPROVE либо точный REQUEST CHANGES; официальный review и merge делает человек.
```
