# Git и интеграция

## Ветки и merge

- `main` всегда проходит shared contract tests и остаётся демонстрируемым.
- Ветки: `feat/rs-*`, `feat/backend-*`, `feat/chain-*`, `feat/frontend-*`,
  `docs/*`, `fix/*`.
- Один PR решает одну проверяемую задачу. Автор указывает вход, выход, команды
  проверки, зависимые PR и изменение контрактов.
- Evidence contract смотрят RS + Backend; OpenAPI — Backend + Frontend; ABI —
  Blockchain + Backend; общую политику — Тимлид + Backend.
- Merge выполняет тимлид или Integration Owner после required checks.

## Contract change protocol

1. Создать запись: проблема, минимальная правка, потребители, автор и дедлайн.
2. Обновить источник: generator/Solidity spec/OpenAPI design.
3. Перегенерировать schemas/ABI/fixtures.
4. Обновить тесты и документы.
5. Получить согласие владельцев обеих сторон.
6. Merge одним совместимым набором; сообщить commit в общий чат.

Сообщение в чате не меняет контракт. Нельзя присылать `status_final2.json` как
новую версию без PR и test result.

## Stable release

- После E2E: tag `demo-stable-HHMM`, commit, data-manifest, policy hash,
  deployment ID/address/code hash, ABI hash.
- Экспериментальная ветка не заменяет stable, пока не пройдёт полный smoke.
- Rollback — checkout отдельного worktree/архива. Не применять destructive reset
  к незакоммиченным изменениям других людей.
- В release входят lock-файлы и `frontend/dist`; не входят `node_modules`,
  `.venv`, приватные ключи и большая неиспользуемая сырьёвая коллекция.

## Handoff между ноутбуками

- Bundle передаётся вместе с SHA-256 manifest.
- Два ноутбука содержат основной и запасной real-data пакет.
- Второй человек проверяет README в чистом терминале.
- `.env.example` содержит только имена переменных. Ключи Anvil остаются в
  локальном demo-сценарии и не используются с реальными активами.

## Правило для личных Claude-чатов

> Используй BOUNTYTEAM_MANIFEST и shared contracts v1.0.0 как обязательные
> границы. Не меняй API, JSON Schema, ABI, enum, единицы, время, хеширование и
> scope самостоятельно. При противоречии предложи минимальную правку и список
> потребителей; до решения сохраняй совместимость. Сообщи изменённые файлы,
> выполненные тесты, ограничения и следующий handoff.

Человек проверяет сгенерированный код. Ответ нейросети «всё готово» не является
результатом checkpoint.
