import { useCallback, useState } from 'react';
import { Empty, Section, Skeleton } from '../../components/common';
import type { LensSession } from '../auth';
import { PASSPORT_STATUS_TEXT, passportStatusOf, type Submission, type SubmissionStatus } from '../workspace';
import type { WorkspaceState } from '../useWorkspace';
import { errorRu } from '../ru';
import type { Notify } from '../notify';
import { LensMapView } from './LensMapView';
import { LifecyclePanel } from './LifecyclePanel';
import { PassportPanel } from './PassportPanel';
import { RequestForm } from './RequestForm';
import { ResultView } from './ResultView';
import { FIXTURE_SCENARIO_ORDER, FIXTURE_LABELS, SCENARIO_DEFAULTS } from '../fixtures';

/** Одна фраза на каждое состояние заявки: ни одно состояние не рисуется пустым абзацем. */
const OWNER_STATUS_TEXT: Record<SubmissionStatus, string> = {
  DRAFT: 'Черновик: заявка ещё не подана на проверку.',
  SUBMITTED: 'Заявка подана и ждёт верификатора: расчёт запускает он, а не вы.',
  ANALYSING: 'Сервис считает заявку. Результат появится здесь сам, когда расчёт закончится.',
  CALCULATED: 'Расчёт выполнен верификатором. Числа видны вам как владельцу заявки; инвестор увидит их после подтверждения.',
  FINALIZED: 'Верификатор подтвердил результат. Паспорт можно скачать и проверить.',
  INTEGRITY_FAILED: 'Целостность паспорта не подтверждена: содержимое изменилось после фиксации.',
  UNKNOWN: 'Сервис сообщил состояние, которого этот клиент не знает. Обновите клиент, чтобы работать с этой заявкой.',
};

function SubmissionRow({ submission, active, onOpen }: { submission: Submission; active: boolean; onOpen: () => void }) {
  const status = PASSPORT_STATUS_TEXT[passportStatusOf(submission)];
  const q = submission.result?.units.q ?? null;
  // Заявка может иметь расчёт, который этой роли ещё не показывают: сервис отдаёт чужой результат
  // только после подтверждения. Это не «не считали».
  const hidden = q === null && submission.analysis_id !== null;
  const submitted = new Date(submission.created_at);
  return (
    <li>
      <button type="button" className={`lens-history-item${active ? ' selected' : ''}`} onClick={onOpen} aria-pressed={active} data-testid={`lens-submission-${submission.submission_id}`}>
        <span className="lens-history-head">
          <span>
            {submission.title} · {submission.year_start}–{submission.year_end}
          </span>
          <span className={`badge tone-${status.tone}`}>{status.label}</span>
        </span>
        <span className="lens-history-meta">
          <span className="small lens-open-hint">{active ? 'открыто' : 'открыть →'}</span>
          <span className="small">
            подана {Number.isNaN(submitted.getTime()) ? '—' : submitted.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
          </span>
          <span className="small">
            единиц: {q !== null ? q.toLocaleString('ru-RU') : hidden ? 'скрыто до подтверждения' : 'не считали'}
          </span>
          {submission.claimed_units !== null && <span className="small">заявлено {submission.claimed_units.toLocaleString('ru-RU')}</span>}
        </span>
      </button>
    </li>
  );
}

function ResultArea({ workspace, session, showClaim, showValue, withMap }: { workspace: WorkspaceState; session: LensSession; showClaim: boolean; showValue: boolean; withMap?: boolean }) {
  const { analysis, shownResult } = workspace;
  void session;
  return (
    <>
      {analysis.state.phase === 'submitting' && <Skeleton label="Отправляем запрос сервису…" height={140} />}
      {analysis.state.phase === 'polling' && <Skeleton label="Сервис считает. Это занимает до минуты — страницу можно не трогать" height={140} />}
      {analysis.state.phase === 'timeout' && (
        <div className="state state-warn" role="status" data-testid="lens-timeout">
          <strong>Расчёт ещё выполняется</strong>
          <span>Мы перестали ждать ответ, но расчёт на сервисе не отменён. Откройте заявку позже или запустите проверку снова.</span>
        </div>
      )}
      {analysis.state.phase === 'error' && analysis.state.error && (
        <div className="state state-error" role="alert" data-testid="lens-error">
          <strong>{errorRu(analysis.state.error.code) ?? 'Расчёт не выполнен'}</strong>
          <span>{analysis.state.error.message}</span>
          {analysis.state.error.detail && <span className="muted small">{analysis.state.error.detail}</span>}
          <span className="muted small">Офлайн-набор не подставляется вместо ответа сервиса: числа на экране либо посчитаны, либо их нет.</span>
          <details className="lens-tech">
            <summary>Технические подробности</summary>
            <div className="lens-tech-body">
              <span className="mono small">{analysis.state.error.code}</span>
            </div>
          </details>
        </div>
      )}
      {shownResult ? (
        <ResultView
          result={shownResult}
          priceKey={workspace.priceKey}
          onPriceKey={workspace.setPriceKey}
          customPrice={workspace.customPrice}
          onCustomPrice={workspace.setCustomPrice}
          selectedZoneId={workspace.selectedZoneId}
          onSelectZone={workspace.setSelectedZoneId}
          cells={workspace.cells}
          selectedCellId={workspace.selectedCellId}
          onShowCells={() => void workspace.showCells()}
          snapshots={workspace.snapshots}
          onShowSnapshots={() => void workspace.showSnapshots()}
          showClaim={showClaim}
          showValue={showValue}
          onDownloadReport={workspace.downloadReport}
          {...(withMap ? { mapSlot: <MapArea workspace={workspace} /> } : {})}
        />
      ) : (
        analysis.state.phase === 'idle' && (
          <Empty>
            <strong>Результата пока нет</strong>
            <span>Откройте заявку из списка выше или запустите проверку.</span>
          </Empty>
        )
      )}
    </>
  );
}

function MapArea({
  workspace,
  pickable,
  openByArea,
  notify,
  emptyHint,
}: {
  workspace: WorkspaceState;
  /** Клик по участку подставляет его в черновик новой заявки (экран владельца). */
  pickable?: boolean;
  /** Клик по участку открывает заявку по этому участку из переданного списка. */
  openByArea?: Submission[];
  notify?: Notify;
  /** Кто может помочь, если по участку ещё нечего показывать. */
  emptyHint?: string;
}) {
  const areas = workspace.catalog?.areas;
  // Карта выбора участка живёт черновиком новой заявки, а не показанным результатом: иначе обзор
  // всех участков не виден, пока открыта хоть одна заявка.
  const geometry = pickable ? workspace.draft.geometry : workspace.shownResult?.request.geometry ?? workspace.draft.geometry;
  const { setDraft, setActiveSubmissionId, draft } = workspace;

  // Обработчики обязаны быть стабильными: карта перерисовывает слои, когда они меняются, и
  // новая функция на каждом рендере убирала бы слой из-под курсора между нажатием и щелчком.
  const pickDraft = useCallback(
    (aoiId: string) => {
      const area = areas?.find((item) => item.aoi_id === aoiId);
      if (!area) {
        notify?.({ tone: 'warn', title: 'Участок не выбран', text: `Сервис не отдал контур участка ${aoiId}.` });
        return;
      }
      setDraft({
        ...draft,
        aoiId: area.aoi_id,
        geometry: area.geometry,
        geometrySource: `участок каталога ${area.aoi_id}`,
        yearStart: area.analysis_start_year,
        yearEnd: area.analysis_end_year,
      });
      notify?.({
        tone: 'ok',
        title: `Участок выбран: ${area.region}`,
        text: `${area.aoi_id}, период ${area.analysis_start_year}–${area.analysis_end_year}.`,
        hint: 'Площадь измеряет сервис — она появится в форме заявки.',
      });
    },
    [areas, draft, notify, setDraft],
  );

  const openSubmission = useCallback(
    (aoiId: string) => {
      const match = openByArea?.find((item) => item.aoi_id === aoiId);
      if (match) {
        setActiveSubmissionId(match.submission_id);
        notify?.({ tone: 'ok', title: 'Заявка открыта', text: `${match.title}, ${match.year_start}–${match.year_end}.` });
        return;
      }
      notify?.({
        tone: 'warn',
        title: 'По этому участку показывать нечего',
        text: `Данных по участку ${aoiId} в этом списке нет.`,
        ...(emptyHint ? { hint: emptyHint } : {}),
      });
    },
    [emptyHint, notify, openByArea, setActiveSubmissionId],
  );

  const isAreaOpenable = useCallback(
    (aoiId: string) => (openByArea ?? []).some((item) => item.aoi_id === aoiId),
    [openByArea],
  );
  return (
    <LensMapView
      geometry={geometry}
      {...(areas ? { areas } : {})}
      {...(pickable && areas ? { onPickArea: pickDraft, pickHint: 'выбрать его для заявки' } : {})}
      {...(!pickable && openByArea && areas
        ? { onPickArea: openSubmission, pickHint: 'открыть заявку по нему', isAreaOpenable }
        : {})}
      result={pickable ? null : workspace.shownResult}
      cells={pickable ? { kind: 'hidden' } : workspace.cells}
      gaps={pickable ? { kind: 'hidden' } : workspace.gaps}
      selectedZoneId={workspace.selectedZoneId}
      onSelectZone={workspace.setSelectedZoneId}
      selectedCellId={workspace.selectedCellId}
      onSelectCell={workspace.setSelectedCellId}
      drawing={workspace.drawing}
      onDrawn={(geometry) => {
        workspace.setDraft({ ...workspace.draft, aoiId: null, geometry, geometrySource: 'нарисованный контур' });
        workspace.setDrawing(false);
      }}
    />
  );
}

/** Шаги подачи заявки: человеку видно, где он находится и сколько осталось. */
function OwnerStepper({ step }: { step: 1 | 2 | 3 }) {
  const steps: Array<[number, string]> = [
    [1, 'Выбрать участок'],
    [2, 'Указать период и объём'],
    [3, 'Отправить на проверку'],
  ];
  return (
    <ol className="lens-stepper" data-testid="lens-stepper">
      {steps.map(([number, label]) => (
        <li key={number} data-state={number === step ? 'current' : number < step ? 'done' : 'todo'}>
          <span className="lens-step-number">{number < step ? '✓' : number}</span>
          <span>{label}</span>
        </li>
      ))}
    </ol>
  );
}

/** Владелец: подать участок, следить за обработкой, прочитать замечания и паспорт. */
export function OwnerWorkspace({ workspace, session, notify }: { workspace: WorkspaceState; session: LensSession; notify: Notify }) {
  const mine = workspace.submissions.filter((item) => item.owner_email === session.username);
  const active = workspace.activeSubmission;
  const step: 1 | 2 | 3 = workspace.draft.geometry === null ? 1 : workspace.measurement === null ? 2 : 3;

  return (
    <div className="lens-single">
      <Section title="Новая заявка" id="lens-new-request">
        <OwnerStepper step={step} />
        <RequestForm
          catalog={workspace.catalog}
          catalogLoading={workspace.catalogLoading}
          draft={workspace.draft}
          onDraft={workspace.setDraft}
          measurement={workspace.measurement}
          measuring={workspace.measuring}
          measureError={workspace.measureError}
          drawing={workspace.drawing}
          onToggleDrawing={() => workspace.setDrawing(!workspace.drawing)}
          onSubmit={() => void workspace.submitRequest(workspace.draft.aoiId ?? 'Контур пользователя')}
          submitLabel="Отправить на проверку"
          busy={workspace.analysis.busy}
          allowClaim
          error={workspace.requestError}
        />
      </Section>

      <Section title="Карта участков" id="lens-owner-map">
        <p className="lens-tab-lead">Нажмите на участок, чтобы взять его в заявку. Площадь измерит сервис.</p>
        <MapArea workspace={workspace} pickable notify={notify} />
      </Section>

      <Section title={`Мои заявки${mine.length > 0 ? ` · ${mine.length}` : ''}`} id="lens-my-requests">
        {mine.length === 0 ? (
          <Empty>
            <strong>Заявок пока нет</strong>
            <span>Подайте первую: выберите участок в форме выше и отправьте на проверку.</span>
          </Empty>
        ) : (
          <ul className="lens-history-list scroll-list" data-testid="lens-my-requests">
            {mine.map((submission) => (
              <SubmissionRow key={submission.submission_id} submission={submission} active={submission.submission_id === active?.submission_id} onOpen={() => workspace.setActiveSubmissionId(submission.submission_id)} />
            ))}
          </ul>
        )}
      </Section>

      {active && (
        <Section title="Что с моей заявкой" id="lens-status">
          <button type="button" className="btn btn-small btn-secondary" onClick={workspace.clearActiveSubmission} data-testid="lens-back">
            ← Ко всем заявкам
          </button>
          <p data-testid="lens-owner-status">{OWNER_STATUS_TEXT[active.status]}</p>
          {active.notes.length > 0 && (
            <>
              <h3>Замечания верификатора</h3>
              <ul className="limitations small" data-testid="lens-verifier-notes">
                {active.notes.map((note) => (
                  <li key={note.note_id}>
                    <strong>{note.author}</strong> · {new Date(note.created_at).toLocaleString('ru-RU')}
                    <div>{note.text}</div>
                  </li>
                ))}
              </ul>
            </>
          )}
          <ResultArea workspace={workspace} session={session} showClaim showValue />
          {active.result && (
            <PassportPanel
              result={active.result}
              proof={workspace.proof}
              status={passportStatusOf(active)}
              submittedBy={active.owner_email}
              finalizedBy={active.finalized_by}
              finalizedAt={active.finalized_at}
              onIntegrityFailed={() => workspace.markIntegrityFailed(active)}
            />
          )}
        </Section>
      )}
    </div>
  );
}

/** Верификатор: очередь, расчёт, замечания и подтверждение. */
export function VerifierWorkspace({ workspace, session, offline, notify }: { workspace: WorkspaceState; session: LensSession; offline: boolean; notify: Notify }) {
  const [note, setNote] = useState('');
  const [scenario, setScenario] = useState(FIXTURE_SCENARIO_ORDER[0]);
  const active = workspace.activeSubmission;
  const running = workspace.analysis.busy || active?.status === 'ANALYSING';

  return (
    <div className="lens-single">
      <Section title={`Заявки на проверку${workspace.submissions.length > 0 ? ` · ${workspace.submissions.length}` : ''}`} id="lens-queue">
        {workspace.submissions.length === 0 ? (
          <Empty>
            <strong>Очередь пуста</strong>
            <span>Заявки появятся здесь, когда владелец их отправит. Для показа войдите владельцем и подайте заявку.</span>
          </Empty>
        ) : (
          <ul className="lens-history-list scroll-list" data-testid="lens-queue-list">
            {workspace.submissions.map((submission) => (
              <SubmissionRow key={submission.submission_id} submission={submission} active={submission.submission_id === active?.submission_id} onOpen={() => workspace.setActiveSubmissionId(submission.submission_id)} />
            ))}
          </ul>
        )}
      </Section>

      {offline && (
        <Section title="Набор значений офлайн-режима" id="lens-scenario">
          <label className="lens-field">
            <span>Помеченный набор</span>
            <select className="select" value={scenario} onChange={(event) => setScenario(event.target.value as typeof scenario)} data-testid="lens-scenario-select">
              {FIXTURE_SCENARIO_ORDER.map((id) => (
                <option key={id} value={id}>
                  {SCENARIO_DEFAULTS[id].acceptance ? `${SCENARIO_DEFAULTS[id].acceptance} · ` : ''}
                  {FIXTURE_LABELS[id].label}
                </option>
              ))}
            </select>
            <span className="lens-field-note">Офлайн-режим отвечает готовым набором. Это не расчёт по выбранному участку.</span>
          </label>
        </Section>
      )}

      {!workspace.shownResult && (
        <Section title="Карта участков" id="lens-verifier-map">
          <p className="lens-tab-lead">Нажмите на участок на карте или строку в очереди, чтобы открыть заявку.</p>
          <MapArea
            workspace={workspace}
            openByArea={workspace.submissions}
            notify={notify}
            emptyHint="Заявку по участку подаёт владелец проекта — до этого проверять нечего."
          />
        </Section>
      )}

      <Section title="Проверка заявки" id="lens-decision">
        {active ? (
          <>
            <div className="lens-actions">
              <button type="button" className="btn btn-small btn-secondary" onClick={workspace.clearActiveSubmission} data-testid="lens-back">
                ← Ко всей очереди
              </button>
              <span className="muted small">
                {active.title} · {active.year_start}–{active.year_end}
              </span>
            </div>
            <p className="lens-tab-lead">
              {running
                ? 'Сервис считает по спутниковым данным. Кнопка снова станет активной, когда расчёт закончится.'
                : active.result
                  ? 'Расчёт уже выполнен. Его можно пересчитать, а можно подтвердить — тогда результат увидит инвестор.'
                  : 'Нажмите «Проверить проект»: сервис посчитает результат по официальным данным. Это занимает до минуты.'}
            </p>
            <div className="lens-actions">
              <button
                type="button"
                className="btn lens-run"
                onClick={() => void workspace.runAnalysis(active, offline ? scenario : undefined)}
                // Три независимые причины отказать, и все три сервис проверяет сам. Кнопка следует
                // сервису, а не только флагу этой вкладки: после перезагрузки во время расчёта флаг
                // уже false, а заявка всё ещё ANALYSING.
                disabled={workspace.analysis.busy || active.status === 'ANALYSING' || active.status === 'UNKNOWN'}
                data-testid="lens-run-analysis"
              >
                {running ? 'Расчёт выполняется…' : active.result ? 'Пересчитать' : 'Проверить проект'}
              </button>
              <button
                type="button"
                className="btn btn-small btn-secondary"
                onClick={() => void workspace.finalize(active, session.username)}
                disabled={!active.result || active.status === 'FINALIZED' || active.status === 'UNKNOWN'}
                data-testid="lens-finalize"
              >
                Подтвердить результат
              </button>
            </div>
            {!active.result && <p className="muted small">Подтвердить можно только после расчёта.</p>}
            <details className="lens-tech" {...(active.notes.length > 0 ? { open: true } : {})}>
              <summary>Замечания владельцу{active.notes.length > 0 ? ` · ${active.notes.length}` : ''}</summary>
              <div className="lens-tech-body">
                <label className="lens-field">
                  <span>Текст замечания</span>
                  <textarea className="input lens-textarea" rows={3} value={note} onChange={(event) => setNote(event.target.value)} data-testid="lens-note-input" />
                  <span className="lens-field-note">Владелец увидит это у себя в заявке.</span>
                </label>
                <button
                  type="button"
                  className="btn btn-small btn-secondary"
                  onClick={() => {
                    if (note.trim() === '') return;
                    workspace.addNote(active, session.username, note.trim());
                    setNote('');
                  }}
                  data-testid="lens-note-add"
                >
                  Добавить замечание
                </button>
                {active.notes.length > 0 && (
                  <ul className="limitations small" data-testid="lens-notes-list">
                    {active.notes.map((item) => (
                      <li key={item.note_id}>
                        <strong>{item.author}</strong>: {item.text}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </details>
          </>
        ) : (
          <Empty>
            <strong>Заявка не выбрана</strong>
            <span>Выберите заявку из очереди выше.</span>
          </Empty>
        )}
      </Section>

      <ResultArea workspace={workspace} session={session} showClaim showValue={false} withMap />

      {active?.result && (
        <PassportPanel
          result={active.result}
          proof={workspace.proof}
          status={passportStatusOf(active)}
          submittedBy={active.owner_email}
          finalizedBy={active.finalized_by}
          finalizedAt={active.finalized_at}
          onIntegrityFailed={() => workspace.markIntegrityFailed(active)}
        />
      )}
    </div>
  );
}

/** Инвестор: только подтверждённые паспорта, стоимость и демонстрационный жизненный цикл. */
export function InvestorWorkspace({ workspace, session, notify }: { workspace: WorkspaceState; session: LensSession; notify: Notify }) {
  const finalized = workspace.submissions.filter((item) => item.status === 'FINALIZED' || item.status === 'INTEGRITY_FAILED');
  // Никакого запасного «откроем первую»: иначе кнопка возврата к портфелю тут же открывала
  // заявку обратно, и выйти из неё было нельзя.
  const active = workspace.activeSubmission && finalized.includes(workspace.activeSubmission) ? workspace.activeSubmission : null;

  return (
    <div className="lens-single">
      <Section title={`Портфель${finalized.length > 0 ? ` · ${finalized.length}` : ''}`} id="lens-portfolio">
        {finalized.length === 0 ? (
          <Empty>
            <strong>Подтверждённых результатов нет</strong>
            <span data-testid="lens-investor-empty">Инвестору доступны только результаты, подтверждённые верификатором.</span>
          </Empty>
        ) : (
          <ul className="lens-history-list scroll-list" data-testid="lens-portfolio-list">
            {finalized.map((submission) => (
              <SubmissionRow key={submission.submission_id} submission={submission} active={submission.submission_id === active?.submission_id} onOpen={() => workspace.setActiveSubmissionId(submission.submission_id)} />
            ))}
          </ul>
        )}
      </Section>

      {!active?.result && (
        <Section title="Карта участков" id="lens-investor-map">
          <p className="lens-tab-lead">Нажмите на участок на карте или строку в портфеле, чтобы открыть подтверждённый результат.</p>
          <MapArea
            workspace={workspace}
            openByArea={finalized}
            notify={notify}
            emptyHint="Подтверждённого результата по участку пока нет: расчёт подтверждает верификатор."
          />
        </Section>
      )}

      {active?.result ? (
        <>
          <div id="lens-investor-result">
            <div className="lens-actions">
              <button type="button" className="btn btn-small btn-secondary" onClick={workspace.clearActiveSubmission} data-testid="lens-back">
                ← Ко всему портфелю
              </button>
              <span className="muted small">
                {active.title} · {active.year_start}–{active.year_end}
              </span>
            </div>
            <ResultView
              result={active.result}
              priceKey={workspace.priceKey}
              onPriceKey={workspace.setPriceKey}
              customPrice={workspace.customPrice}
              onCustomPrice={workspace.setCustomPrice}
              selectedZoneId={workspace.selectedZoneId}
              onSelectZone={workspace.setSelectedZoneId}
              cells={workspace.cells}
              selectedCellId={workspace.selectedCellId}
              onShowCells={() => void workspace.showCells()}
              snapshots={workspace.snapshots}
              onShowSnapshots={() => void workspace.showSnapshots()}
              showClaim
              showValue
              onDownloadReport={workspace.downloadReport}
              mapSlot={<MapArea workspace={workspace} />}
            />
          </div>

          <PassportPanel
            result={active.result}
            proof={workspace.proof}
            status={passportStatusOf(active)}
            submittedBy={active.owner_email}
            finalizedBy={active.finalized_by}
            finalizedAt={active.finalized_at}
            onIntegrityFailed={() => workspace.markIntegrityFailed(active)}
          />

          <LifecyclePanel submission={active} canAct onStep={(step) => workspace.recordLifecycle(active, step, session.username)} />
        </>
      ) : (
        <Empty>
          <strong>Результат не выбран</strong>
          <span>
            {finalized.length === 0
              ? 'Пока нет ни одного подтверждённого результата.'
              : 'Выберите строку в портфеле выше или нажмите участок на карте — откроются числа, карта и паспорт.'}
          </span>
        </Empty>
      )}
    </div>
  );
}
