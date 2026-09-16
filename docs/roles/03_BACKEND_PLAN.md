# BountyTeam — окончательный план Backend / Integration Owner

> Обязательный контекст: `00_BOUNTYTEAM_MANIFEST.md`,
> `01_ARCHITECTURE_AND_FLOW.md`, `02_JSON_API_ABI_CONTRACTS.md` и этот файл.
> Общие schema/OpenAPI/ABI и enum нельзя менять в одиночку.

## 1. Твоя роль и конечный результат

Ты — Backend Developer и технический Integration Owner. Твоя система отделяет
наблюдение RS от решения и связывает off-chain evidence с контрактом и UI.

P0-результат:

1. RS bundle валидируется и сохраняется без ручного редактирования.
2. Backend канонизирует evidence по JCS/RFC 8785 и считает SHA-256.
3. Policy выдаёт `NO_RESTRICTION`, `REVIEW_REQUIRED` или `FREEZE_REQUESTED`.
4. Issue/buy/transfer/freeze выполняются идемпотентно через контракт.
5. `CONFIRMED` появляется только после receipt, ожидаемого event и readback.
6. Frontend получает всё только из единого `/api/v1`.
7. После рестарта не теряются jobs, pending operations и история.

## 2. Граница ответственности

### Входы

- От RS: schema-valid evidence bundle и artifact manifest.
- От blockchain: согласованный ABI, deployment manifest, address/code hash.
- От frontend: запросы строго по OpenAPI.
- От тимлида: policy/config decisions и demo authorization.

### Выходы

- REST API `/api/v1` и соответствующий `/openapi.json`.
- Persistent jobs/operations и SQLite.
- Canonical evidence bytes, `evidence_hash`, decision record и `decision_hash`.
- Contract transactions, receipts, events, readback и unified timeline.
- Флаги `can_issue`, `can_buy`, `can_transfer_backend`.
- Proof endpoint, показывающий соответствие off-chain evidence и on-chain hash.

## 3. Нормативный API

Реализуй ровно согласованный набор:

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/v1/health` | backend, DB, chain/deployment state |
| GET | `/api/v1/plots` | список demo-проектов |
| GET | `/api/v1/plots/{plot_id}` | участок и текущий summary |
| POST | `/api/v1/plots/{plot_id}/verify` | создать async job, вернуть `202` |
| GET | `/api/v1/jobs/{job_id}` | `QUEUED/RUNNING/SUCCEEDED/FAILED` |
| GET | `/api/v1/verifications/{id}` | evidence + quality + decision |
| GET | `/api/v1/verifications/{id}/proof` | canonical hash и on-chain comparison |
| GET | `/api/v1/verifications/{id}/canonical` | канонический payload/metadata |
| GET | `/api/v1/plots/{plot_id}/history` | история наблюдений |
| GET | `/api/v1/plots/{plot_id}/credits` | серии, балансы, flags |
| POST | `/api/v1/plots/{plot_id}/issue` | demo issuance |
| POST | `/api/v1/batches/{batch_id}/buy` | тестовая покупка |
| POST | `/api/v1/batches/{batch_id}/transfer` | demo transfer |
| GET | `/api/v1/operations/{id}` | состояние chain operation |
| GET | `/api/v1/events?plot_id=...` | единый timeline |
| GET | `/api/v1/artifacts/{id}` | локальный разрешённый artifact |

Любой mutation POST требует `Idempotency-Key` и demo authorization. Публичного
`/freeze` не существует: freeze вызывается только внутренним oracle-flow.

## 4. Статусы и policy

### RS outcome — входной факт

- `NO_CHANGE`
- `DISTURBANCE_DETECTED`
- `INSUFFICIENT_DATA`

### Evidence quality — рассчитывает backend

- `SUFFICIENT`
- `REVIEW_REQUIRED`
- `INSUFFICIENT`

### Decision — рассчитывает backend

- `NO_RESTRICTION`
- `REVIEW_REQUIRED`
- `FREEZE_REQUESTED`

### Credit status — читает из chain

- `ACTIVE`
- `FROZEN`
- `REVOKED` зарезервирован, но P0 не реализует автоматический revoke.

### P0 decision rules

1. Schema/artifact/source hash failure → reject import; никакой policy/tx.
2. Недостаточная coverage, cloud/season mismatch или outcome
   `INSUFFICIENT_DATA` → evidence quality `INSUFFICIENT` или `REVIEW_REQUIRED`;
   decision `REVIEW_REQUIRED`.
3. `NO_CHANGE + SUFFICIENT` → `NO_RESTRICTION`.
4. `DISTURBANCE_DETECTED`, но нет FIRMS support/атрибуции либо не достигнут
   financial threshold → `REVIEW_REQUIRED`.
5. `DISTURBANCE_DETECTED + SUFFICIENT + FIRMS support + affected area >= 5 ha +
   affected area >= 1% baseline forest area` → `FREEZE_REQUESTED`, reason
   `FIRE_REVERSAL`.
6. Старый evidence никогда не размораживает и не понижает новое состояние.

Пороги только из versioned config. Любое изменение — contract change protocol.

## 5. Хеширование и проверяемость

- RS **не** присылает `evidence_hash`.
- Валидируй JSON Schema, затем cross-field semantics, source/artifact hashes и
  безопасные относительные пути.
- До canonicalization нормализуй schema-defined timestamps, числа и отсутствующие
  optional values согласно contract, но не «исправляй» научные результаты.
- Evidence hash: SHA-256 от JCS/RFC 8785 canonical bytes согласованного payload без
  поля собственного hash.
- Храни canonical bytes неизменяемо рядом с hash.
- Decision — отдельный versioned record; считай отдельный `decision_hash`.
- Solidity получает bytes32 raw digest. Нельзя делать `keccak(text=hex_hash)` и
  тем самым незаметно хешировать строку второй раз.
- `/proof` показывает computed evidence hash, decision hash, chain-stored hash,
  tx/event и результат сравнения.

## 6. Jobs, operations и надёжность

### Долгие RS jobs

`POST /verify` немедленно возвращает:

```json
{"job_id":"...","state":"QUEUED"}
```

CPU/IO pipeline запускай отдельным процессом/worker command. FastAPI
`BackgroundTasks` сам по себе не является durable queue и не должен быть
единственным механизмом. Для MVP достаточно persistent `jobs` table + worker,
который подбирает `QUEUED` jobs после рестарта.

### Идемпотентность

- Unique binding: actor + operation + idempotency key + canonical request-body hash.
- Повтор того же запроса возвращает ту же operation.
- Тот же key с другим body → `409 IDEMPOTENCY_CONFLICT`.
- Unique `(plot_id, evidence_hash)` предотвращает повторный import/decision.
- Unique `issuance_key` предотвращает duplicate batch.

### Chain operation state

```text
QUEUED → SUBMITTED → CONFIRMED
  ↘ FAILED       ↘ FAILED
```

- Сначала запиши intent в БД.
- Публичные состояния: только `QUEUED`, `SUBMITTED`, `CONFIRMED`, `FAILED`.
  `SIGNING` не является API-состоянием: подписание выполняется внутри `QUEUED`.
- Единственный runtime signer сериализует nonce.
- Сохрани signed raw transaction и tx hash до broadcast.
- После сохранения подписанной транзакции и broadcast перейди в `SUBMITTED`.
- Timeout после broadcast остаётся `SUBMITTED`; не создавай новую транзакцию.
- `CONFIRMED` только если receipt status=1, найден ожидаемый event и readback
  подтверждает batch state/balance.
- После рестарта reconciliation восстанавливает `QUEUED/SUBMITTED` операции
  по сохранённым intent, signed bytes и tx hash, без отдельного состояния
  подписания и без создания транзакционных дублей с новым nonce.
- При старте проверь chain ID, deployment address, runtime code hash и ABI hash;
  не работай молча с новым локальным deploy.

## 7. Безопасность MVP

- SQLite, FastAPI/Pydantic v2, web3.py AsyncWeb3 для неблокирующих RPC reads.
- Private keys только в env/runtime demo configuration; `.env` не коммитить.
- Bind services к loopback по умолчанию.
- Demo actors: issuer, buyer, recipient, oracle; права различаются.
- Artifacts endpoint использует allowlist/DB IDs, не принимает произвольный path.
- CORS только для известного frontend origin.
- Freeze инициирует policy/oracle internally; admin override, если вообще нужен,
  только с отдельной ролью и явным audit event.

## 8. Приоритеты

### P0

- SQLite models/migrations, jobs, operations, events.
- Bundle import + schema/cross-field/hash validation.
- JCS/SHA-256 evidence и decision record.
- Policy state machine.
- Issue/buy/transfer/internal freeze + reconciliation.
- Full OpenAPI endpoints, idempotency, error model.
- Offline fixtures и real bundle.
- One-command/demo startup совместно с blockchain/frontend.

### P1

- Удобный proof viewer response, better metrics/health, автоматическая сборка,
  расширенный journal filtering.

### P2

- Sepolia, PostgreSQL/PostGIS, полноценная auth — только после stable P0 и
  разрешения тимлида.

### CUT

Celery/Redis ради масштаба, публичный freeze endpoint, хранение снимков on-chain,
самостоятельная переработка научной методики, полный marketplace.

## 9. До старта: 16–17 сентября

### Блок A — contract skeleton, 3 часа

- Сгенерируй Pydantic models из shared schema или вручную реализуй строго по ней.
- Подними `/health`, SQLite, plots/verifications/jobs/operations/events.
- Зафиксируй error envelope и `Idempotency-Key` handling.
- Передай frontend OpenAPI/client types.

Результат: backend принимает три golden fixtures и выдаёт ожидаемые decisions.

### Блок B — chain adapter, 3 часа

- Получи ABI только из компиляции согласованного Solidity.
- Реализуй adapter `issue/buy/transfer/freeze/readback`.
- Проверь deployment identity и один runtime signer.
- С blockchain-разработчиком прогоните balance/freeze/revert.

Результат: adapter integration test проходит на локальном Anvil.

### Блок C — offline/demo, 2 часа

- Seed demo plot/actors; подключи fixtures и artifact serving.
- Подготовь exact start commands и `.env.example` без секретов.
- Проверь cold restart/reconciliation.

## 10. Почасовой план хакатона

### Пятница, 18:30–19:00

Уточни требования к API/auth/chain и передай ответы тимлиду. Не добавляй PostGIS
или production auth без прямого требования.

### 19:00–19:30

- Подними `/health`, DB, OpenAPI.
- Прими golden fixture от RS.
- Подтверди frontend base path и schemas.
- Подключись к согласованному local deployment.

Результат: Integration Owner сообщает всей команде адрес API, contract version и
команды smoke.

### 19:30–22:00

- Реализуй/проверь import, validation, policy и read endpoints.
- Отдай frontend реальные API responses на fixtures.
- С blockchain проверь issue/balance/buy.
- Добавь operations polling и unified events.

Checkpoint 22:00: fixture проходит RS→backend→frontend; issue/buy подтверждены
readback. Если нет — P1 прекращается.

### 22:00–02:00

- Собери полный E2E: issue → buy → fire evidence import → internal freeze → event
  → readback → direct transfer revert.
- Включи idempotency и pending state.
- Прими первый computed RS bundle.
- Запиши e2e test/script и помоги создать stable tag.

Checkpoint 02:00: есть receipt+event+readback, не только UI; повтор не создаёт
дубль; restart не теряет operation.

### 02:15–07:45 — сон

Перед сном сохрани DB, operation states, start/reconcile command и список
блокеров. Не оставляй неподтверждённую транзакцию без tx hash.

### 07:45–08:15

- Холодный запуск backend/worker/chain adapter.
- Reconcile pending operations.
- Запусти smoke на stable fixtures.

### 08:15–11:30

- Импортируй финальный real bundle RS без ручной правки.
- Проверь hashes/artifacts и policy branches.
- Убедись, что real/no-change/insufficient идут одним кодом.
- Отдай frontend реальный history/credits/events/proof.
- Получи от другого участника повтор cold run.

Checkpoint 11:30: real E2E, truthful mode labels, negative branches не freeze.

### 12:00–14:30

- Покажи эксперту policy и separation of concerns.
- Исправляй только P0/rubric gap.
- Добавь формулировку, что `FREEZE_REQUESTED` — demo governance, а production
  требует verifier workflow.

### 14:30–16:30

- Заверши journal, proof, error states, buyer flow.
- Проверь corrupt JSON/artifact, mismatched date/hash, RS `FROZEN` field rejection.
- Научи blockchain-разработчика/тимлида запускать backend demo.

Checkpoint 16:30: offline/restart/idempotency/receipt timeout безопасны.

### 16:30–18:00

- Тест recovery `SUBMITTED`, stale evidence, deployment mismatch.
- Устрани только критические дефекты.
- В 18:00 feature freeze.

### 18:00–20:00

- Полный regression, export DB/seed/config manifest.
- Зафиксируй policy hash, OpenAPI version, ABI hash, deployment identity.
- Сформируй release candidate и финальное видео.

### 20:00–23:30

- Второй участник запускает всё по README.
- Проверка release без интернета, секретов и dev-only путей.
- Помощь в загрузке и проверка точного артефакта на платформе.

## 11. Интеграционные handoffs

| Время | Вход/выход | С кем | Acceptance |
|---|---|---|---|
| Пт 19:30 | fixture import + API response | RS/Frontend | schema/OpenAPI pass |
| Пт 22:00 | issue/buy adapter | Blockchain | balances/readback |
| Сб 01:00 | computed bundle decision | RS | no manual edits |
| Сб 02:00 | full E2E | Все | receipt/event/revert |
| Сб 10:00 | real data endpoints | Frontend | UI uses API only |
| Сб 16:30 | restart/offline release | Тимлид | cold smoke pass |
| Сб 18:00 | frozen OpenAPI/policy/DB schema | Release | versioned manifest |

## 12. Acceptance criteria Backend

- [ ] `POST /verify` возвращает 202; jobs persistent и recoverable.
- [ ] Golden и real bundles проходят одну schema/semantic pipeline.
- [ ] Изменённые JSON/GeoJSON/raster/source hash отклоняются.
- [ ] JCS canonical bytes сохраняются; SHA-256 воспроизводится.
- [ ] Outcome, evidence quality, decision, operation и credit state разделены.
- [ ] Insufficient/unattributed disturbance никогда автоматически не freeze.
- [ ] Все mutations идемпотентны; conflict даёт 409.
- [ ] Intent записан до sign/broadcast; nonce сериализован.
- [ ] `CONFIRMED` требует receipt status, event и readback.
- [ ] Restart reconcile не создаёт duplicate tx.
- [ ] Deployment mismatch обнаруживается.
- [ ] Public freeze отсутствует; demo roles/auth работают.
- [ ] Frontend получает history, credits, flags, operations, events и artifacts.
- [ ] Direct contract transfer после freeze revert подтверждён тестом.
- [ ] Другой участник запускает backend по README.

## 13. Fallbacks

- RS computation недоступен → импорт hash-verified cached bundle с меткой
  `CACHED_REPLAY`.
- Chain RPC недоступен → операция остаётся pending/failed; UI не рисует FROZEN.
  Для защиты переключиться на stable local Anvil deployment.
- Новый Anvil deployment → запустить deploy script и seed, обновить deployment
  manifest; не переиспользовать старый address молча.
- Frontend недоступен → Swagger/API + events/proof и резервное видео.
- DB повреждена → восстановить seed/stable DB; не имитировать chain confirmation.

## 14. Что говорить на защите, 40–60 секунд

> Backend разделяет наблюдение и решение. Мы валидируем evidence bundle, проверяем
> hashes артефактов, канонизируем JSON по JCS и считаем SHA-256. Затем versioned
> policy определяет: нет ограничения, нужна ручная проверка или требуется
> временная заморозка. Для blockchain-операций есть идемпотентность, журнал и
> восстановление после таймаута. Статус `CONFIRMED` появляется только после
> receipt, события и чтения состояния контракта. Поэтому зелёный интерфейс не
> может скрыть неуспешную транзакцию.

## 15. Что запрещено менять самостоятельно

- Schema/OpenAPI/ABI, enum, units, thresholds и hash algorithm.
- Принимать `FROZEN` от RS.
- Выдавать pending tx за confirmed.
- Добавлять public freeze или хранить пользовательские ключи в коде.
- Создавать обходной mock path, который рисует успех без chain readback.
- Делать frontend зависимым от RPC или файлов RS.

## 16. Формат отчёта на sync

```text
BACKEND <время>
Commit/API: <link/version>
Bundle import: PASS|FAIL
Decision: <value>
Chain operation: <state + tx hash if exists>
E2E: <last passing test>
Blocker: <exact repro or none>
Next handoff: <кому, что, время>
```
