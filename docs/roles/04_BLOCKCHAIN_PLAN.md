# BountyTeam — окончательный план Blockchain-разработчика

> Обязательный контекст: `00_BOUNTYTEAM_MANIFEST.md`,
> `01_ARCHITECTURE_AND_FLOW.md`, `02_JSON_API_ABI_CONTRACTS.md` и этот файл.
> Согласованный Solidity-интерфейс — граница. ABI создаётся компиляцией контракта,
> а не редактируется вручную.

## 1. Твоя роль и конечный результат

Ты реализуешь минимальный on-chain реестр серий углеродных единиц с настоящими
балансами, тестовой продажей, контролем доступа и ограничением обращения.

P0-результат:

- серия выпускается только issuer;
- тестовый покупатель платит точную demo-цену и получает настоящий баланс;
- держатель может передать ACTIVE units;
- только oracle может заморозить всю серию по evidence/decision hashes;
- после `FROZEN` прямые `buy` и `transfer` revert на уровне контракта;
- backend получает compiled ABI, deployment manifest, события и readback;
- весь основной сценарий стабильно работает на local Anvil без интернета.

Это не полный ERC-3643 и не production registry. Не выдавай локальную сеть за
независимую публичную инфраструктуру.

## 2. Нормативный интерфейс

Реализуй сигнатуры из общего контракта:

```solidity
setIssuer(address account, bool allowed)
setOracle(address account, bool allowed)

issue(
  bytes32 issuanceKey,
  string plotId,
  address seller,
  uint256 amount,
  uint256 unitPriceWei,
  bytes32 evidenceHash,
  uint64 observedAt
) returns (uint256 batchId)

buy(uint256 batchId, uint256 amount) payable
transfer(uint256 batchId, address to, uint256 amount)

freeze(
  uint256 batchId,
  bytes32 evidenceHash,
  bytes32 decisionHash,
  uint64 observedAt,
  uint8 reasonCode
)

balanceOf(uint256 batchId, address holder) view returns (uint256)
getBatch(uint256 batchId) view returns (...)
withdrawProceeds()
```

События минимум:

- `IssuerPermissionChanged(address indexed account, bool allowed)`
- `OraclePermissionChanged(address indexed account, bool allowed)`
- `Issued`
- `Purchased`
- `Transferred`
- `Frozen`
- `ProceedsWithdrawn`

Если используешь custom errors, их имена и ABI также фиксируются после contract
freeze. Backend сверяет ABI hash.

## 3. Модель данных и инварианты

### Доступ

- `owner` устанавливается в constructor.
- Только owner вызывает `setIssuer` и `setOracle`.
- Никто не может назначить себя агентом.
- `issue` — только issuer; `freeze` — только oracle.

### Batch

Batch хранит как минимум:

- `exists` — обязательно, чтобы default enum не сделал неизвестный batch ACTIVE;
- `plotId`, `seller`, `totalSupply`, `unitPriceWei`;
- `status: ACTIVE/FROZEN` (`REVOKED` зарезервирован, но не нужен P0);
- текущий `evidenceHash`, `decisionHash`, `lastObservedAt`;
- timestamps выпуска/заморозки.

### Балансы

```solidity
mapping(uint256 => mapping(address => uint256)) balances;
```

- При issue весь amount получает seller.
- Buy уменьшает seller inventory и увеличивает buyer balance.
- Transfer уменьшает баланс `msg.sender` и увеличивает получателя.
- `totalSupply` при buy/transfer не меняется.
- Нельзя только эмитить event без обновления ownership.

### Issue

- Уникальный `issuanceKey`.
- `plotId` не пустой; seller не zero.
- amount > 0; unitPriceWei > 0; evidenceHash не zero.
- observedAt допустим и становится baseline времени batch.
- Повторный issuance key revert.

### Buy

- Batch существует и `ACTIVE`.
- amount > 0; buyer не zero и не seller.
- У seller достаточно inventory.
- `msg.value == amount * unitPriceWei` с безопасной арифметикой Solidity 0.8+.
- Используй pull-payment: выручка накапливается, seller вызывает
  `withdrawProceeds`; не делай внешний ETH call до обновления состояния.

### Transfer

- Batch существует и `ACTIVE`.
- `to != address(0)` и `to != msg.sender`.
- amount > 0 и не превышает balance sender.
- После freeze любой прямой transfer revert независимо от backend/UI.

### Freeze

- Только oracle.
- Batch существует и `ACTIVE`.
- evidenceHash и decisionHash не zero.
- `observedAt >= lastObservedAt`; stale evidence reject.
- `reasonCode == 1` означает `FIRE_REVERSAL`.
- Заморозка batch-level: блокирует buy/transfer всех его units.
- P0 не включает automatic unfreeze/revoke.

## 4. Сеть, ключи и интеграция

- Основная среда: Anvil. Hardhat допустим, если вся команда уже на нём, но сеть
  должна быть одна.
- Sepolia — P2 и не может заменить стабильное local demo.
- Deployment script назначает owner/issuer/oracle demo accounts.
- Deployment manifest содержит chain ID, address, deploy tx, runtime code hash,
  compiler/settings, ABI hash и роли. Никаких private keys.
- Backend — единственный runtime oracle sender. Не создавай отдельный `oracle.py`,
  конкурирующий за nonce.
- Backend вызывает contract; frontend не ходит в RPC напрямую.

## 5. Приоритеты

### P0

- Рабочий contract по согласованному интерфейсу.
- Owner/issuer/oracle access control.
- Existence checks, unique issuance, настоящие balances.
- Issue, buy, transfer, freeze, withdraw.
- Events/custom errors.
- Unit tests и backend integration test.
- Local deploy/seed script, compiled ABI, deployment manifest, README.

### P1

- Более удобный event index/debug output, gas snapshot, one-command integration.

### P2

- Sepolia deploy/verification, расширенная compliance-модель — только после
  разрешения тимлида.

### CUT

Полный ERC-3643/T-REX suite, KYC/ONCHAINID, DAO, bridge, upgradeable proxy,
on-chain изображения/JSON, сложный marketplace, автоматический revoke/unfreeze.

## 6. Обязательные тесты

### Доступ и существование

- Посторонний не может `setIssuer`, `setOracle`, `issue`, `freeze`.
- Unknown batch отклоняется во всех relevant functions.
- Zero address/zero amount/zero hash/empty plot отклоняются.
- Duplicate issuance key отклоняется.

### Балансы и продажа

- Issue создаёт seller balance и totalSupply.
- Buy с точной оплатой двигает реальные балансы.
- Wrong payment, insufficient inventory и invalid amount revert.
- Transfer ACTIVE двигает balances, totalSupply неизменен.
- Withdraw работает и защищён от повторного вывода/reentrancy.

### Freeze

- Only oracle; reason code и hashes валидируются.
- Stale `observedAt` revert.
- `Frozen` event содержит ожидаемые hashes/status metadata.
- После freeze прямой `buy` revert.
- После freeze прямой `transfer` revert для seller и buyer.
- Повторный freeze не создаёт ложное новое событие.

### Интеграция

- ABI скомпилирован из exact source.
- Backend может decode все events и прочитать `getBatch/balanceOf`.
- Receipt status + event + readback совпадают.
- Перезапуск Anvil обнаруживается по deployment/code hash, а не даёт тихо
  работать со старым address.

## 7. До старта: 16–17 сентября

### Блок A — контракт, 3 часа

- Проверь правила о заранее написанном коде.
- Реализуй storage/access/invariants по интерфейсу.
- Напиши unit tests до UI-интеграции.

Результат: `forge test`/`hardhat test` проходит access, balances, buy, transfer,
freeze и negative cases.

### Блок B — deploy/handoff, 2–3 часа

- Подними Anvil, deploy, назначь роли.
- Сформируй compiled ABI и deployment manifest.
- Передай backend source commit, ABI hash, address и read commands.
- Вместе прогоните issue→buy→freeze→transfer revert.

### Блок C — резерв, 1–2 часа

- Подготовь exact clean-start commands.
- Научи backend-разработчика повторить deploy.
- Сохрани стабильный source/ABI/test report без secrets.

## 8. Почасовой план хакатона

### Пятница, 18:30–19:00

Уточни, обязателен ли конкретный chain/testnet, требуется ли ERC-3643 и есть ли
требование к explorer verification. Передай ответы тимлиду; не расширяй scope сам.

### 19:00–19:30

- Запусти согласованный local node.
- Compile/deploy exact contract.
- Назначь owner/issuer/oracle; создай deployment manifest.
- Передай backend ABI/address/hash.

Результат: backend подключается к живому контракту, не к мокам.

### 19:30–22:00

- Прогони access/existence tests.
- Совместно с backend: issue → getBatch/balance → buy → balances/readback.
- Исправь event decoding/ABI mismatch.
- Выведи понятный live log операций для диагностики.

Checkpoint 22:00: deploy стабилен; настоящие балансы меняются; неизвестный batch
и unauthorized calls revert.

### 22:00–02:00

- Интегрируй freeze с backend decision hashes.
- Проверь direct transfer до freeze успешен, после freeze revert.
- Проверь повторный запрос/idempotency на стороне backend и duplicate protection
  контракта.
- Зафиксируй e2e test и stable deployment manifest.

Checkpoint 02:00: receipt status=1, `Frozen` event декодирован, `getBatch`
возвращает FROZEN, direct RPC transfer revert. Затем handoff и сон.

### 02:15–07:45 — сон

Оставь clean-start/deploy/test команды и backup владельцу backend. Не оставляй
единственную рабочую конфигурацию только в своей shell history.

### 07:45–08:15

- Cold start Anvil + deploy/seed.
- Сверь code/ABI hashes.
- Backend повторяет подключение без ручной подмены address.

### 08:15–11:30

- Прогони real evidence hashes через тот же freeze path.
- Убедись, что insufficient/review cases не вызывают contract freeze.
- Отдай frontend только через backend реальные batch/balance/status/tx данные.
- Проверь buyer/recipient balances в demo accounts.

Checkpoint 11:30: один и тот же контракт обслуживает real/cached evidence;
decision остаётся ответственностью backend.

### 12:00–14:30

- Покажи эксперту минимальную модель и честно обозначь её границы.
- Исправляй только P0/security/rubric gaps.
- Не начинай внедрение полного ERC-3643 после совета «было бы хорошо».

### 14:30–16:30

- Заверши withdraw, error mapping, event docs и deploy README.
- Научи backend/тимлида cold deploy и event/readback check.
- Запиши стабильный tx/event набор для fallback.

Checkpoint 16:30: offline deploy, restart detection и post-freeze reverts проходят.

### 16:30–18:00

- Regression security/idempotency/deployment mismatch.
- Устрани только P0 bugs.
- В 18:00 freeze source/interface/ABI; новые функции запрещены.

### 18:00–20:00

- Полный test suite и integration test.
- Зафиксируй compiler/settings/source commit/ABI/code hashes.
- Помоги собрать release candidate и видео.

### 20:00–23:30

- Второй участник разворачивает contract по README.
- Проверь отсутствие secrets и real-network ключей.
- Сверь deployment manifest в загруженном release.

## 9. Точки интеграции

| Время | Что отдаёшь | Кому | Acceptance |
|---|---|---|---|
| Пт 19:30 | compiled ABI + deployment manifest | Backend | health/readback |
| Пт 22:00 | issue/buy/balance flow | Backend/Frontend через API | real balances |
| Сб 01:30 | freeze/event/revert flow | Backend | decoded event + readback |
| Сб 08:15 | cold deploy | Backend | deployment check passes |
| Сб 16:30 | fallback logs/manifests | Тимлид | offline smoke |
| Сб 18:00 | frozen source/ABI/tests | Release Owner | hashes recorded |

Блокер больше 20 минут — exact failing test/revert/data и сообщение тимлиду.

## 10. Acceptance criteria Blockchain

- [ ] Owner задан constructor; role management onlyOwner.
- [ ] Unknown batch не считается ACTIVE из-за default enum.
- [ ] Issuer/oracle permissions проверяются контрактом.
- [ ] Duplicate issuance key и invalid inputs revert.
- [ ] Реальные per-holder balances существуют.
- [ ] Issue/buy/transfer корректно двигают balances; supply инвариантен.
- [ ] Exact payment и seller proceeds проверены.
- [ ] Freeze принимает raw bytes32 evidence/decision hashes без повторного hashing.
- [ ] Stale observation/repeat freeze отклоняются.
- [ ] Direct buy/transfer после freeze revert на contract level.
- [ ] Events декодируются backend; receipt/event/readback совпадают.
- [ ] ABI получен компиляцией exact source; hashes записаны.
- [ ] Local deploy воспроизводится другим участником.
- [ ] Ни одного secret/private key в репозитории.

## 11. Fallbacks

- Sepolia/RPC internet не работает → local Anvil, основной предусмотренный режим.
- Local deployment потерян → clean deploy + seed из скрипта; frontend/backend
  получают новый manifest через штатный startup, не ручную правку.
- ABI mismatch → откат к last stable source+compiled ABI; не редактировать JSON.
- Backend oracle временно сломан → показать unit/integration test и сохранённый
  event/readback; UI не должен притворяться, что новая tx confirmed.
- Транзакция timeout → backend reconciliation; не отправлять вручную дубль nonce.

## 12. Что говорить на защите, 40–60 секунд

> Контракт хранит не картинки, а состояние серии и криптографические hashes
> evidence и решения. Выпуск разрешён issuer, заморозка — только oracle; назначить
> себя агентом нельзя. У каждой серии есть реальные балансы владельцев и
> тестовая цена: покупка меняет on-chain balances. После подтверждённого
> `FIRE_REVERSAL` вся серия временно получает статус `FROZEN`, и прямые buy и
> transfer отклоняются самим контрактом, не только интерфейсом. Это минимальный
> прототип бизнес-логики; production-версия потребует identity/compliance и
> governance, например на базе ERC-3643.

## 13. Что запрещено менять самостоятельно

- Сигнатуры, events, ABI semantics, reason codes и status enum.
- Создавать публичный `addAgent` или обход role checks.
- Делать «transfer» только событием без balances.
- Добавлять второй oracle script/signer параллельно backend.
- Выдавать Sepolia/полный ERC-3643 за реализованный P0.
- Добавлять unfreeze/revoke без общей governance и change protocol.

## 14. Формат отчёта на sync

```text
CHAIN <время>
Source commit: <hash>
Network/deployment: <chain id + address>
ABI/code hash: <hashes>
Tests: <passed/failed>
Last tx: <operation + receipt/readback>
Blocker: <failing test/revert or none>
Next handoff: <кому, что, время>
```
