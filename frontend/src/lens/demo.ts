// Guided walkthrough of the Carbon Lens workspace. Every step only selects controls a user could select
// by hand: territory, period, claim and the labelled result set. No numbers live here — the screen shows
// whatever the adapter returns for that request.

import type { FixtureScenarioId } from './fixtures';

export type DemoTab = 'calculation' | 'coverage' | 'observations' | 'zones' | 'comparison' | 'passport';

export interface DemoStep {
  id: string;
  title: string;
  narration: string;
  /** Acceptance scenario of docs/roadmaps/ROADMAP_FRONTEND.md this step demonstrates. */
  acceptance: string | null;
  setup: {
    aoiId?: string;
    sampleRequestId?: string;
    years?: [number, number];
    scenario?: FixtureScenarioId;
    claimedUnits?: string;
    tab?: DemoTab;
    run?: boolean;
  };
}

export const DEMO_STEPS: DemoStep[] = [
  {
    id: 'control',
    title: 'Контрольный участок: ноль — это результат',
    narration:
      'Тверской контрольный участок за 2019–2024. Отсутствие зарегистрированных потерь покрова не гарантирует ни постоянную биомассу, ни положительные единицы: расчёт показывает 0 и называет причину.',
    acceptance: 'S1',
    setup: { aoiId: 'RU_TVER_01', years: [2019, 2024], scenario: 'ZERO_NON_POSITIVE', claimedUnits: '', tab: 'calculation', run: true },
  },
  {
    id: 'fire',
    title: 'Пожар августа 2021: зона, вклад и граница доказательства',
    narration:
      'Мордовия, 2020–2022. Зона потери связана с официальной записью продукта гарей MODIS: видны даты, погрешность и ограничения. Площадь гари продуктом не измеряется, доля «половина леса» не выводится.',
    acceptance: 'S2',
    setup: { aoiId: 'RU_MORDOVIA_03', years: [2020, 2022], scenario: 'FIRE_SUPPORTED_LOSS', tab: 'zones', run: true },
  },
  {
    id: 'cause-unknown',
    title: 'Потери без установленной причины',
    narration:
      'Вологодская мозаика потерь, 2019–2024. Изменение наблюдается, но записи о событии для участка нет: статус причины остаётся «не установлена», и это честный итог.',
    acceptance: 'S3',
    setup: { aoiId: 'RU_VOLOGDA_02', years: [2019, 2024], scenario: 'CAUSE_UNKNOWN_LOSS', tab: 'observations', run: true },
  },
  {
    id: 'recovery',
    title: 'История потери и последующая динамика',
    narration:
      'Мордовия, участок ранней потери, 2019–2024. Видно снижение и последующий прирост, но период в целом остаётся ниже базовой линии: восстановление объявляется только по результату, а не по ожиданию.',
    acceptance: 'S4',
    setup: { aoiId: 'RU_MORDOVIA_04', years: [2019, 2024], scenario: 'RECOVERY_AFTER_LOSS', tab: 'calculation', run: true },
  },
  {
    id: 'optics',
    title: 'Облака не равны отсутствию данных о биомассе',
    narration:
      'Сентябрьские сцены 2021 года с высокой облачностью ограничивают объяснение изменения. Числовое покрытие CCI при этом полное: оси качества разделены.',
    acceptance: 'S6',
    setup: { aoiId: 'RU_MORDOVIA_03', years: [2021, 2022], scenario: 'WEAK_OPTICS_VALID_CCI', tab: 'coverage', run: true },
  },
  {
    id: 'unavailable',
    title: 'Недоступно — это не ноль',
    narration:
      'Когда часть контура выходит за числовое покрытие, единицы не рассчитываются: показано «Недоступно» с причиной и площадью пропуска, а не 0.',
    acceptance: 'S7',
    setup: { scenario: 'UNAVAILABLE_COVERAGE', tab: 'coverage', run: true },
  },
  {
    id: 'subplot',
    title: 'Подучасток: базовая линия родителя на реальную площадь',
    narration:
      'Официальный подучасток CHECK_TRANSFER_01 (~808,85 га) за 2020–2024. Удельная базовая линия родительского участка применяется к площади запроса; разбор показывает путь от R к Q.',
    acceptance: 'S5',
    setup: { sampleRequestId: 'CHECK_TRANSFER_01', years: [2020, 2024], scenario: 'SUBPLOT_BASELINE', tab: 'calculation', run: true },
  },
  {
    id: 'claim',
    title: 'Заявление инвестора и разрыв',
    narration:
      'Введено заявление 3000 единиц для того же запроса. Расчёт не меняется под заявление: показан разрыв и его сценарная стоимость при выбранной цене кейса.',
    acceptance: 'S8',
    setup: { sampleRequestId: 'CHECK_TRANSFER_01', years: [2020, 2024], scenario: 'SUBPLOT_BASELINE', claimedUnits: '3000', tab: 'calculation', run: true },
  },
  {
    id: 'doc-example',
    title: 'Проверка формул на условном примере',
    narration:
      'Условный пример постановки задачи: 100 га, один год, Q = 395. Каждый шаг разбора раскрывает формулу и подставленные значения — методика проверяема.',
    acceptance: null,
    setup: { scenario: 'DOC_EXAMPLE_Q395', years: [2019, 2020], claimedUnits: '', tab: 'calculation', run: true },
  },
  {
    id: 'passport',
    title: 'Паспорт и проверка изменённой копии',
    narration:
      'Паспорт скачивается в JSON и HTML. Проверка загруженного файла пересчитывает хеш блока content: изменённая копия отчёта обнаруживается. Один хеш не защищает от повторной продажи.',
    acceptance: 'S9',
    setup: { tab: 'passport' },
  },
];
