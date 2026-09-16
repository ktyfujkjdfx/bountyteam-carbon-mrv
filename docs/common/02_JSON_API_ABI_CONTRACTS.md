# BountyTeam — единые JSON, API и ABI-контракты

Версия: **1.0.0**. Этот документ фиксирует человечески читаемый контракт между
RS, backend, blockchain и frontend. Точные машинные схемы создаются разработчиками
из этих решений и не должны менять их смысл.

## 1. Три независимые группы статусов

| Слой | Допустимые значения | Кто определяет |
|---|---|---|
| RS outcome | `NO_CHANGE`, `DISTURBANCE_DETECTED`, `INSUFFICIENT_DATA` | RS |
| Evidence quality | `SUFFICIENT`, `REVIEW_REQUIRED`, `INSUFFICIENT` | Backend |
| Backend decision | `NO_RESTRICTION`, `REVIEW_REQUIRED`, `FREEZE_REQUESTED` | Backend |
| Credit status | `ACTIVE`, `FROZEN`, `REVOKED` | Смарт-контракт |
| Job state | `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED` | Backend worker |
| Transaction state | `QUEUED`, `SUBMITTED`, `CONFIRMED`, `FAILED` | Backend + chain receipt |

`REVOKED` зарезервирован и не используется автоматически. Автоматического
`FROZEN → ACTIVE` в MVP нет.

## 2. JSON, который RS отдаёт backend

Основной объект: `VerificationEvidence`. В нём запрещены `FROZEN`, `ACTIVE`,
`decision`, `confidence`, `confidence_score`, `evidence_hash` и команды
смарт-контракту.

```json
{
  "schema_version": "1.0.0",
  "dataset_kind": "REAL",
  "plot_id": "KRAS-001",
  "plot_geometry_hash": "0x<64 lowercase hex>",
  "observation": {
    "before": {
      "scene_id": "<real scene id>",
      "acquired_at": "2023-07-10T05:00:00Z",
      "provider": "CDSE",
      "collection": "sentinel-2-l2a",
      "processing_baseline": "<from metadata>",
      "mgrs_tile": "<tile>",
      "assets": []
    },
    "after": {
      "scene_id": "<real scene id>",
      "acquired_at": "2024-07-10T05:00:00Z",
      "provider": "CDSE",
      "collection": "sentinel-2-l2a",
      "processing_baseline": "<from metadata>",
      "mgrs_tile": "<tile>",
      "assets": []
    }
  },
  "outcome": "NO_CHANGE",
  "method": {},
  "quality": {},
  "metrics": {},
  "firms": {},
  "artifacts": [],
  "limitations": []
}
```

### Обязательные данные сцены

Каждый входной asset содержит:

```json
{
  "band": "B8A",
  "source_ref": "идентификатор без секрета",
  "local_sha256": "0x<64 lowercase hex>",
  "scale_applied": 0.0001,
  "offset_applied": 0,
  "transform_origin": "PRODUCT_METADATA"
}
```

Каналы для полноценного расчёта: `B04`, `B08`, `B8A`, `B12`, `SCL` для обеих
дат. `transform_origin`: `PRODUCT_METADATA` либо `PROVIDER_HARMONIZED`.

### `method`

```json
{
  "pipeline_version": "1.0.0",
  "code_commit": "40 lowercase hex",
  "config_sha256": "0x<64 lowercase hex>",
  "grid": {
    "epsg": 32646,
    "resolution_m": 20,
    "width": 500,
    "height": 500,
    "transform": [20, 0, 430000, 0, -20, 6230000]
  },
  "forest_mask": {
    "source": "ESA WorldCover 2021",
    "version": "v200",
    "reference_year": 2021,
    "sha256": "0x<64 lowercase hex>",
    "interpretation_note": "Ограничения маски"
  },
  "parameters": {
    "ndvi_bands": ["B08", "B04"],
    "nbr_bands": ["B8A", "B12"],
    "disturbance_dnbr_min": 0.27,
    "min_component_area_ha": 1,
    "connectivity": 8,
    "excluded_scl_classes": [0, 1, 2, 3, 6, 7, 8, 9, 10, 11],
    "resampling_continuous": "average",
    "resampling_categorical": "nearest"
  }
}
```

### `quality` и `metrics`

`quality`:

- `paired_valid_aoi_ratio`;
- `paired_valid_forest_ratio`;
- `aoi_cloud_ratio_before`, `aoi_cloud_ratio_after`;
- `metadata_complete`, `grid_aligned`;
- `temporal_comparability`: `YES`, `NO`, `UNCERTAIN`;
- `temporal_note`.

`metrics`:

- `plot_area_ha`, `baseline_forest_area_ha`, `analysed_forest_area_ha`;
- `affected_area_ha`, `affected_fraction_of_baseline_forest`;
- `ndvi_before_mean`, `ndvi_after_mean`, `dnbr_mean`;
- `dnbr_mean_scope: PAIRED_VALID_BASELINE_FOREST`;
- `baseline_forest_pixel_count`, `paired_valid_forest_pixel_count`,
  `affected_pixel_count`.

Неизвестное значение — `null`. Измеренный ноль — `0`. `NaN` и `Infinity`
запрещены. Пороговые решения считаются по целому числу пикселей, а не по
округлённой цифре интерфейса.

### `firms`

```json
{
  "support": "SUPPORTED",
  "hotspot_count": 3,
  "window_start": "2024-07-10T05:00:00Z",
  "window_end": "2024-08-01T05:00:00Z",
  "spatial_tolerance_m": 500,
  "product": "VIIRS",
  "confidence_filter": ["nominal", "high"],
  "source_refs": ["<source id>"],
  "matched_points_artifact_id": "firms-points"
}
```

`support`: `SUPPORTED`, `NOT_FOUND`, `NOT_CHECKED`. FIRMS-точки подтверждают
тепловые аномалии, но не являются периметром пожара.

### `artifacts`

Каждый файл: `artifact_id`, `role`, `relative_path`, `media_type`, `sha256`,
`size_bytes`. PNG/WebP также содержат `bounds_wgs84`, `width`, `height`.

Роли: `PREVIEW_BEFORE`, `PREVIEW_AFTER`, `DNBR_RASTER`, `AFFECTED_AREA`,
`FIRMS_POINTS`, `DNBR_PREVIEW`, `SWIR_BEFORE`, `SWIR_AFTER`.

## 3. Правила backend-oracle

1. Невалидный JSON, неверные hashes/geometry/files → отчёт отклоняется.
2. Coverage < 0.70 или отсутствуют metadata/grid/forest mask →
   `INSUFFICIENT + REVIEW_REQUIRED`.
3. Coverage 0.70–<0.85 либо temporal comparability не `YES` →
   `REVIEW_REQUIRED`.
4. `NO_CHANGE + SUFFICIENT` → `NO_RESTRICTION`.
5. Disturbance < 5 га или < 1% baseline forest → `REVIEW_REQUIRED`.
6. Порог пройден, но FIRMS не `SUPPORTED` → `REVIEW_REQUIRED`.
7. Все условия пройдены → `FREEZE_REQUESTED / FIRE_REVERSAL`.

Backend рассчитывает `evidence_hash = SHA-256(JCS(evidence))`. Поле хеша не
входит внутрь хешируемого evidence. Отдельно хешируется decision record.

## 4. REST API v1

Базовый путь: `/api/v1`.

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | API/DB/worker/chain/deployment |
| GET | `/plots` | Список проектов |
| GET | `/plots/{plot_id}` | Карточка проекта и доступные действия |
| POST | `/plots/{plot_id}/verify` | Запустить сценарий; ответ `202 + job_id` |
| GET | `/jobs/{job_id}` | Polling задания |
| GET | `/verifications/{id}` | Evidence, quality, decision и artifacts |
| GET | `/verifications/{id}/proof` | Recomputed/anchored hashes |
| GET | `/verifications/{id}/canonical` | Точные JCS-байты |
| GET | `/plots/{plot_id}/history` | История наблюдений |
| GET | `/plots/{plot_id}/credits` | Серии и реальные балансы |
| POST | `/plots/{plot_id}/issue` | Выпуск по demo authorization |
| POST | `/batches/{batch_id}/buy` | Тестовая покупка |
| POST | `/batches/{batch_id}/transfer` | Передача своего баланса |
| GET | `/operations/{operation_id}` | Polling транзакции |
| GET | `/events?plot_id=...` | Общий журнал |
| GET | `/artifacts/{artifact_id}` | Разрешённый файл из manifest |

Все POST требуют `Idempotency-Key`, `X-Demo-Session`, `X-Demo-Actor`.
Frontend проверяет HTTP status. `202` означает обработку, а не успех. Публичного
`POST /freeze` нет.

## 5. ABI смарт-контракта

Минимальные функции:

```solidity
setIssuer(address account, bool allowed)
setOracle(address account, bool allowed)
issue(bytes32 issuanceKey, string plotId, address seller,
      uint256 amount, uint256 unitPriceWei,
      bytes32 evidenceHash, uint64 observedAt) returns (uint256 batchId)
buy(uint256 batchId, uint256 amount) payable
transfer(uint256 batchId, address to, uint256 amount)
freeze(uint256 batchId, bytes32 evidenceHash, bytes32 decisionHash,
       uint64 observedAt, uint8 reasonCode)
balanceOf(uint256 batchId, address account) view returns (uint256)
getBatch(uint256 batchId) view returns (BatchView)
withdrawProceeds()
```

События: `Issued`, `Purchased`, `Transferred`, `Frozen`,
`ProceedsWithdrawn`, `IssuerPermissionChanged`, `OraclePermissionChanged`.

Обязательные ошибки: `Unauthorized`, `UnknownBatch`, `DuplicateIssuance`,
`InvalidAmount`, `InvalidAddress`, `InsufficientBalance`, `BatchNotActive`,
`IncorrectPayment`, `StaleObservation`.

Контракт обязан хранить реальные балансы по `batchId + address`. Заморозка
всего batch запрещает `buy` и `transfer` у любого держателя, но не уничтожает
балансы. Только owner назначает issuer/oracle. Backend передаёт 32 байта готового
SHA-256, не делает `keccak(text=hex_hash)`.

## 6. Форматы, которые нельзя менять самостоятельно

- Время: UTC `YYYY-MM-DDTHH:mm:ssZ`.
- GeoJSON: EPSG:4326, `[longitude, latitude]`.
- Расчёт: метрическая 20-метровая сетка; площадь по пикселям.
- `uint256` в REST: десятичная строка, чтобы JavaScript не терял точность.
- Hash JSON: `0x` + 64 строчных hex-символа.
- Evidence schema/API/ABI меняются только совместно производителем,
  потребителем и тимлидом.
