# BountyTeam — golden fixtures

Golden fixtures — три одинаковых **синтетических** сценария, от которых все
роли начинают разработку. Они фиксируют форму данных и ожидаемое поведение.
Это не результаты реального пожара и не материалы для научной защиты.

## Fixture 1: `verification_no_change`

| Поле | Значение |
|---|---|
| `dataset_kind` | `SYNTHETIC` |
| `outcome` RS | `NO_CHANGE` |
| Paired valid forest | 100% |
| Affected pixels/area | 0 / 0 га |
| FIRMS | `NOT_FOUND` |
| Backend quality | `SUFFICIENT` |
| Backend decision | `NO_RESTRICTION` |
| Financial effect | Никакой автоматической транзакции; отдельное demo authorization может разрешить issue |

Используют:

- RS — как эталон формата полного отчёта;
- Backend — для проверки допуска baseline;
- Frontend — для зелёного состояния без слова «сертифицирован»;
- Blockchain — как evidence hash выпуска.

## Fixture 2: `verification_fire`

| Поле | Значение |
|---|---|
| `dataset_kind` | `SYNTHETIC` |
| `outcome` RS | `DISTURBANCE_DETECTED` |
| Paired valid forest | 100% |
| Affected area | 16 га из 100 га исходной synthetic forest mask |
| dNBR mask | 400 пикселей по 0.04 га |
| FIRMS | `SUPPORTED`, одна synthetic FIRMS-shaped точка |
| Backend quality | `SUFFICIENT` |
| Backend decision | `FREEZE_REQUESTED` |
| Reason | `FIRE_REVERSAL` |
| Chain result после реализации | Confirmed `FROZEN`; buy/transfer делают revert |

Все цифры созданы специально для контрактных тестов. Их нельзя произносить на
защите как реальные показатели Красноярского края.

## Fixture 3: `verification_insufficient`

| Поле | Значение |
|---|---|
| `dataset_kind` | `SYNTHETIC` |
| `outcome` RS | `INSUFFICIENT_DATA` |
| Paired valid forest | 20% |
| Cloud coverage after | 80% |
| Индексы и affected area | `null` |
| FIRMS | `NOT_CHECKED` |
| Backend quality | `INSUFFICIENT` |
| Backend decision | `REVIEW_REQUIRED` |
| Financial effect | Новые issue/buy закрыты через backend; автоматической freeze нет |

Этот сценарий обязателен: недостаток данных не должен превращаться ни в
`NO_CHANGE`, ни в обвинение владельца, ни в автоматическую блокировку.

## Минимальные примеры ответов API

### Проверка запущена

```json
{
  "job_id": "30000000-0000-4000-8000-000000000001",
  "state": "QUEUED",
  "status_url": "/api/v1/jobs/30000000-0000-4000-8000-000000000001"
}
```

### Транзакционная операция поставлена в очередь

```json
{
  "operation_id": "40000000-0000-4000-8000-000000000001",
  "transaction_state": "QUEUED",
  "status_url": "/api/v1/operations/40000000-0000-4000-8000-000000000001"
}
```

### Ошибка схемы

```json
{
  "error": {
    "code": "INVALID_EVIDENCE",
    "message": "Неверная схема",
    "details": {}
  },
  "request_id": "30000000-0000-4000-8000-000000000001"
}
```

## Обязательные проверки для всех реализаций

1. `no_change` не вызывает freeze.
2. `fire` вызывает только `FREEZE_REQUESTED`; UI ждёт confirmed receipt.
3. `insufficient` не вызывает freeze и не разрешает новые финансовые действия.
4. RS JSON с полем `FROZEN`, `confidence` или `evidence_hash` отклоняется.
5. Повреждение файла/неверный hash отклоняется.
6. Перепутанные даты и CRS отклоняются.
7. Повтор одного idempotency key не создаёт повторный выпуск/платёж.
8. Direct transfer после confirmed freeze отклоняет контракт.
9. Старый хороший отчёт не размораживает серию.
10. Реальные данные позже обязаны пройти тот же формат и проверки, но сохраняют
    `dataset_kind: REAL` и настоящие source IDs.
