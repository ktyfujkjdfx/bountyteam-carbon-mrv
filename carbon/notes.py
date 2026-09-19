"""Methodological notes attached to engine results.

Codes are stable identifiers for consumers; the Russian text is what a report shows.
Every wording keeps the scenario status of the case rules visible: the engine reports
what the case rules give, and never states that a violation or a market outcome is
established.
"""
from __future__ import annotations

from dataclasses import dataclass

SCENARIO_INTERVAL = "SCENARIO_INTERVAL"
POOL_LIMITED = "POOL_LIMITED"
CASE_UNITS = "CASE_UNITS"
SCENARIO_PRICES = "SCENARIO_PRICES"
BASELINE_FIXED = "BASELINE_FIXED"
BASELINE_DECLINING = "BASELINE_DECLINING"
RESULT_FROM_DECLINING_BASELINE = "RESULT_FROM_DECLINING_BASELINE"
STOP_RULE_APPLIED = "STOP_RULE_APPLIED"
NON_POSITIVE_RESULT = "NON_POSITIVE_RESULT"
ROUNDED_BELOW_ONE_UNIT = "ROUNDED_BELOW_ONE_UNIT"
COVERAGE_INCOMPLETE = "COVERAGE_INCOMPLETE"
CLAIM_INPUT_LABEL = "CLAIM_INPUT_LABEL"
CLAIM_GAP_SCENARIO = "CLAIM_GAP_SCENARIO"
CLAIM_ZERO = "CLAIM_ZERO"
OPTICAL_QUALITY_SEPARATE = "OPTICAL_QUALITY_SEPARATE"
AREA_NOT_FULLY_COVERED = "AREA_NOT_FULLY_COVERED"
RESEARCH_VARIANT = "RESEARCH_VARIANT"
PASSPORT_NEW_OBSERVATION = "PASSPORT_NEW_OBSERVATION"
PROVISIONAL_INPUT = "PROVISIONAL_INPUT"
UNCERTAINTY_COVERAGE_NOT_REPORTED = "UNCERTAINTY_COVERAGE_NOT_REPORTED"
CELLS_EXCLUDED = "CELLS_EXCLUDED"
CANONICAL_E_DISAGREES = "CANONICAL_E_DISAGREES"
BASELINE_PROJECTION = "BASELINE_PROJECTION"
PROJECTION_CLIPPED = "PROJECTION_CLIPPED"

CATALOGUE: dict[str, str] = {
    SCENARIO_INTERVAL: (
        "Интервал сценарный: он получен из явно заданных допущений о пространственной "
        "и временной зависимости ошибок входных данных. Вероятностное покрытие не заявляется, "
        "эмпирическая калибровка по независимым наземным измерениям не выполнялась."
    ),
    POOL_LIMITED: (
        "Учитывается только живая надземная древесная биомасса. Корни, мёртвая древесина, "
        "подстилка, почва и продукция в расчёт не входят; их запасы не равны нулю."
    ),
    CASE_UNITS: (
        "Потенциальные единицы рассчитаны по условиям кейса. Это не единицы официального "
        "реестра и не подтверждение права на выпуск."
    ),
    SCENARIO_PRICES: (
        "Стоимость показана в сценарных ценах кейса (500, 1500 и 4000 руб./ед.). "
        "Это не прогноз рынка и не ожидаемая выручка."
    ),
    BASELINE_FIXED: (
        "Базовая линия и вычет за утечку зафиксированы условиями кейса и не входят "
        "в интервал результата. Их сценарная неопределённость показывается отдельно."
    ),
    BASELINE_DECLINING: (
        "Базовая линия участка {aoi_id} за период снижается на {decline:.6f} т C/га: "
        "сценарий без проекта сам предполагает потерю запаса, поэтому его легче превзойти."
    ),
    RESULT_FROM_DECLINING_BASELINE: (
        "Положительный результат относительно базовой линии получен при потере запаса "
        "на участке: он отражает сравнение со снижающимся сценарием, а не наблюдаемое "
        "накопление углерода."
    ),
    STOP_RULE_APPLIED: (
        "Отношение H/R достигло порога {stop_ratio}, поэтому по правилу кейса Q = 0. "
        "Обычный waterfall для этого случая не строится: при чуть меньшем H/R то же правило "
        "дало бы положительное число единиц."
    ),
    NON_POSITIVE_RESULT: (
        "Результат относительно базовой линии не положителен, поэтому Q = 0, "
        "а отношение H/R не вычисляется."
    ),
    ROUNDED_BELOW_ONE_UNIT: (
        "После вычета за неопределённость и резерва результат меньше одной единицы, "
        "поэтому Q = 0."
    ),
    COVERAGE_INCOMPLETE: (
        "Обязательные входные данные покрывают не всю площадь запроса, поэтому число "
        "потенциальных единиц не рассчитывается."
    ),
    CLAIM_INPUT_LABEL: (
        "Заявленный объём — пользовательский или демонстрационный ввод. Он не влияет "
        "на расчёт запаса, интервала, базовой линии и Q."
    ),
    CLAIM_GAP_SCENARIO: (
        "Разрыв заявления пересчитан в сценарные цены кейса. Это сравнение расчёта "
        "с заявлением, а не установленный финансовый результат и не оценка риска."
    ),
    CLAIM_ZERO: (
        "Заявлен нулевой объём: сравнивать нечего, поэтому доля поддержки не определена. "
        "Нулевое заявление не считается подтверждённым."
    ),
    OPTICAL_QUALITY_SEPARATE: (
        "Оптическое качество снимков показано отдельно и относится к наглядности "
        "свидетельств. Оно не уменьшает число потенциальных единиц: облачность снимка "
        "не меняет модельную оценку запаса биомассы."
    ),
    AREA_NOT_FULLY_COVERED: (
        "Расчётная площадь меньше запрошенной. Непокрытая часть показана отдельно "
        "и не заменяется нулевым запасом."
    ),
    RESEARCH_VARIANT: (
        "Исследовательский вариант расчёта. Он показывает чувствительность результата "
        "к допущениям и не заменяет основной расчёт по официальной базовой линии."
    ),
    PASSPORT_NEW_OBSERVATION: (
        "Период или контур отличаются от предыдущей версии паспорта, поэтому это новое "
        "наблюдение, а не пересчёт прежнего. Прежняя версия остаётся без изменений."
    ),
    UNCERTAINTY_COVERAGE_NOT_REPORTED: (
        "Покрытие обязательного входа AGB_SD не сообщено вызывающей стороной, поэтому "
        "полнота данных о неопределённости не проверена. Отсутствующее стандартное "
        "отклонение не считается нулевым: нулевое SD сузило бы интервал и завысило Q."
    ),
    CELLS_EXCLUDED: (
        "Из расчёта исключено ячеек: {excluded}. Их площадь остаётся непокрытой и "
        "не заменяется нулевым запасом."
    ),
    CANONICAL_E_DISAGREES: (
        "Изменение запаса, пересчитанное по пер-клеточному слою, расходится со значением, "
        "опубликованным поставщиком данных, больше объявленного допуска. Расхождение "
        "требует согласования сторон и не усредняется."
    ),
    BASELINE_PROJECTION: (
        "Продолжение официальной базовой линии до сценарного горизонта — методическое "
        "допущение кейса, а не прогноз будущей биомассы и не прогноз рынка. Оно "
        "рассчитано по той же формуле и не влияет на Q за запрошенный период."
    ),
    PROJECTION_CLIPPED: (
        "На части горизонта траектория базовой линии опускается ниже нуля и обрезается "
        "по правилу max(0, …). Обрезанный участок не является оценкой запаса."
    ),
    PROVISIONAL_INPUT: (
        "Пер-клеточные входные данные получены предварительным локальным извлечением "
        "из официальных файлов data/, а не компонентом RS. После фиксации контракта RS "
        "результат подлежит пересчёту на его выходе."
    ),
}


@dataclass(frozen=True)
class Note:
    code: str
    text: str


def note(code: str, **values: object) -> Note:
    template = CATALOGUE[code]
    return Note(code=code, text=template.format(**values) if values else template)
