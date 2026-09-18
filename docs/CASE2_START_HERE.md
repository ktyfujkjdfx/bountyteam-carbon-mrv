# BountyTeam Carbon Lens — старт команды

## Что мы строим

**Carbon Lens — стресс-тест лесной углеродной инвестиции:** сколько потенциальной стоимости остаётся после baseline, неопределённости, проверки данных и резерва.

Изюминка продукта: **от инвестиционного вывода — до зоны карты, источника и формулы**.

Carbon Lens развивается поверх стабильного P0. P0 обнаруживает изменения леса, хранит воспроизводимое evidence и демонстрирует ограничения операций; новый кейс добавит расчёт запаса углерода, неопределённости, общей baseline, потенциальных единиц и паспорта результата. Эти возможности пока запланированы в roadmap и не должны описываться как уже реализованные.

Проверенная исходная точка:

- tag: `p0-integrated-v1.0.0`;
- commit tag и базовый `origin/main`: `5ba24ddb4b8f47099e7569613b9ce51ab16009e8`.

После merge bootstrap-PR единой стартовой точкой станет новый полный SHA `origin/main`. Не используйте HEAD старой bootstrap-ветки как командную базу.

## Авторитетные материалы

- [`../data/`](../data/) — официальный распакованный набор: 178 файлов, включая 168 GeoTIFF. `data/file_catalog.csv` описывает 177 исходных файлов и не включает собственный checksum.
- [`../doc/`](../doc/) — четыре исходных PDF: постановка задачи, критерии, описание данных и ссылка на данные.
- [`../data/methodology/baseline.csv`](../data/methodology/baseline.csv) и [`../data/methodology/parameters.csv`](../data/methodology/parameters.csv) — официальные baseline и параметры.
- [`../data/sources.csv`](../data/sources.csv) — версии, лицензии и обязательные attribution.

Официальные ZIP были доступны при bootstrap и проверены:

```text
data.zip             d8723225a1f66f1ff1890439e6e561f3a28a94f6a81b63b5db99a73579fc22a8
doc-1789730244.zip   f1e471dc909800a827d194c6baebb5e46c915b92bdf9deae0e65761d744a3cf7
```

Распакованные файлы побайтово сопоставлены с архивами; все пути, размеры и SHA-256 из `data/file_catalog.csv` совпадают. Подробности и команды находятся в [`case2/BOOTSTRAP_VERIFICATION.md`](case2/BOOTSTRAP_VERIFICATION.md).

Для конкурсной науки используются только `data/` и `doc/`. Сторонние GitHub-проекты служат инженерными и архитектурными ориентирами. Исключение — требуемая критериями демонстрация получения того же продукта совместимой версии из открытого источника; она не заменяет основной официальный набор.

## Roadmap и ownership

| Роль | Roadmap | Ответственность |
|---|---|---|
| RS | [`roadmaps/ROADMAP_RS.md`](roadmaps/ROADMAP_RS.md) | Растры, геометрия и площади, годовые запасы, изменение, зоны и evidence |
| Backend / Integration | [`roadmaps/ROADMAP_BACKEND.md`](roadmaps/ROADMAP_BACKEND.md) | G0 v2-контракт, jobs, orchestration, хранение, API и выдача отчёта |
| Frontend | [`roadmaps/ROADMAP_FRONTEND.md`](roadmaps/ROADMAP_FRONTEND.md) | `/lens`, карта и объяснение готовых значений API; научные величины на клиенте не рассчитываются |
| Carbon Methodology / Trust | [`roadmaps/ROADMAP_TRUST_BLOCKCHAIN.md`](roadmaps/ROADMAP_TRUST_BLOCKCHAIN.md) | Итоговая неопределённость, baseline, Q, сравнение заявления, паспорт и integrity |
| Team Lead | [`roadmaps/ROADMAP_TEAM_LEAD.md`](roadmaps/ROADMAP_TEAM_LEAD.md) | Методика, порядок PR, consumer-review, merge, исследование и защита |

Blockchain anchor необязателен и начинается только по отдельному решению Team Lead после готовности обязательного MVP.

## Получение актуальной стартовой точки

```bash
git clone https://github.com/ktyfujkjdfx/bountyteam-carbon-mrv.git
cd bountyteam-carbon-mrv
git fetch origin --tags --prune
git switch main
git pull --ff-only origin main
git status -sb
git status --porcelain
git log -1 --oneline
git tag --list
```

Перед началом работы дерево должно быть чистым, а `main` — совпадать с `origin/main`. Каждый разработчик полностью читает свой roadmap, `CLAUDE.md` в корне, инструкции своего модуля и официальные документы кейса.

## Первая волна

1. Backend открывает Draft PR G0 в ветке `feat/lens-g0-contracts` и согласует v2-контракт с RS, Trust, Frontend и Team Lead.
2. RS параллельно проводит RS-0 аудит форматов и готовит чистые функции для `feat/lens-rs-raster-core`, не фиксируя несовместимый интерфейс до G0.
3. Trust параллельно проводит Trust-0 аудит формул и метода uncertainty и готовит pure functions для `feat/lens-carbon-engine`.
4. Frontend параллельно проводит F0 mapping API → экран и готовит workspace/fixtures для `feat/lens-frontend-workspace`.

## Git и review

- Каждый этап выполняется в отдельной feature-ветке от актуального чистого `main`.
- Draft PR открывается после первого проверяемого результата; он содержит команды, фактические результаты, ограничения и consumer/handoff.
- Shared v2-контракт меняет Backend в G0. Остальные роли проводят consumer-review, но не создают собственные несовместимые версии.
- Автор не переводит свой PR в Ready и не merge. Ready и squash merge выполняет только Team Lead после независимого review и зелёных checks.
- Запрещены direct push в `main`, rebase общей истории, force-push, перемещение тегов и изменение frozen v1 без change protocol.
- После каждого этапа Claude сообщает SHA, PR, изменённые файлы, проверки и ограничения, затем останавливается до review/merge.

Все статусы и deliverables в roadmap являются планом будущей работы. Bootstrap не реализует RS-, Backend-, Frontend- или Trust-этапы нового MVP.
