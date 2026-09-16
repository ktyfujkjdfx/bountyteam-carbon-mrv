# BountyTeam — окончательный план Frontend-разработчика / Demo Operator

> Обязательный контекст: `00_BOUNTYTEAM_MANIFEST.md`,
> `01_ARCHITECTURE_AND_FLOW.md`, `02_JSON_API_ABI_CONTRACTS.md` и этот файл.
> Frontend работает только через backend API и не придумывает собственные статусы.

## 1. Твоя роль и конечный результат

Ты создаёшь один плотный SPA-дашборд и физически управляешь демонстрацией. UI
должен за 90 секунд доказать всю историю: участок и реальные наблюдения → evidence
→ решение → тестовая покупка → on-chain freeze → запрещённая передача.

P0-результат:

- один SPA, а не шесть страниц;
- карта/снимки/метрики доказательства;
- отдельные и честные статусы evidence, decision, operation и credit;
- реальные batch balances и тестовая покупка;
- `FROZEN` только после backend-confirmed receipt/event/readback;
- единый timeline;
- offline build и записанное видео.

Ты — основной Demo Operator. Тимлид — запасной. Во время защиты ноутбук не
передаётся по кругу.

## 2. Архитектурная граница

Frontend общается только с `/api/v1` backend.

Запрещено:

- обращаться напрямую к Copernicus/FIRMS;
- читать GeoTIFF в браузере;
- обращаться напрямую к Anvil/Sepolia RPC;
- самостоятельно вычислять evidence/decision/credit status;
- показывать fake success при failed/pending operation.

Backend отдаёт локальные PNG/WebP previews, GeoJSON, operations, balances,
receipts, events и flags.

## 3. Один SPA: обязательная композиция

### Верхняя панель

- Название проекта/участка и площадь.
- Mode badges: `REAL` или `SYNTHETIC`; `HISTORICAL_REPLAY`;
  `COMPUTED` или `CACHED_REPLAY`.
- Последнее наблюдение и источник сцен.

### Основная область

1. **Map/Evidence**
   - участок;
   - affected-area GeoJSON;
   - FIRMS points с подписью «thermal anomalies, not perimeter»;
   - fallback на локальную static background/image overlay.
2. **Before/After**
   - одинаковые bounds, size и orientation;
   - web-ready PNG/WebP, не GeoTIFF;
   - даты и real scene IDs.
3. **Evidence card**
   - RS outcome;
   - evidence quality;
   - affected area, percent baseline forest, valid ratio, AOI cloud ratio;
   - dNBR threshold/legend;
   - limitations и source IDs.
4. **Tokens/Investment**
   - batch ID, supply, unit demo price, seller/buyer balances, credit status;
   - issue для demo issuer;
   - тестовая покупка amount;
   - transfer ACTIVE units;
   - disabled reason после freeze.
5. **Journal/Proof**
   - observation → decision → transaction → event;
   - evidence/decision hash, tx hash, receipt/readback;
   - operation state polling.

Лучший layout: карта/слайдер слева, evidence/tokens справа, timeline снизу; вкладки
`Evidence / Tokens / Journal` допустимы внутри одной SPA.

## 4. Статусы нельзя смешивать

Показывай отдельными компонентами:

| Слой | Значения |
|---|---|
| RS outcome | `NO_CHANGE`, `DISTURBANCE_DETECTED`, `INSUFFICIENT_DATA` |
| Evidence quality | `SUFFICIENT`, `REVIEW_REQUIRED`, `INSUFFICIENT` |
| Backend decision | `NO_RESTRICTION`, `REVIEW_REQUIRED`, `FREEZE_REQUESTED` |
| Operation | `QUEUED`, `SUBMITTED`, `CONFIRMED`, `FAILED` |
| Credit | `ACTIVE`, `FROZEN`, `REVOKED` |

`SIGNING` не является публичным API-состоянием и не отображается отдельно.
Backend выполняет подписание внутри `QUEUED`; после сохранения подписанной
транзакции и broadcast операция переходит в `SUBMITTED`.

Критическое правило: `FREEZE_REQUESTED` и `SUBMITTED` ещё не означают `FROZEN`.
Красный confirmed FROZEN показывается только когда backend вернул chain readback.

## 5. API и состояние

- Сгенерируй TS types/client из frozen OpenAPI либо держи одну типизированную
  client-layer. Нельзя копировать разные интерфейсы по компонентам.
- Всегда проверяй `response.ok` и error envelope.
- `POST /verify` возвращает 202/job; poll `/jobs/{id}` с backoff до terminal state.
- Issue/buy/transfer возвращают operation; poll `/operations/{id}`.
- Любой POST отправляет `Idempotency-Key`, который сохраняется на время операции.
- После refresh восстанавливай текущий job/operation из URL/local state и backend.
- Кнопки используют backend flags `can_issue`, `can_buy`,
  `can_transfer_backend`, но безопасность всё равно обеспечивается контрактом.
- Loading, empty, insufficient, review, failed и retry states обязательны.

## 6. Визуализация и офлайн

- React + TypeScript + Vite; Leaflet достаточно.
- Не строй шесть routes. Один экран и простые panels/tabs.
- Реальные previews должны быть заранее отрендерены RS и локально обслуживаться
  backend. Browser не открывает GeoTIFF.
- Before/after slider разрешён только для географически согласованных картинок.
- Для offline не скачивай тысячи OSM tiles. Используй локальный image overlay,
  static basemap screenshot с корректной attribution/разрешением либо чистый фон
  с GeoJSON.
- Все числа показывай с единицами и источником. Evidence Quality Score подписывай
  как completeness indicator, не «вероятность, что пожар настоящий».

## 7. UX demo-flow

1. Открыть real project и показать mode labels.
2. Выбрать baseline observation: `NO_CHANGE`, достаточное evidence.
3. Показать ACTIVE demo batch и seller balance.
4. Купить несколько units: дождаться `CONFIRMED`, показать buyer balance.
5. Переключить observation на реальный post-fire historical replay или запустить
   import/verification job.
6. Показать before/after, dNBR, affected contour, FIRMS и ограничения.
7. Backend decision становится `FREEZE_REQUESTED`; operation проходит стадии.
8. После receipt/readback credit показывает `FROZEN`.
9. Нажать transfer: backend/контракт возвращает ожидаемый отказ; показать событие
   в journal.

Не использовать кнопку «Симулировать пожар». Можно переключать реальные даты или
запускать historical replay с честной подписью.

## 8. Приоритеты

### P0

- Один SPA shell и API client.
- Plot/evidence map + aligned before/after.
- Все пять групп статусов раздельно.
- Async job/operation polling и errors.
- Tokens block: batch, price, supply, balances, issue/buy/transfer.
- Unified timeline/proof.
- Real/cached/synthetic/historical labels.
- Offline `dist`, local assets и fallback video.

### P1

- Улучшенная SWIR/dNBR легенда, hash copy/verify UI, аккуратные transitions,
  responsive polish.

### P2

- Дополнительные графики, второй project, wallet integration — только после
  разрешения тимлида и stable P0.

### CUT

Шесть отдельных экранов, сложный marketplace, MetaMask как обязательная
зависимость, remote map tiles для основного demo, direct RPC, 3D/анимации,
мобильная идеальность ценой P0.

## 9. До старта: 16–17 сентября

### Блок A — contract-first UI, 2–3 часа

- Получи frozen OpenAPI и golden fixture responses.
- Зафиксируй одну SPA-композицию и client layer.
- Подними skeleton с tabs/panels и status components.

Результат: три golden scenarios отображаются без изменения компонентов.

### Блок B — evidence visuals, 2–3 часа

- Карта с тестовым AOI/affected GeoJSON/FIRMS.
- Before/after slider на одинаковых локальных картинках.
- Evidence/limitations/source card.

Результат: UI переживает отсутствующий artifact и insufficient data.

### Блок C — transactions/offline, 2–3 часа

- Issue/buy/transfer UI с operation polling.
- Journal и proof panel.
- Production build с local assets; короткий скринкаст.

Результат: frontend переключается между mock adapter и API только конфигурацией,
а не переписыванием компонентов. К началу хакатона основной режим — API.

## 10. Почасовой план хакатона

### Пятница, 18:30–19:00

Уточни требования к desktop/mobile, локализации и обязательному marketplace.
Передай ответы тимлиду. Не начинай редизайн без связи с rubric.

### 19:00–19:30

- Подключись к backend `/health`, plots и frozen OpenAPI.
- Покажи golden no-change fixture через реальный backend.
- Зафиксируй viewport/demo resolution.

Результат: одна ссылка/команда запуска SPA и рабочий API client.

### 19:30–22:00

- Подключи plot/evidence summary, artifacts и отдельные status badges.
- Подключи credits, seller/buyer balances и issue/buy operation polling.
- Не жди real RS data: работай на golden fixtures.
- После каждой интеграции сразу запускай smoke/error test.

Checkpoint 22:00: fixture идёт backend→UI; issue/buy меняют показанные реальные
balances; нет direct RPC.

### 22:00–02:00

- Подключи decision/freeze operation, journal и proof.
- Показать pending отдельно от confirmed.
- Disabled transfer после readback FROZEN; попытка отправки показывает contract
  rejection, а не только frontend validation.
- Подключи первый computed RS preview/bundle через backend.
- Запиши первый полный скринкаст.

Checkpoint 02:00: E2E виден в браузере; video сохранено; stable build создан.

### 02:15–07:45 — сон

Перед сном `npm run build`, сохрани `dist`, commit и start command. Не оставляй
единственную рабочую версию в dev server memory.

### 07:45–08:15

- Холодный запуск stable `dist`.
- Проверь API error и offline/local-assets режим.
- Назначь один визуальный P0-дефект.

### 08:15–11:30

- Заменяй golden imagery на real bundle только через те же API поля.
- Добавь affected GeoJSON/FIRMS/SWIR/dNBR previews.
- Проверь реальные scene IDs, даты, units и limitations.
- Прогони no-change, fire и insufficient scenarios.
- Запиши real-data скринкаст до checkpoint.

Checkpoint 11:30: UI честно показывает REAL vs cached/synthetic и не freeze на
insufficient/review.

### 12:00–14:30

- Покажи UI эксперту; спроси, понятно ли различие observation/decision/status.
- Исправляй только ошибки смысла и P0/rubric gaps.
- Убери перегруженность; не добавляй новый экран.

### 14:30–16:30

- Заверши purchase block, timeline, proof, error messages и accessibility basics.
- Проведи demo самому три раза.
- Научи тимлида провести тот же сценарий.
- Запиши резервное видео до дальнейшей полировки.

Checkpoint 16:30: API timeout, offline, restart и failed tx не разрушают demo.

### 16:30–18:00

- Проверка idempotent double click, slow operation, missing artifact, long text.
- Исправляй только P0.
- В 18:00 feature freeze и final `npm run build`.

### 18:00–20:00

- Полный regression на release API/chain/data.
- Финальное видео, screenshots и release candidate `dist`.
- Проверка в demo resolution и на втором ноутбуке.

### 20:00–22:00

- Три репетиции с таймером; одна без интернета.
- Demo Operator работает одним ноутбуком и одной последовательностью окон.
- Убери devtools/лишние вкладки/уведомления, подготовь fallback shortcuts.

### 22:00–23:30

- В release входят `package.json`, lockfile, source, `dist`, README; не
  `node_modules`.
- После загрузки открыть точный release и повторить короткий smoke.

## 11. Интеграционные handoffs

| Время | Вход | От кого | Твой измеримый результат |
|---|---|---|---|
| Пт 19:30 | OpenAPI + fixtures | Backend | typed client + plot view |
| Пт 22:00 | issue/buy responses | Backend/Chain | real balances in UI |
| Сб 01:30 | freeze operation/events | Backend | pending→confirmed→FROZEN |
| Сб 10:00 | final real artifacts | RS через Backend | map/slider/evidence |
| Сб 16:30 | stable offline API/assets | Integration Owner | no-internet demo |
| Сб 18:00 | frozen release API | Backend | final dist |

Если API-field расходится — не делай локальный alias молча. Открой blocker с
OpenAPI/schema version и согласуй fix через Integration Owner.

## 12. Acceptance criteria Frontend

- [ ] Один SPA; P0 не разнесён на шесть routes.
- [ ] Frontend общается только с backend `/api/v1`.
- [ ] Outcome/quality/decision/operation/credit state визуально разделены.
- [ ] `SUBMITTED` не отображается как confirmed FROZEN.
- [ ] 202 jobs и operations polling работают после refresh.
- [ ] Все POST имеют stable idempotency key и double-click protection.
- [ ] Real scene IDs, dates, units, sources и limitations показаны.
- [ ] Before/after aligned; GeoTIFF не грузится напрямую в browser.
- [ ] Map/GeoJSON/FIRMS и offline static fallback работают.
- [ ] Issue/buy/transfer показывают реальные chain balances/readback.
- [ ] Direct transfer rejection после freeze виден в journal.
- [ ] Insufficient/review не выглядят как нарушение или confirmed fire.
- [ ] REAL/SYNTHETIC и COMPUTED/CACHED_REPLAY маркированы.
- [ ] `npm run build` проходит; `dist` запускается на втором ноутбуке.
- [ ] Есть два видео: ранний stable и финальный.

## 13. Fallbacks

- Backend недоступен → не показывать фиктивный live success; перейти на заранее
  поднятый stable backend либо видео/статический доказательный walkthrough.
- Remote tiles недоступны → local image overlay/static background + GeoJSON.
- Real computation долго идёт → backend отдаёт честно помеченный `CACHED_REPLAY`.
- Artifact повреждён → показать error/manifest failure и резервный stable bundle.
- Chain tx timeout → оставить `SUBMITTED`, затем перейти к заранее подтверждённой
  операции; не красить статус в FROZEN.
- Ноутбук сломался → второй ноутбук с тем же `dist` и release tag.

## 14. Что говорить на защите, 40–60 секунд

> Это единое окно для оператора и покупателя. Слева видны участок, снимки до и
> после, контур изменения и независимые thermal anomaly points; справа — качество
> evidence, решение, серия и реальные балансы demo-участников. Мы намеренно
> разделяем наблюдение, решение backend, состояние транзакции и статус серии.
> Поэтому запрос на freeze ещё не рисуется как выполненная заморозка. После
> подтверждённого receipt и readback серия становится `FROZEN`, а прямая передача
> отклоняется контрактом. Все внешние данные закэшированы для воспроизводимого
> offline demo.

## 15. Что запрещено менять самостоятельно

- OpenAPI/schema/enum/единицы и смысл status colors.
- Придумывать `FROZEN` из RS outcome или frontend state.
- Ходить напрямую в RPC/RS provider.
- Добавлять кнопку «Симулировать пожар».
- Делать remote tiles/MetaMask обязательными для основного demo.
- Скрывать historical/cached/synthetic режимы.
- Добавлять новые экраны после feature freeze.

## 16. Формат отчёта на sync

```text
FRONTEND <время>
Build/commit: <link>
API version: <version>
Scenario tested: <no-change|fire|insufficient>
Last confirmed UI state: <operation + credit status>
Offline/video: <status>
Blocker: <exact request/response or none>
Next handoff: <что и время>
```
