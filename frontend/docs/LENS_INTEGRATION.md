# Carbon Lens — граница интеграции интерфейса

Документ для Backend, Trust, RS и Team Lead. Он фиксирует, что интерфейс `/lens` читает сам, что ждёт
от сервиса, и какие расхождения обнаружены при работе против живого стенда.

Владелец файла: Frontend. Область записи — только `frontend/`.
Состояние контракта: типы выровнены по `contracts/v2/api-models.v2.schema.json` на SHA Backend
`e9817d0144569731e3a98c7af6c916cf55a510cf` (PR #15).

## 1. Что интерфейс читает сам, а что получает от сервиса

| Источник | Что берётся | Где в коде |
|---|---|---|
| `data/areas.csv`, `data/areas.geojson` | участки, регион, площадь, годы, `baseline_id`, bbox, контур — для офлайн-каталога | `src/lens/data.ts` |
| `data/sample_requests.geojson` | официальный подучасток `CHECK_TRANSFER_01` и его площадь | `src/lens/data.ts` |
| `data/scenes.csv` | сцены Sentinel-2: дата, облачность, доля пригодных пикселей | `src/lens/data.ts` |
| `data/events.csv` | записи о продуктах гарей: даты, погрешность, число пикселей, ограничения, ссылка | `src/lens/data.ts` |
| `data/methodology/baseline.csv` | базовая линия по годам, включая сценарий до 2029 года | `src/lens/data.ts` |
| `data/methodology/parameters.csv` | CF, 44/12, UNC_allowance, порог H/R, BUF, LK, цены 500/1500/4000 | `src/lens/data.ts` |
| `data/sources.csv` | продукты, версии, лицензии, DOI, атрибуция, ограничения | `src/lens/data.ts` |
| **Сервис** | запас, ΔC, Eproj, базовая линия в CO₂-экв., интервал, R, вычеты, резерв, **Q**, покрытия, зоны, артефакты, паспорт, proof | `src/lens/httpClient.ts` |

Интерфейс **не вычисляет** научные величины. Единственная арифметика на экране: `Q × цена` (цена из
`parameters.csv` или введённая пользователем и помеченная «ваш сценарий») и показ уже полученного
`claim.gap_units`.

## 2. Граница адаптера

```ts
interface LensApiClient {
  kind: 'fixture' | 'http';
  getCatalog(signal?): Promise<Catalog>;
  measureArea(geometry, signal?): Promise<AreaMeasurement>;
  createAnalysis(body, { idempotencyKey, signal?, scenario? }): Promise<AnalysisAccepted>;
  getAnalysis(analysisId, signal?): Promise<Analysis>;          // job_state + result одним ресурсом
  getProof(analysisId, signal?): Promise<Proof>;
  getReport(analysisId, 'json', signal?): Promise<Report>;
  getReportHtml(analysisId, signal?): Promise<string>;
  getArtifact(artifact, signal?): Promise<ArtifactPayload>;     // sha256 проверяется до показа
}
```

Живой клиент — `src/lens/httpClient.ts`, офлайн-набор — `src/lens/fixtureClient.ts`. Экраны не знают,
кто ответил. Режим выбирается конфигурацией: живой сервис по умолчанию, офлайн-набор только по
`?lens=fixture` или `VITE_LENS_API_MODE=fixture`. Автоматической подмены при сбое сервиса нет.

## 3. Расхождения, найденные на живом стенде PR #15

Проверено в браузере против `backend.serve` на SHA `e9817d0`, режим CONTRACT_FIXTURE.

| № | Наблюдение | Следствие для интерфейса | Что нужно от Backend |
|---|---|---|---|
| L1 | В `Access-Control-Allow-Headers` нет `Authorization`. Запрос с bearer-заголовком не доходит: браузер блокирует preflight | Добавлена схема доступа `demo-header`: `?auth=demo` передаёт токен заголовком `X-Demo-Session`. По умолчанию — bearer, как в roadmap | Разрешить `Authorization` в CORS, тогда `?auth=demo` перестанет быть нужен |
| L2 | Маршрута `POST /areas/measure` нет (404) | Площадь произвольного контура показывается как **предварительная оценка** браузера с явной подписью; предел 2000 га проверяется по ней и перепроверяется сервисом при расчёте | Добавить измерение контура или письменно зафиксировать, что клиент не проверяет предел локально |
| L3 | Маршрутов `POST /auth/login` и `GET /auth/me` нет (404) | Вход в живом режиме: роль выбирается по перечисленным учётным записям, а введённый пароль используется как токен сессии сервиса. В сборку ничего не зашивается, в URL токен не попадает | Опубликовать вход и `/auth/me` с ролями `owner`/`verifier`/`investor` |
| L4 | `evidence.warnings[]` — массив строк (нарушение METHOD FREEZE v1 п.18) | Строка принимается и показывается с кодом `UNSTRUCTURED_WARNING` и серьёзностью `WARNING`; сортировать и подписывать по коду нельзя | Перейти на `{code, severity, message, details}` |
| L5 | `zones[]` пуст, у `Zone` нет `geometry` | Карта не может обвести зону: показывается «зоны не выделены» с объяснением | Либо `Zone.geometry`, либо артефакт `zones` с `zone_id` в properties |
| L6 | `Areas.area_difference_ha` отсутствует (METHOD FREEZE v1 п.17) | Поле показывается только когда приходит; иначе строка скрыта | Добавить знаковую разность |
| L7 | Нулевое заявление возвращается как `SUPPORTED_BY_CASE` (METHOD FREEZE v1 п.12) | Интерфейс показывает статус сервиса и рядом предупреждение, что нулевое заявление не является подтверждённым | Вернуть `NOT_APPLICABLE` + `NO_POSITIVE_CLAIM` |
| L8 | Артефакт `cells` содержит реальную геометрию ячеек и значения по годам | Карточка ячейки CCI построена поверх него; целостность проверяется по sha256 | Сохранить формат; добавить `zone_id` в properties, когда появятся зоны |

Проверено и совпадает: маршруты каталога и анализа, объединение job+result, идемпотентность и 409,
конверт ошибки `{error:{code,message,details}, request_id}`, коды 401/404/422/503, четыре покрытия,
`q=null` против `q=0` с раздельными причинами, неокруглённые R/H/UNC/Radj/B, геодезическая площадь в
результате, отчёт JSON и HTML, proof с `anchor.status = NOT_REQUESTED`, хеш содержания без самого себя.

## 4. Помеченные значения офлайн-режима

`src/lens/fixtures.ts`, одиннадцать наборов: `DOC_EXAMPLE_Q395` (условный пример постановки, Q = 395) и
десять логических векторов — `ZERO_NON_POSITIVE` (S1), `ZERO_UNCERTAINTY`, `ZERO_ROUNDED`,
`UNAVAILABLE_COVERAGE` (S7), `WEAK_OPTICS_VALID_CCI` (S6), `FIRE_SUPPORTED_LOSS` (S2),
`CAUSE_UNKNOWN_LOSS` (S3), `RECOVERY_AFTER_LOSS` (S4), `SUBPLOT_BASELINE` (S5), `UNKNOWN_DRIFT`.
Каждый результат несёт `fixture.label` и `fixture.note`, которые видны на экране. Схематичны и
подписаны: контуры зон и сетка ячеек офлайн-режима.

## 5. Известные ограничения интерфейса

1. Площадь произвольного контура до появления `/areas/measure` — предварительная оценка (см. L2).
2. Растровые превью, маска облачности и растр гарей в браузер не выдаются; показываются табличные
   метаданные сцен и записи о событиях.
3. Жизненный цикл заявок (подача, замечания, финализация, демо-выпуск) хранится в `sessionStorage`
   вкладки и помечен как демонстрационный. Это не реестр выпуска единиц.
4. Ограничение доступа по ролям на клиенте — подсказка, а не защита: решение принимает сервис. До
   появления серверных ролей прямой переход на чужой экран показывает объяснение и не делает запросов.
5. Путь `/lens` требует SPA-fallback; офлайн-сборка открывается через `index.html#/lens`.

## 6. Порядок подключения

1. Backend публикует `contracts/v2` в main → `openapi-typescript` заменяет ручной `src/lens/types.ts`.
2. `VITE_LENS_API_BASE_URL=<origin>/api/v2`, режим `http` (по умолчанию).
3. До появления `Authorization` в CORS открывать с `?auth=demo`; после — убрать параметр.
4. До появления `/auth/login` роль выбирается по списку учётных записей, пароль = токен сессии сервиса.
5. Проверка: `npx playwright test e2e/lens-backend.spec.ts` с `E2E_LENS_BACKEND_URL` и `E2E_LENS_SESSION`.
