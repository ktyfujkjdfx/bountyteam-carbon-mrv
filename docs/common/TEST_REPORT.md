# Test report — shared contracts v1.0.0

Дата прогона: **16 сентября 2026**.

## Результат

```text
.................................................................... [100%]
68 passed
```

После регенерации JSON Schema, OpenAPI, policy и fixtures полный набор снова
прошёл: **68/68**. ABI freshness отдельно проверена компилятором:

```json
{
  "ok": true,
  "compiler": "0.8.30+commit.73712a01.Emscripten.clang",
  "functions": 9,
  "events": 7,
  "specification_only": true
}
```

## Покрытые интеграционные риски

- JSON Schema Draft 2020-12 и OpenAPI 3.1 validation.
- Три evidence outcomes и ожидаемые policy decisions.
- JCS/SHA-256, tampered artifact и неверный geometry hash.
- Повторный расчёт NDVI/dNBR/area из synthetic GeoTIFF.
- Файлы PNG/GeoJSON/GeoTIFF, совпадение bounds и grid.
- Неверные даты, non-finite numbers, path traversal и чужие поля.
- Границы coverage 0.70/0.85, 5 га и 1%.
- Запрет `FROZEN`, `confidence`, `evidence_hash` во входе RS.
- OpenAPI responses/requests и отсутствие публичной freeze-ручки.
- Компиляторное происхождение ABI и фиксированные сигнатуры.

## Что этот отчёт не доказывает

Не реализованы и не тестировались runtime backend/frontend, deployable Solidity
contract, Anvil receipt/nonce/restart и реальные Sentinel-2/FIRMS данные. Эти
проверки входят в Definition of Done приложения и индивидуальные планы.
