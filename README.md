# BountyTeam Carbon MRV

Hackathon monorepo for satellite verification of forest carbon-credit projects
and programmable temporary restrictions after a confirmed fire reversal.

## Carbon Lens — главный результат второго кейса

**Carbon Lens** — сервис инвестиционной проверки лесных углеродных проектов. Он отвечает не
на вопрос «сколько углерода в лесу», а на вопрос **подтверждаются ли заявленные углеродные
единицы**: фиксирует территорию и период, сравнивает фактическую динамику с общей базовой
линией, показывает качество наблюдений и раскрывает результат до зоны, ячейки, источника и
формулы. Не хватает данных — `Q = null`. Эффект не превышает базовую линию — `Q = 0`. Ни то,
ни другое не заменяется удобным числом.

Три роли: владелец подаёт заявку, верификатор запускает расчёт по официальным растрам и
подтверждает паспорт, инвестор видит только подтверждённое.

```bash
python3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-contracts.txt -r backend/requirements-backend.txt
./.venv/Scripts/python.exe -m backend.migrate
./.venv/Scripts/python.exe -m backend.serve --host 127.0.0.1 --port 8031   # переменные окружения — в файле по запуску
cd frontend && npm ci && npm run dev                                       # http://127.0.0.1:5173/lens?demo=1
```

Данные кейса (`data/`, `doc/`) лежат в репозитории — расчёт воспроизводится на чистом клоне
без скачивания. Весь путь без браузера:
`LIVE_REQUIRED=1 python -m backend.tools.live_composition`.

| Документ | О чём |
|---|---|
| [ФАЙЛ ПО ЗАПУСКУ.md](<ФАЙЛ ПО ЗАПУСКУ.md>) | запуск, зависимости, порядок воспроизведения расчёта, форматы входов и выходов, проверка хеша отчёта |
| [CARBON_LENS_HANDOFF.md](CARBON_LENS_HANDOFF.md) | полный контекст: методика, frozen rules, роли, архитектура, состояние работ |
| [docs/case2/SCORING_AUDIT.md](docs/case2/SCORING_AUDIT.md) | разбор по критериям оценки |
| [docs/case2/G0_CONTRACT.md](docs/case2/G0_CONTRACT.md) | контракт между модулями |
| [frontend/docs/LENS_INTEGRATION.md](frontend/docs/LENS_INTEGRATION.md) | граница интерфейса и сервиса |

Ниже — замороженный первый кейс (`/api/v1`, дашборд MRV и блокчейн). Он не менялся и к
Carbon Lens отношения не имеет.

## Source of truth

- Product rules: `docs/common/00_BOUNTYTEAM_MANIFEST.md`
- Architecture: `docs/common/01_ARCHITECTURE_AND_FLOW.md`
- Human-readable contracts: `docs/common/02_JSON_API_ABI_CONTRACTS.md`
- Evidence schema: `contracts/verification.schema.json`
- HTTP API: `contracts/openapi.yaml`
- Chain interface: `contracts/contract-interface.sol`
- Policy: `config/policy.v1.json`
- State semantics: `docs/common/status-machine.md`
- Pull Request workflow: `docs/common/07_PR_WORKFLOW.md`

Current contract baseline: `contracts-v1.0.0`.

## Modules

| Directory | Owner |
|---|---|
| `rs/` | Remote Sensing developer |
| `backend/` | Backend developer and Integration Owner |
| `blockchain/` | Blockchain developer |
| `frontend/` | Frontend developer and Demo Operator |
| `docs/` | Team Lead; shared contract changes require affected owners |

## Validate the shared package

Use Python **3.12** (reference version) or **3.13**, and Node.js **24.19.0**
from `.nvmrc` with its bundled npm. Use `npm ci --ignore-scripts` and the committed
`package-lock.json`; do not regenerate the lockfile or run `npm audit fix`.
See [the readiness audit](docs/common/08_READINESS_AUDIT.md) for verified platforms
and remaining blockers. The cross-platform CI matrix must pass before claiming
support on every platform.

After cloning, start with a clean working tree and synchronize the baseline:

```text
git fetch origin --tags
git switch main
git pull --ff-only origin main
```

On **Windows PowerShell**, verify that `python --version` reports 3.12 or 3.13:

```powershell
python -m venv .venv
$env:PYTHONUTF8='1'
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-contracts.txt
npm.cmd ci --ignore-scripts
python -m pytest -q
npm.cmd run check:abi
```

If execution policy blocks activation, skip activation and replace `python` in
the install/test commands with `.\.venv\Scripts\python.exe`; keep
`$env:PYTHONUTF8='1'` in that terminal. `npm.cmd` avoids the `npm.ps1` restriction.
No system execution-policy change or global Python dependency installation is needed.

On **macOS/Linux**, verify that `python3 --version` reports 3.12 or 3.13:

```bash
python3 -m venv .venv
source .venv/bin/activate
export PYTHONUTF8=1
python -m pip install -r requirements-contracts.txt
npm ci --ignore-scripts
python -m pytest -q
npm run check:abi
```

If the default interpreter differs, use an installed `python3.12`/`python3.13`
on macOS/Linux or `py -3.12`/`py -3.13` on Windows to create `.venv`.
Do not reuse a virtual environment copied from another OS.

Expected: **68 passed**; ABI `ok: true`, **9 functions**, **7 events**,
`specification_only: true`. These checks also validate schemas/OpenAPI, reproduce
canonical fixture bytes/hashes, and read the binary fixtures. They do not run
fixture generators or implement the application. Keep local private keys only
in environment variables (an untracked `.env` may supply them); never place
them in committed config or deployment manifests.

Build output stays untracked; package `frontend/dist` into the approved demo
release bundle when implemented, as required by the release plan.

## Branches

- `feat/rs-pipeline`
- `feat/backend-api`
- `feat/chain-registry`
- `feat/frontend-dashboard`
- `docs/teamlead`

No direct pushes to `main`. Team Lead or Integration Owner merges a reviewed PR
after required checks. Chat messages do not modify contracts.

## Important boundary

This baseline contains specifications and synthetic contract fixtures. It is not
the implemented application: runtime RS, backend, frontend and deployable smart
contract are built in the role branches.
