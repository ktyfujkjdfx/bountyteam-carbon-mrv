# Definition of Done

## Общий P0-релиз готов, когда

- [ ] Другой участник запускает сданную сборку по README.
- [ ] Указаны real scene IDs, provider, processing baseline/transform и SHA-256.
- [ ] Real baseline и post-fire evidence проходят shared schema и semantic checks.
- [ ] Недостаточные данные и unattributed disturbance не запускают freeze.
- [ ] Backend вычисляет JCS/SHA-256, policy decision и хранит canonical bytes.
- [ ] Demo-authorisation однократно выпускает ограниченную серию.
- [ ] Покупка меняет реальные on-chain балансы seller/buyer.
- [ ] Freeze подтверждён receipt, событием и readback состояния.
- [ ] Прямой `transfer` после freeze отклоняется контрактом.
- [ ] UI различает outcome, quality, decision, tx state и credit status.
- [ ] UI обозначает REAL/SYNTHETIC и COMPUTED/CACHED_REPLAY.
- [ ] Интернет можно отключить без разрушения основного демо.
- [ ] Есть verified release, video fallback и второй ноутбук.
- [ ] Загруженный пакет открыт с платформы до стоп-кода.

## Приёмка по ролям

| Роль | Минимальное доказательство готовности |
|---|---|
| RS | Реальный воспроизводимый bundle; корректные маски/grid/area; insufficient branch; backend повторил запуск |
| Backend | 202 jobs, durable state, schema/JCS/policy, idempotency/nonce/reconciliation, real chain readback, journal |
| Blockchain | owner/issuer/oracle access, real balances/buy, frozen batch rejects direct buy/transfer, ABI/deploy manifest/tests |
| Frontend | Один SPA, polling/error states, real balances/receipt, aligned local previews, truthful mode labels, offline dist |
| Тимлид | Регламент, contract version, checkpoints, claims/risk/decision logs, release/video/submission and rehearsed pitch |

## Обязательные негативные тесты приложения

- [ ] Посторонний не назначает себя issuer/oracle и не mint/freeze.
- [ ] Неизвестный batch не получает ACTIVE по default enum.
- [ ] Duplicate issuance/idempotency не создаёт вторую серию/списание.
- [ ] Freeze pending не рисуется подтверждённым FROZEN.
- [ ] Receipt timeout восстанавливается без нового nonce-дубля.
- [ ] Старый evidence не отменяет новое и не размораживает серию.
- [ ] Cloudy/season-mismatch → REVIEW_REQUIRED без автоматического freeze.
- [ ] Altered JSON/GeoJSON/raster/source file не проходит hash checks.
- [ ] Неверный actor, amount, payment, balance и address отклоняются.
- [ ] Direct RPC transfer замороженной серии делает revert.
- [ ] Смена локального deployment обнаруживается.
- [ ] Перезапуск backend не теряет SUBMITTED/QUEUED operations.

Shared package tests доказывают совместимость спецификаций и synthetic fixtures.
Они не заменяют эти runtime/E2E тесты реализованного приложения.
