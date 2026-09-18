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

# BountyTeam Carbon Lens — Carbon, Uncertainty & Trust — бывший Blockchain

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

## Личная миссия — Carbon Methodology, Uncertainty & Trust Owner

Ты бывший Blockchain-разработчик. Теперь владеешь `carbon/`: неопределённость → baseline → единицы → сравнение заявления → паспорт. Это обязательный математический центр MVP, а не факультативная задача. RS считает площади/stock/E и передаёт per-cell данные; ты один владелец итогового интервала, Q и денежного отображения.

Python + NumPy и существующие библиотеки сериализации/шаблонов; не переписывать расчёт в Solidity. Report: canonical JSON + самодостаточный HTML с печатью в PDF браузером; отдельная PDF-библиотека только если реально нужна и успевает пройти тесты.
Ориентиры: forest-offsets, forest-risks, FLINT; изучить паттерны прозрачности и модульности, не их научные параметры.

## Формулы, обязательные для всех твоих модулей

Сверено с doc, «Постановка задачи», с.4–6. Параметры читать из CSV, включая utf-8-sig, не загружать из GitHub.

```text
C_t = Σ(AGB_i,t × CF × area_i_ha), CF=0.47
ΔC = C_end − C_start
Eproj = −ΔC × (44/12)
e = Eproj / (calculated_area_ha × (end−start))
Ebase = −Σ_parts(area_part × baseline_delta_tc_ha_for_period) × (44/12)
R = Ebase − Eproj − LK; LK=0
H = max(Eproj−L, U−Eproj)
```

Входы finite, L≤Eproj≤U, H≥0, A>0, Δt>0, полностью покрыты CCI, требуемые SD и baseline.
- missing/invalid → Q unavailable; не преобразовывать NaN в ноль;
- R≤0 → Q=0; ratio=null, без деления;
- R>0, H/R≥1 → Q=0 по отдельному stop-rule;
- иначе:

```text
UNC = min(1, max(0, H/R − 0.10))
Radj = R × (1−UNC)
B = Radj × 0.15
Q = floor(Radj × 0.85)
V_p = Q × p, p∈{500,1500,4000}
```

UNC НЕ фиксированные 10%: 10% — допускаемый порог без вычета. Сохранить rounding residual: Radj−B−Q. На stop-rule H/R≥1 не показывать обычный waterfall так, будто он дал ненулевой Q.

Baseline parent trajectory уже в CSV, для подучастка применить удельные изменения к его площади. При пересечении AOI — неперекрывающиеся части. Не пересчитывать baseline под конкретное заявление. Даты начала проекта в dataset неизвестны: говорим «результат относительно сценария», не «доказанный эффект действий владельца».

## Trust-0 — аудит методики и review G0

Выпиши точную формулу/единицы/знак и пример Q=395. С RS согласуй per-cell payload и method freeze. Backend передай поля waterfall, q nullable, причины unavailable, claim comparability, report hashes.
Назови расположение `carbon/` и отсутствие зависимостей от HTTP/web3. Проверяй фактический P0 contract перед решением о reuse anchoring.

## Trust-1 — uncertainty + baseline + units: один полный расчётный engine

Ветка `feat/lens-carbon-engine`. До G0 можно делать pure functions; merge требует G0 и согласованного uncertainty метода. Не ждать real RS для unit-тестов, но перед APPROVE проверить его реальный payload.

### Неопределённость: выполнить в этом этапе, не оставить без владельца

1. Получить SD для обеих дат, площадь и пространственные координаты клеток, не только среднюю SD.
2. При самостоятельной разности исследовать временную зависимость:
   var(Δb_i)=s0_i²+s1_i²−2ρ_t s0_i s1_i.
   ρ_t — подписанное сценарное допущение, не извлечённая из воздуха научная калибровка.
3. Исследовать пространственную зависимость: вариант independent cells и обоснованный block/correlated вариант. Указать размер блоков, grid/CRS и проверку sensitivity. Независимость не называть автоматически нижней границей всех возможных ошибок.
4. Ошибки суммировать с площадными весами и ковариацией, не делить на sqrt(N) без предположения независимости.
5. Допустим аналитический расчёт или fixed-seed Monte Carlo. Для вероятностного интервала назвать распределение, параметры, корреляции и отсутствие эмпирической калибровки; для сценарного диапазона явно написать «сценарный», без обещания 95% покрытия.
6. Основной метод и параметры утверждаются TL до просмотра «удобных» Q; сохранить method_version. Не выбирать модель ради положительных единиц.
7. CCI Change 2019–2020 SD использовать для исследования согласованности (зависимости уже учтены издателем); это не независимые наземные измерения.
8. Неопределённость baseline отдельно как sensitivity; основной baseline и LK фиксированы по кейсу.
9. Не применять SCL как механическую маску CCI stock. Низкая optical quality влияет на evidence status; неполный обязательный numeric input — на availability Q.

### Engine и сравнение заявления

Функции отдельно: compute_interval, compute_baseline, compute_units, compare_claim.
`claimed_units`: optional конечное неотрицательное число (лучше целое с явной валидацией), источник USER_INPUT или DEMO_INPUT. Вход содержит контур/период/пул/единицы заявления. Если не совпадают — NOT_COMPARABLE, gap=null.

```text
gap_units = max(claimed_units − Q, 0)
supported_share = min(Q/claimed_units,1)  [только claimed_units>0]
gap_value_p = gap_units × p
```

Claim отсутствует → NOT_PROVIDED; 0 → share=null и «нулевое заявление»; Q=null → UNASSESSABLE, все сравнения null.
Q≥claim>0 → SUPPORTED_BY_CASE; 0<Q<claim → PARTIALLY_SUPPORTED_BY_CASE; Q=0<claim → NOT_SUPPORTED_BY_CASE. Это арифметический статус, рядом отдельно REVIEW_REQUIRED если evidence слабый. Не «одобрено к покупке».
Заявление не меняет RS, baseline, interval и Q. Не называть gap_value финансовым VaR или фактическим убытком.

### Тесты этапа

- официальный пример: R=517,H=103.4,ratio=.2,UNC=.1,Radj=465.3,B=69.795,Q=395;
- R<0,R=0; ratio 0,.1,.1+ε,1−ε,1,1+ε;
- floor/остаток, без раннего округления; IEEE пограничные эффекты задокументировать;
- A=0,Δt=0,NaN,Inf,отсутствующий SD/coverage/baseline;
- subpolygon и multi-parent, отрицательная baseline trajectory, чтение готового clipping из таблицы;
- одинаковая SD при ρ_t=0/1, постоянные ошибки клеток, dependence influence, deterministic replay;
- claim absent/0/negative/nonfinite/mismatch/equal/lower/higher, Q null/zero;
- E>0 может сочетаться с R>0 при более плохой baseline: не объявлять физическое накопление;
- H≥R stop-rule не заменяется UNC=.9;
- inputs/output типизированы, без HTTP/chain imports.

Draft PR после official example и базовых interval boundary tests.
Review: RS проверяет SD/площадные веса/ковариацию; Backend интерфейс; Frontend waterfall; TL основной метод.
Evidence: input→expected vectors, ручной пересчёт Q=395, первые реальные AOI, assumptions и limitations.
После merge — Trust-2.

## Trust-2 — углеродный паспорт, integrity и исследование

Ветка `feat/lens-passport-research`. Depends Trust-1, RS-1 outputs и G0 artifact contract; final real-map report — RS-2.

1. Canonical scientific payload: geometry hash, годы, пул, source checksums, parameters snapshot, method/code version, stock/E/interval/baseline/Q/claim.
2. Не смешивать stable content hash с created_at/run_id. Определить сериализацию, порядок ключей, числа/UTF-8/NaN rejection и format version; использовать уже надёжный P0 механизм, если совместим.
3. Report builder читает готовый typed result; не пересчитывает formulas второй раз. Форматы JSON + автономный HTML с локально встроенными картами/графиком.
4. В отчёте: requested/calculated/missing area; optical quality отдельно; annual timeline, E/e, interval assumptions, signed baseline comparison, deductions/reserve/rounding, Q/prices, input claim label, explanation/limitations, sources/licenses/versions.
5. Ровно те же числа и статусы в API/HTML/canonical; escapes для любых пользовательских строк, без scripts/локальных путей/secrets.
6. SHA-256 passport payload, manifest и report bytes — разные поля. Никакого self-referential hash: detached integrity manifest/receipt. Проверять относительно заранее сохранённого trusted hash, не только пары «поддельный файл + его новый manifest».
7. Previous version hash связывает версии; сравнимость явно оценивается. Изменение периода → NEW_OBSERVATION, а не автоматическое списание Q. Старая версия остаётся read-only.
8. Integrity utility принимает скачанный файл и доверенный reference; tampered copy test. Не обещать предотвращение перепродажи.
9. Research: control Тверь и disturbed Мордовия; одинаковые AOI/периоды, таблица spatial/temporal assumptions→[L,U],H/R,Q,V; strict/relaxed mask от RS→quality/zones.
10. Исследование baseline: официальный вариант и явно исследовательский альтернативный (например flat baseline из той же data). Основной Q всегда по baseline.csv; toggle не переписывает паспорт.
11. Отчёт о расхождениях CCI/GFC/Sentinel/MODIS, без объявления одного продукта ground truth.
12. Windows explicit UTF-8, portable paths, deterministic numeric replay. HTML может содержать run timestamp, поэтому его byte hash версии отличается честно.

Tests: report/API equality, missing artifacts, wrong hash, Unicode, HTML injection, offline open, 4 AOIs+S5, comparisons null/0.
Draft PR: первый реальный полный паспорт S5 + integrity utility.
Review: Backend serving/schema, Frontend downloading/labels, RS provenance, TL research conclusions.
После merge обязательная роль готова; помочь интеграции и защите.

## Trust-3 — blockchain anchor, только по отдельному GO от TL

Ветка `feat/lens-passport-anchor`; исключительно после рабочего обязательного MVP. При дефиците времени отменяется целиком без потери core.

Аудитируй фактические возможности P0. Если старый registry не подходит, не подменяй evidence_hash новым смыслом; предложи отдельный additive adapter/контракт и новый ABI вне frozen v1, согласуй с TL.
Минимальное anchoring: хеш canonical manifest уже связывает geometry, inputs, method и previous hash; нет необходимости хранить растры или каждый параметр on-chain.
Backend adapter читает receipt + event + state; обязательны chain_id, contract_address, tx_hash, block и readback. Pending≠anchored; failed≠verified.
Тесты: authorized/unauthorized writer, duplicate/idempotency, hash mismatch, version linkage, receipt/event/readback match. Keys только локальные demo через env.
Anvil — «локальная демонстрационная сеть», не публичное независимое долговременное доказательство. Без сети паспорт и Q работают. Не обещать публичную неизменность на управляемом локальном стенде.
UI/Backend wiring в отдельных owner PR, не редактируй frontend сам.
Не marketplace, не trading, не automatic credits retirement, не calculation on-chain.

## Мини-промпты Claude

### Старт

```text
Ты Carbon Methodology, Uncertainty & Trust Owner, бывший Blockchain-разработчик. Полностью прочитай ROADMAP_TRUST_BLOCKCHAIN.md, doc и methodology CSV. Изучи P0 и согласуй G0 с RS/Backend. Реализуй только Trust-1 в carbon/: итоговый uncertainty с явными допущениями, baseline, точный UNC/Q, claim comparison. Сначала покажи формулы и предложенный основной метод TL; не подбирай его под положительный Q. Official example Q=395 обязателен. Commit/push/Draft PR после проверок, без Ready/merge; затем остановись.
```

### Следующий этап

```text
ПРОДОЛЖАЙ Trust-2. Предыдущий этап смержен, обнови main и создай ветку roadmap. Сделай report/provenance/integrity и исследовательскую таблицу только из официальных данных. Сверь числа API/report, прогони carbon и общие тесты, открой Draft PR и остановись. Solidity пока не разрешён.
```

### Опциональный anchor

```text
Team Lead разрешает Trust-3: обязательный MVP уже принят. Сначала проверь фактический P0 registry и предложи минимальный совместимый anchoring. Не меняй frozen ABI, не добавляй trading. Реализуй только согласованный объём, проверь реальный receipt/event/readback на Anvil, явно укажи локальный demo-статус, открой Draft PR и остановись.
```

### Завершение роли

Выдать `TRUST COMPLETE — FORMULAS/UNCERTAINTY/PASSPORT VERIFIED`: method_version, HEAD, PR, official vector, реальные Q (включая нули), таблица sensitivity, report hashes, доказательство отсутствия certified/guaranteed claims и список нерешённых ограничений.
