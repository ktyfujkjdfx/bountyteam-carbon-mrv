import { useState } from 'react';
import { Empty, Section, Skeleton } from '../../components/common';
import type { LensSession } from '../auth';
import { PASSPORT_STATUS_TEXT, passportStatusOf, type Submission } from '../workspace';
import type { WorkspaceState } from '../useWorkspace';
import { LensMapView } from './LensMapView';
import { LifecyclePanel } from './LifecyclePanel';
import { PassportPanel } from './PassportPanel';
import { RequestForm } from './RequestForm';
import { ResultView } from './ResultView';
import { FIXTURE_SCENARIO_ORDER, FIXTURE_LABELS, SCENARIO_DEFAULTS } from '../fixtures';

function SubmissionRow({ submission, active, onOpen }: { submission: Submission; active: boolean; onOpen: () => void }) {
  const status = PASSPORT_STATUS_TEXT[passportStatusOf(submission)];
  const q = submission.result?.units.q ?? null;
  return (
    <li>
      <button type="button" className={`lens-history-item${active ? ' selected' : ''}`} onClick={onOpen} aria-pressed={active} data-testid={`lens-submission-${submission.submission_id}`}>
        <span className="lens-history-head">
          <span>{submission.title}</span>
          <span className="mono small">
            {submission.year_start}–{submission.year_end}
          </span>
        </span>
        <span className="lens-history-meta">
          <span className={`badge tone-${status.tone}`}>{status.label}</span>
          <span className="mono small">Q: {q === null ? 'не рассчитано' : q.toLocaleString('ru-RU')}</span>
          {submission.claimed_units !== null && <span className="mono small">заявлено {submission.claimed_units.toLocaleString('ru-RU')}</span>}
        </span>
      </button>
    </li>
  );
}

function ResultArea({ workspace, session, showClaim, showValue }: { workspace: WorkspaceState; session: LensSession; showClaim: boolean; showValue: boolean }) {
  const { analysis, shownResult } = workspace;
  void session;
  return (
    <>
      {analysis.state.phase === 'submitting' && <Skeleton label="Запрос отправляется…" height={140} />}
      {analysis.state.phase === 'polling' && <Skeleton label={`Расчёт: ${String(analysis.state.analysis?.job_state ?? 'QUEUED')}…`} height={140} />}
      {analysis.state.phase === 'timeout' && (
        <div className="state state-warn" role="status" data-testid="lens-timeout">
          <strong>Расчёт ещё выполняется</strong>
          <span>Опрос приостановлен, задание не отменено. Откройте заявку позже или запустите расчёт снова.</span>
        </div>
      )}
      {analysis.state.phase === 'error' && analysis.state.error && (
        <div className="state state-error" role="alert" data-testid="lens-error">
          <strong>Расчёт недоступен · {analysis.state.error.code}</strong>
          <span>{analysis.state.error.message}</span>
          {analysis.state.error.detail && <span className="muted small">{analysis.state.error.detail}</span>}
          <span className="muted small">Помеченный набор не подставляется автоматически вместо ответа сервиса.</span>
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
          showClaim={showClaim}
          showValue={showValue}
          onDownloadReport={workspace.downloadReport}
        />
      ) : (
        analysis.state.phase === 'idle' && (
          <Empty>
            <strong>Результата пока нет</strong>
            <span>Выберите заявку из списка или выполните расчёт.</span>
          </Empty>
        )
      )}
    </>
  );
}

function MapArea({ workspace }: { workspace: WorkspaceState }) {
  return (
    <LensMapView
      geometry={workspace.shownResult?.request.geometry ?? workspace.draft.geometry}
      result={workspace.shownResult}
      cells={workspace.cells}
      gaps={workspace.gaps}
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

/** Owner: my requests, a new request, the state of processing and the finalised passport. */
export function OwnerWorkspace({ workspace, session }: { workspace: WorkspaceState; session: LensSession }) {
  const mine = workspace.submissions.filter((item) => item.owner_email === session.username);
  const active = workspace.activeSubmission;

  return (
    <div className="lens-layout">
      <aside className="rail rail-left">
        <Section title="Новая заявка" id="lens-new-request">
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
            onSubmit={() => workspace.submitRequest(workspace.draft.aoiId ?? 'Контур пользователя')}
            submitLabel="Подать заявку"
            busy={workspace.analysis.busy}
            allowClaim
            error={workspace.requestError}
          />
        </Section>
        <Section title="Мои заявки" id="lens-my-requests">
          {mine.length === 0 ? (
            <Empty>
              <strong>Заявок пока нет</strong>
              <span>Подайте первую заявку: выберите участок и период.</span>
            </Empty>
          ) : (
            <ul className="lens-history-list" data-testid="lens-my-requests">
              {mine.map((submission) => (
                <SubmissionRow key={submission.submission_id} submission={submission} active={submission.submission_id === active?.submission_id} onOpen={() => workspace.setActiveSubmissionId(submission.submission_id)} />
              ))}
            </ul>
          )}
        </Section>
      </aside>

      <div className="center">
        <MapArea workspace={workspace} />
        {active && active.notes.length > 0 && (
          <Section title="Замечания верификатора" id="lens-notes">
            <ul className="limitations small" data-testid="lens-verifier-notes">
              {active.notes.map((note) => (
                <li key={note.note_id}>
                  <strong>{note.author}</strong> · {new Date(note.created_at).toLocaleString('ru-RU')}
                  <div>{note.text}</div>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>

      <div className="rail rail-right">
        <Section title="Статус обработки" id="lens-status">
          {active ? (
            <>
              <p data-testid="lens-owner-status">
                {active.status === 'SUBMITTED' && 'Заявка подана и ждёт верификатора: расчёт запускает он.'}
                {active.status === 'CALCULATED' && 'Расчёт выполнен. Паспорт станет финальным после подтверждения верификатора.'}
                {active.status === 'FINALIZED' && 'Верификатор финализировал паспорт.'}
                {active.status === 'INTEGRITY_FAILED' && 'Целостность паспорта не подтверждена: содержимое изменилось после фиксации.'}
              </p>
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
            </>
          ) : (
            <Empty>
              <strong>Заявка не выбрана</strong>
              <span>Откройте заявку из списка слева.</span>
            </Empty>
          )}
        </Section>
      </div>
    </div>
  );
}

/** Verifier: the queue, the analysis, the notes and finalisation. */
export function VerifierWorkspace({ workspace, session, offline }: { workspace: WorkspaceState; session: LensSession; offline: boolean }) {
  const [note, setNote] = useState('');
  const [scenario, setScenario] = useState(FIXTURE_SCENARIO_ORDER[0]);
  const active = workspace.activeSubmission;

  return (
    <div className="lens-layout">
      <aside className="rail rail-left">
        <Section title="Очередь заявок" id="lens-queue">
          {workspace.submissions.length === 0 ? (
            <Empty>
              <strong>Очередь пуста</strong>
              <span>Заявки появятся, когда владелец их подаст. Для показа войдите владельцем и подайте заявку.</span>
            </Empty>
          ) : (
            <ul className="lens-history-list" data-testid="lens-queue-list">
              {workspace.submissions.map((submission) => (
                <SubmissionRow key={submission.submission_id} submission={submission} active={submission.submission_id === active?.submission_id} onOpen={() => workspace.setActiveSubmissionId(submission.submission_id)} />
              ))}
            </ul>
          )}
        </Section>

        {offline && (
          <Section title="Набор значений" id="lens-scenario">
            <label className="lens-field">
              <span>Помеченный набор офлайн-режима</span>
              <select className="select" value={scenario} onChange={(event) => setScenario(event.target.value as typeof scenario)} data-testid="lens-scenario-select">
                {FIXTURE_SCENARIO_ORDER.map((id) => (
                  <option key={id} value={id}>
                    {SCENARIO_DEFAULTS[id].acceptance ? `${SCENARIO_DEFAULTS[id].acceptance} · ` : ''}
                    {FIXTURE_LABELS[id].label}
                  </option>
                ))}
              </select>
            </label>
            <p className="muted small">Офлайн-режим отвечает помеченным набором. Это не расчёт по выбранному участку.</p>
          </Section>
        )}
      </aside>

      <div className="center">
        <MapArea workspace={workspace} />
        <Section title="Решение верификатора" id="lens-decision">
          {active ? (
            <>
              <div className="lens-actions">
                <button
                  type="button"
                  className="btn"
                  onClick={() => void workspace.runAnalysis(active, offline ? scenario : undefined)}
                  disabled={workspace.analysis.busy}
                  data-testid="lens-run-analysis"
                >
                  {workspace.analysis.busy ? 'Расчёт выполняется…' : active.result ? 'Пересчитать' : 'Проверить проект'}
                </button>
                <button
                  type="button"
                  className="btn btn-small btn-secondary"
                  onClick={() => workspace.finalize(active, session.username)}
                  disabled={!active.result || active.status === 'FINALIZED'}
                  data-testid="lens-finalize"
                >
                  Финализировать паспорт
                </button>
              </div>
              {!active.result && <p className="muted small">Паспорт нельзя финализировать до расчёта.</p>}
              <label className="lens-field">
                <span>Замечание владельцу</span>
                <textarea className="input lens-textarea" rows={3} value={note} onChange={(event) => setNote(event.target.value)} data-testid="lens-note-input" />
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
            </>
          ) : (
            <Empty>
              <strong>Заявка не выбрана</strong>
              <span>Выберите заявку из очереди.</span>
            </Empty>
          )}
        </Section>
      </div>

      <div className="rail rail-right">
        <Section title="Результат проверки" id="lens-verifier-result">
          <ResultArea workspace={workspace} session={session} showClaim showValue={false} />
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
        </Section>
      </div>
    </div>
  );
}

/** Investor: finalised passports only, with the value scenarios and the demo lifecycle. */
export function InvestorWorkspace({ workspace, session }: { workspace: WorkspaceState; session: LensSession }) {
  const finalized = workspace.submissions.filter((item) => item.status === 'FINALIZED' || item.status === 'INTEGRITY_FAILED');
  const active = workspace.activeSubmission && finalized.includes(workspace.activeSubmission) ? workspace.activeSubmission : finalized[0] ?? null;

  return (
    <div className="lens-layout">
      <aside className="rail rail-left">
        <Section title="Финализированные паспорта" id="lens-portfolio">
          {finalized.length === 0 ? (
            <Empty>
              <strong>Финализированных паспортов нет</strong>
              <span data-testid="lens-investor-empty">Инвестору доступны только паспорта, подтверждённые верификатором.</span>
            </Empty>
          ) : (
            <ul className="lens-history-list" data-testid="lens-portfolio-list">
              {finalized.map((submission) => (
                <SubmissionRow key={submission.submission_id} submission={submission} active={submission.submission_id === active?.submission_id} onOpen={() => workspace.setActiveSubmissionId(submission.submission_id)} />
              ))}
            </ul>
          )}
        </Section>
      </aside>

      <div className="center">
        <MapArea workspace={workspace} />
        {active && <LifecyclePanel submission={active} canAct onStep={(step) => workspace.recordLifecycle(active, step, session.username)} />}
      </div>

      <div className="rail rail-right">
        <Section title="Подтверждённый результат" id="lens-investor-result">
          {active?.result ? (
            <>
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
                showClaim
                showValue
                onDownloadReport={workspace.downloadReport}
              />
              <PassportPanel
                result={active.result}
                proof={workspace.proof}
                status={passportStatusOf(active)}
                submittedBy={active.owner_email}
                finalizedBy={active.finalized_by}
                finalizedAt={active.finalized_at}
                onIntegrityFailed={() => workspace.markIntegrityFailed(active)}
              />
            </>
          ) : (
            <Empty>
              <strong>Паспорт не выбран</strong>
              <span>Выберите финализированный паспорт слева.</span>
            </Empty>
          )}
        </Section>
      </div>
    </div>
  );
}
