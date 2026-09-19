"""The passport as a JSON document and as a self-contained HTML page.

The HTML embeds every number it shows. It links to no session URL and loads no script or
stylesheet, so a copy saved today still reads correctly after the demo session is gone —
which is the whole point of handing someone a passport rather than a dashboard link.

Both formats carry exactly the values of the result. The builder formats; it never
recomputes, and it never rounds a number into a different answer.
"""
from __future__ import annotations

import html
from typing import Any

REPORT_SCHEMA_VERSION = "carbon-lens-report/2.0.0"

ZERO_REASON_TEXT = {
    "NON_POSITIVE_RELATIVE_RESULT": "относительный результат не положителен",
    "UNCERTAINTY_TOO_HIGH": "неопределённость достигла стоп-правила H/R ≥ 1",
    "ROUNDED_TO_ZERO": "округление вниз до целого дало ноль",
}
UNAVAILABLE_REASON_TEXT = {
    "MISSING_INPUT": "не хватает обязательных входных величин",
    "NON_FINITE_INPUT": "во входных данных есть неконечные значения",
    "NON_POSITIVE_AREA": "площадь запроса не положительна",
    "NON_POSITIVE_PERIOD": "период не положителен",
    "INVALID_UNCERTAINTY_INPUT": "оценки неопределённости некорректны",
    "INVALID_INTERVAL": "интервал не содержит оценку",
    "INCOMPLETE_COVERAGE": "контур покрыт данными не полностью",
    "BASELINE_OUT_OF_COVERAGE": "базовая линия не задана на этот период",
    "BASELINE_UNKNOWN_AREA": "базовая линия для этого участка отсутствует",
    "RASTER_ANALYSIS_UNAVAILABLE": "растровый расчёт недоступен для этого запроса",
}
CLAIM_TEXT = {
    "NOT_PROVIDED": "заявление не вводилось",
    "NOT_APPLICABLE": "заявлен нулевой объём, подтверждать нечего",
    "NOT_COMPARABLE": "заявление несопоставимо с расчётом",
    "UNASSESSABLE": "расчёт единиц недоступен, сравнивать не с чем",
    "SUPPORTED_BY_CASE": "расчёт по условиям кейса покрывает заявление",
    "PARTIALLY_SUPPORTED_BY_CASE": "расчёт по условиям кейса покрывает заявление частично",
    "NOT_SUPPORTED_BY_CASE": "расчёт по условиям кейса даёт ноль единиц",
}


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _number(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, int):
        return str(value)
    return f"{value:,.{digits}f}".replace(",", " ")


def _rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(f"<tr><th>{_e(name)}</th><td>{value}</td></tr>" for name, value in pairs)


def units_sentence(units: dict) -> str:
    """One sentence that cannot confuse "no answer" with "the answer is zero"."""
    if units["status"] == "UNAVAILABLE":
        reason = UNAVAILABLE_REASON_TEXT.get(units["unavailable_reason"],
                                             units["unavailable_reason"] or "причина не указана")
        return f"Потенциальные единицы не рассчитаны: {reason}."
    if units["q"] == 0:
        reason = ZERO_REASON_TEXT.get(units["zero_reason"], units["zero_reason"] or "")
        return f"Расчёт выполнен и даёт 0 потенциальных единиц: {reason}."
    return f"Расчёт по условиям кейса даёт {units['q']} потенциальных единиц."


class ReportBuilder:
    """Default report builder. Trust may replace it behind the same port."""

    name = "backend-report/2.0.0"

    def build(self, result: dict) -> tuple[dict, str]:
        document = {
            "schema_version": REPORT_SCHEMA_VERSION,
            # Taken from the run, not from the clock: downloading twice must not
            # produce two documents that differ only in when they were fetched.
            "generated_at": result["run"]["created_at"],
            "report_hash": result["passport"]["report_hash"],
            "result": result,
        }
        return document, self.render(result)

    def render(self, result: dict) -> str:
        units, change, areas = result["units"], result["change"], result["areas"]
        coverage, claim, passport = result["coverage"], result["claim"], result["passport"]
        request, identity = result["request"], result["identity"]

        fixture = result.get("fixture")
        banner = ""
        if fixture:
            banner = (f'<p class="banner"><strong>{_e(fixture["kind"])}: '
                      f'{_e(fixture["label"])}</strong><br>{_e(fixture["note"])}</p>')

        summary = _rows([
            ("Период", f"{_e(request['year_start'])}–{_e(request['year_end'])}"),
            ("Площадь запроса, га", _number(areas["requested_ha"], 4)),
            ("Расчётная площадь, га", _number(areas["calculated_ha"], 4)),
            ("Площадь без данных, га", _number(areas["missing_ha"], 4)),
            ("Расхождение площадей, га", _number(areas["area_difference_ha"], 6)),
            ("Статус расчёта", _e(result["calculation_status"])),
            ("Статус свидетельств", _e(result["evidence_status"])),
        ])
        carbon = _rows([
            ("Средний запас на начало, т C/га", _number(change["mean_carbon_start_tc_ha"])),
            ("Средний запас на конец, т C/га", _number(change["mean_carbon_end_tc_ha"])),
            ("Суммарный запас на начало, т C", _number(change["total_carbon_start_tc"])),
            ("Суммарный запас на конец, т C", _number(change["total_carbon_end_tc"])),
            ("Изменение запаса ΔC, т C", _number(change["delta_carbon_tc"])),
            ("E проекта, т CO₂-экв.", _number(units["eproj_tco2e"])),
            ("e, т CO₂-экв./га/год", _number(change["eproj_tco2e_ha_year"], 4)),
            ("Пул", _e(change["pool"])),
            ("Знак", _e(change["sign_convention"])),
        ])
        ledger = _rows([
            ("E базовой линии, т CO₂-экв.", _number(units["ebase_tco2e"])),
            ("Утечка LK, т CO₂-экв.", _number(units["lk_tco2e"])),
            ("Нижняя граница L", _number(units["lower_tco2e"])),
            ("Верхняя граница U", _number(units["upper_tco2e"])),
            ("H", _number(units["h_tco2e"])),
            ("R", _number(units["r_tco2e"])),
            ("H/R", _number(units["ratio"], 6)),
            ("UNC", _number(units["unc"], 6)),
            ("R с поправкой", _number(units["radj_tco2e"])),
            ("Буфер B", _number(units["buffer_tco2e"])),
            ("Q", "—" if units["q"] is None else str(units["q"])),
            ("Остаток округления", _number(units["rounding_residual_tco2e"], 6)),
        ])
        coverage_rows = _rows([
            ("Биомасса", _number(coverage["biomass_fraction"], 4)),
            ("Неопределённость биомассы", _number(coverage["uncertainty_fraction"], 4)),
            ("Базовая линия", _number(coverage["baseline_fraction"], 4)),
            ("Парные валидные оптические пиксели",
             _number(coverage["optical_paired_valid_fraction"], 4)),
        ])
        money = result["scenario_values"]
        money_rows = _rows([
            (f"Цена {name}, руб./ед.", _number((money[name] or {}).get("price_rub"), 0)
             + " → " + _number((money[name] or {}).get("value_rub"), 0) + " руб.")
            for name in ("low", "base", "high") if money[name] is not None
        ]) or '<tr><td colspan="2">Сценарная стоимость не рассчитывается: Q отсутствует.</td></tr>'

        claim_rows = _rows([
            ("Статус", _e(CLAIM_TEXT.get(claim["status"], claim["status"]))),
            ("Заявлено единиц", _number(claim["claimed_units"], 0)),
            ("Сопоставимо", "да" if claim["comparable"] else "нет"),
            ("Неподтверждённый разрыв, единиц", _number(claim["unsupported_gap"], 0)),
            ("Доля подтверждённого", _number(claim["supported_share"], 4)),
            ("Причины несопоставимости", _e(", ".join(claim["mismatch_reasons"]) or "—")),
        ]) if claim["status"] != "NOT_PROVIDED" else ""

        zones = "".join(
            f"<tr><td>{_e(zone['zone_id'])}</td><td>{_e(zone['fact'])}</td>"
            f"<td>{_e(zone['cause'])}</td><td>{_number(zone['area_ha'], 2)}</td>"
            f"<td>{_number(zone['contribution_e_tco2e'])}</td></tr>"
            for zone in result["zones"])
        sources = "".join(
            f"<li>{_e(item['product'])} ({_e(item['version'])}) — {_e(item['attribution'])}</li>"
            for item in result["sources"])
        limitations = "".join(f"<li>{_e(item['message'])}</li>"
                              for item in result["limitations"])
        warnings = "".join(
            f"<li>{_e(item['severity'])}: {_e(item['message'])}</li>"
            for item in result["evidence"]["warnings"])
        notes = "".join(f"<li>{_e(item)}</li>" for item in result["notes"])

        return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Паспорт расчёта {_e(identity['analysis_id'])}</title>
<style>
 body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 52rem;
        padding: 16px; color: #16281f; background: #fbfdfb; }}
 h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
 table {{ border-collapse: collapse; width: 100%; margin: .5rem 0; }}
 th, td {{ border: 1px solid #cfe0d4; padding: 6px 8px; text-align: left;
           vertical-align: top; }}
 th {{ background: #eef5ef; font-weight: 600; width: 55%; }}
 .banner {{ background: #fff6df; border: 1px solid #e4c874; padding: 10px 12px;
            border-radius: 6px; }}
 .headline {{ font-size: 1.15rem; font-weight: 600; background: #eef5ef;
              border-left: 4px solid #2f6b46; padding: 10px 12px; }}
 code {{ word-break: break-all; font-size: .85em; }}
 footer {{ margin-top: 2rem; font-size: .85em; color: #4a5a50; }}
</style></head><body>
<h1>Паспорт расчёта Carbon Lens</h1>
{banner}
<p class="headline">{_e(units_sentence(units))}</p>
<h2>Запрос</h2><table>{summary}</table>
<h2>Запас и изменение</h2><table>{carbon}</table>
<h2>От изменения к единицам</h2><table>{ledger}</table>
<h2>Покрытие</h2>
<p>Четыре покрытия отвечают на разные вопросы и не смешиваются.</p>
<table>{coverage_rows}</table>
<h2>Сценарная стоимость</h2>
<p>Сценарные цены кейса, а не рыночная котировка и не обещанная выручка.</p>
<table>{money_rows}</table>
{('<h2>Заявление</h2><table>' + claim_rows + '</table>') if claim_rows else ''}
{('<h2>Зоны изменения</h2><table><tr><th>Зона</th><th>Факт</th><th>Причина</th>'
  '<th>Площадь, га</th><th>Вклад, т CO₂-экв.</th></tr>' + zones + '</table>') if zones else ''}
<h2>Источники</h2><ul>{sources}</ul>
{('<h2>Замечания к свидетельствам</h2><ul>' + warnings + '</ul>') if warnings else ''}
<h2>Ограничения</h2><ul>{limitations}</ul>
{('<h2>Примечания метода</h2><ul>' + notes + '</ul>') if notes else ''}
<h2>Идентичность</h2><table>{_rows([
    ("Идентификатор расчёта", f"<code>{_e(identity['analysis_id'])}</code>"),
    ("Хеш содержания", f"<code>{_e(passport['content_hash'])}</code>"),
    ("Хеш отчёта", f"<code>{_e(passport['report_hash'])}</code>"),
    ("Предыдущий хеш", f"<code>{_e(passport['previous_hash'] or '—')}</code>"),
    ("Хеш контура", f"<code>{_e(identity['geometry_hash'])}</code>"),
    ("Хеш входа", f"<code>{_e(identity['input_hash'])}</code>"),
    ("Версия схемы", _e(identity['schema_version'])),
    ("Версия метода", _e(identity['method_version'])),
    ("Версия набора данных", _e(identity['dataset_version'])),
    ("Хеш набора данных", f"<code>{_e(identity['dataset_hash'])}</code>"),
    ("Хеш манифеста источников", f"<code>{_e(identity['source_manifest_hash'])}</code>"),
    ("Происхождение данных", _e(result['run']['dataset_origin'])),
    ("Растровый адаптер", _e(result['run']['raster_adapter'])),
    ("Углеродный адаптер", _e(result['run']['carbon_adapter'])),
    ("Область сравнения", _e(passport['comparison_scope'])),
    ("Результат сравнения", _e(passport['comparison_result'])),
    ("Создан", _e(passport['created_at'])),
])}</table>
<footer>
<p>Хеш выявляет изменение файла относительно доверенной фиксации. Он не предотвращает
двойную продажу и не удостоверяет истинность расчёта.</p>
<p>Документ автономен: он содержит показанные значения и не зависит от ссылок сессии.</p>
</footer>
</body></html>
"""
