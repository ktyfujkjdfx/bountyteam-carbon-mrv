# Carbon Lens bootstrap verification

Дата проверки: 18 сентября 2026 года.

## Исходная точка и scope

- Репозиторий: `https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv.git`.
- Ветка bootstrap: `chore/carbon-lens-bootstrap`.
- Базовый `origin/main`: `5ba24ddb4b8f47099e7569613b9ce51ab16009e8`.
- `p0-integrated-v1.0.0^{commit}`: `5ba24ddb4b8f47099e7569613b9ce51ab16009e8`.
- Stable tag является предком базового main.

Bootstrap добавляет только официальные входные материалы, roadmap, стартовую и проверочную документацию и минимальные правила Git для побайтового хранения материалов. Приложение, научные вычисления, frozen contracts, ABI, fixtures, tests и workflows не менялись.

## Официальные архивы и распакованные материалы

Архивы были доступны во время проверки. Они не добавляются в Git.

| Архив | SHA-256 | Результат |
|---|---|---|
| `data.zip` | `d8723225a1f66f1ff1890439e6e561f3a28a94f6a81b63b5db99a73579fc22a8` | Совпадает с ожидаемым; 178 файлов |
| `doc-1789730244.zip` | `f1e471dc909800a827d194c6baebb5e46c915b92bdf9deae0e65761d744a3cf7` | Совпадает с ожидаемым; 4 PDF |

Каждый распакованный файл сопоставлен с одноимённой записью официального ZIP по SHA-256. Расхождений, пропусков и дополнительных исходных файлов нет.

### `data/`

- файлов: 178;
- GeoTIFF: 168;
- общий размер: 46 128 365 байт (43,99 MiB);
- пустых файлов: 0;
- файлов больше 100 MiB: 0;
- максимальный файл: `data/scene_metadata.json`, 2 249 626 байт;
- `file_catalog.csv`: 177 записей; сам каталог в собственный список не входит;
- SHA-256 `data/file_catalog.csv`: `c466734e505e16bf71f052290c633b22e809d042fed381ffc200913403d45435`;
- SHA-256 `data/methodology/baseline.csv`: `403c58581b7c246c0833d66a8d743bd6c2ec148caa81cbdd3b560525f264307d`;
- SHA-256 `data/methodology/parameters.csv`: `2bca8c22e73231f4b7ae256657fba5e8e8ec4916cd934a0c4e6b92000da37ec6`.

Проверено:

- все пути из `file_catalog.csv` существуют;
- размер и SHA-256 всех 177 перечисленных файлов совпадают;
- CSV читаются как UTF-8-SIG, JSON/GeoJSON — как UTF-8;
- все GeoJSON синтаксически корректны;
- все 168 GeoTIFF открываются через rasterio и имеют CRS, положительные dimensions и bands/dtype;
- присутствуют AOI `RU_TVER_01`, `RU_VOLOGDA_02`, `RU_MORDOVIA_03`, `RU_MORDOVIA_04`;
- присутствует запрос `CHECK_TRANSFER_01`;
- отсутствуют проверяемые признаки secrets и абсолютные пользовательские пути.

### `doc/`

| Файл | Размер | Страниц | SHA-256 |
|---|---:|---:|---|
| `Критерии_оценки_—_Верификация_углеродных_кредитов.pdf` | 440 688 | 4 | `88061b42c40120a41dc75383c91210b0629f06bc4568dd9083c3db1dfa19f678` |
| `Описание_данных_—_Верификация_углеродных_кредитов.pdf` | 653 398 | 7 | `3693c93de87e6551d18b0011dfbd3c73586b09cd022addd00032ca41a3ce14df` |
| `Постановка_задачи_—_Верификация_углеродных_кредитов.pdf` | 633 540 | 8 | `417b91b849704decdb4f3fb3a5970cc208c45f9bf1d5a4f6b1d15f9e5ecd219d` |
| `Ссылка_на_данные.pdf` | 88 453 | 1 | `1e1e4a7e2fa3ece65b86890dbc547c879ad3ce5720f2fcf20fc24cfee0021aed` |

Все PDF читаются и содержат извлекаемый текст. Общий размер `doc/`: 1 816 079 байт. Проверяемые признаки secrets и абсолютных пользовательских путей не обнаружены.

### Распространение и attribution

Авторитетный перечень находится в `data/sources.csv`. Для результатов необходимо сохранить, среди прочего:

- ESA Biomass CCI v7.0: Santoro M.; Cartus O. (2026), NERC EDS CEDA, DOI `10.5285/6429d1aafe1e43b9b414e4a5a7f8b903`, с благодарностью ESA Climate Change Initiative и Biomass CCI team;
- Sentinel-2: `Contains modified Copernicus Sentinel data 2019–2024`, доступ через Element 84 Earth Search;
- Hansen Global Forest Change 2025 v1.13: Hansen et al. (2013), University of Maryland / GLAD, CC BY 4.0;
- MODIS MCD64A1 v6.1: Giglio, Justice, Boschetti, Roy; NASA LP DAAC; DOI `10.5067/MODIS/MCD64A1.061`;
- коэффициенты и метод: IPCC 2006, Volume 4, Chapters 2 and 4;
- baseline, вычеты, резерв и цены: сценарные правила кейса SR Data, а не внешние научные значения.

`.gitignore` больше не исключает официальный `data/`. `.gitattributes` задаёт `data/** -text` и `doc/** -text`, чтобы clone получал точные байты, включая UTF-8 BOM. LFS pointers отсутствуют; размер крупнейшего файла не требует Git LFS.

## Roadmap

Проверены полностью:

- `docs/roadmaps/ROADMAP_RS.md`;
- `docs/roadmaps/ROADMAP_BACKEND.md`;
- `docs/roadmaps/ROADMAP_FRONTEND.md`;
- `docs/roadmaps/ROADMAP_TRUST_BLOCKCHAIN.md`;
- `docs/roadmaps/ROADMAP_TEAM_LEAD.md`.

Каждый начинается обязательным правилом источников. Планы сохраняют P0 как основу и регрессионный контур, назначают Backend владельцем G0, RS владельцем растров/площадей/запасов/evidence, Trust владельцем итоговой uncertainty/baseline/Q/паспорта, а Frontend — потребителем готовых API-величин. Blockchain anchor отмечен как необязательный этап после обязательного MVP. Ветки, зависимости, consumer-review, запрет self-Ready/self-merge и остановки Claude указаны.

Исходный Team Lead roadmap был старее четырёх role roadmap. По разрешению Team Lead в него добавлены единая data policy и статус v2, согласованные имена веток, ownership uncertainty и исключение для проверенного официального `data/`. Остальная структура управления, checkpoints и защита сохранены.

## Окружение

```text
Windows NT 10.0.26200.0
PowerShell 5.1.26100.9444
Git 2.55.0.windows.3
Python 3.12.10
pytest 8.4.2
rasterio 1.4.3 / GDAL 3.9.3
pypdf 6.19.0
Node.js 24.19.0
npm 11.17.0
Playwright 1.63.0
Browser: installed Microsoft Edge channel (msedge)
```

## Регрессия P0

| Команда | Фактический результат |
|---|---|
| `.venv\\Scripts\\python.exe -m pytest -q` | PASS — 139 passed |
| `.venv\\Scripts\\python.exe -m pytest backend -q -rs` | PASS — 123 passed, 3 skipped |
| `.venv\\Scripts\\python.exe -m pytest rs/tests -q` | PASS — 71 passed |
| `npm.cmd run check:abi` | PASS — 9 functions, 7 events, `specification_only: true` |
| `npm.cmd ci` в `frontend/` | PASS — 270 packages installed from lockfile |
| `npm.cmd run verify` в `frontend/` | PASS — check:api, lint, typecheck, 110 tests, build, check:dist |
| `E2E_BROWSER_CHANNEL=msedge E2E_BASE_URL=http://127.0.0.1:4173 npx playwright test "e2e/demo-flow.spec.ts"` | PASS — 4 passed |
| `git diff --check` | PASS |

Backend skips:

- 2 real-Anvil E2E tests требуют `BACKEND_E2E_*` и локального deployment;
- 1 symlink escape test пропущен, потому что текущий Windows token не имеет privilege создания symlink.

Это ограничения окружения, а не скрытые PASS. Полный real-Anvil E2E в bootstrap не запускался. Первый Playwright запуск со встроенным `webServer` выполнил все 4 теста, но завис при завершении preview process и был прерван; затем suite повторена против отдельно поднятого локального preview и завершилась с exit code 0, `4 passed`.

Pytest сообщил предупреждение о невозможности создать `.pytest_cache`; результаты тестов не затронуты, а cache не попал в Git.

## Инварианты bootstrap

- Нет изменений в `backend/`, `rs/`, `frontend/src/`, `blockchain/`, `contracts/`, `fixtures/`, `tests/`, `config/` и `.github/workflows/`.
- Frozen ABI и contracts не изменены; ABI проверен существующей командой.
- Теги не создавались, не перемещались и не перезаписывались.
- ZIP-дубликаты, `.env`, credentials, runtime, cache, `.venv`, `node_modules`, `dist`, test-results и editor files в commit не входят.
- Новый кейс в bootstrap не реализуется; roadmap имеет статус плана.

## Ограничения и следующий gate

- GitHub Actions и clean-clone проверка фиксируются после push Draft PR на точном PR HEAD.
- Draft PR не переводится в Ready и не merge без отдельного разрешения Team Lead.
- После разрешённого merge команда должна использовать проверенный новый SHA `origin/main`, а не SHA bootstrap-ветки.
