"""Report builder: the same numbers as the API, in JSON and in a standalone HTML page.

The builder reads a finished `Analysis` and the passport that was already sealed from it.
It performs no arithmetic of its own — no second floor, no re-derived share, no rounding
"for display" that would make the page disagree with the API. Everything it shows is read
from the typed result, so a reader who compares the page with the API finds the same
values and the same statuses.

The HTML is self-contained and inert: no script, no external request, no local filesystem
path, no secret. Every value that came from a user — the request identifier, a claim
label — is escaped, so a crafted request cannot inject markup into a page someone opens
later.

The page shows one run timestamp, which means two renders of the same analysis are not
byte-identical. That is honest and it is why the passport content hash, not the page, is
the stable identity; the manifest records the bytes of the page that was actually
published.
"""
from __future__ import annotations

import html
import json
from typing import Any

from . import reasons
from .analysis import Analysis
from .passport import Passport

REPORT_FORMAT = "carbon.report/1"

_STATUS_TEXT = {
    reasons.AVAILABLE: "рассчитано",
    reasons.UNAVAILABLE: "не рассчитано",
}

_CLAIM_TEXT = {
    reasons.CLAIM_NOT_PROVIDED: "заявление не предоставлено",
    reasons.CLAIM_NOT_APPLICABLE: "заявлен нулевой объём, сравнивать нечего",
    reasons.CLAIM_NOT_COMPARABLE: "заявление несопоставимо с расчётом",
    reasons.CLAIM_UNASSESSABLE: "оценить невозможно: число единиц не определено",
    reasons.CLAIM_SUPPORTED: "заявленный объём не превышает расчёт по условиям кейса",
    reasons.CLAIM_PARTIALLY_SUPPORTED: "расчёт по условиям кейса покрывает заявление частично",
    reasons.CLAIM_NOT_SUPPORTED: "расчёт по условиям кейса не даёт ни одной единицы",
}


def build_report(
    analysis: Analysis,
    *,
    passport: Passport,
    manifest_hash: str | None = None,
    created_at: str,
    run_id: str,
) -> dict[str, Any]:
    """The JSON report. Structure is presentation; every number comes from the passport."""
    content = passport.content
    return {
        "format": REPORT_FORMAT,
        "hashes": {
            "scientific_passport_content_hash": passport.content_hash,
            "source_manifest_hash": passport.source_manifest_hash,
            "integrity_manifest_hash": manifest_hash,
            "note": (
                "api_result_content_hash и report_file_hash принадлежат слою выдачи: "
                "первый считает Backend, второй считается по байтам скачанного файла."
            ),
        },
        "passport_content_hash": passport.content_hash,
        "manifest_hash": manifest_hash,
        "method_version": analysis.method_version,
        "run": {"created_at": created_at, "run_id": run_id},
        "request": content["request"],
        "input_status": content["input_status"],
        "area": content["area"],
        "coverage": content["coverage"],
        "optical_quality": content["optical_quality"],
        "timeline": content["timeline"],
        "interval": content["interval"],
        "baseline": content["baseline"],
        "units": content["units"],
        "claim": content["claim"],
        "method_options": content["method_options"],
        "provenance": content["provenance"],
        "notes": content["notes"],
        "limitations": content["limitations"],
    }


def _number(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, int):
        return f"{value:d}"
    return f"{value:,.{digits}f}".replace(",", " ")


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(
        f"<tr><th scope=\"row\">{_escape(label)}</th><td>{value}</td></tr>"
        for label, value in pairs
    )


def _waterfall(report: dict[str, Any]) -> str:
    units = report["units"]
    if units["status"] != reasons.AVAILABLE:
        return (
            "<p class=\"warn\">Число потенциальных единиц не рассчитано: "
            f"{_escape(units['unavailable_reason'])}. Это не ноль единиц.</p>"
        )
    if units["r_adj_tco2e"] is None:
        return (
            "<p class=\"warn\">Q = 0 по правилу кейса "
            f"({_escape(units['zero_reason'])}). Пошаговая диаграмма вычетов для этого "
            "случая не строится: правило обрывает расчёт, а не снижает результат "
            "постепенно.</p>"
        )
    return "<table class=\"kv\">" + _rows([
        ("Результат относительно базовой линии R, тCO₂-экв.", _number(units["r_tco2e"])),
        ("Полуширина интервала H, тCO₂-экв.", _number(units["h_tco2e"])),
        ("Отношение H/R", _number(units["ratio"], 6)),
        ("Вычет за неопределённость UNC", _number(units["uncertainty_share"], 6)),
        ("Вычет за неопределённость, тCO₂-экв.", _number(units["uncertainty_deduction_tco2e"])),
        ("Результат после вычета R_adj, тCO₂-экв.", _number(units["r_adj_tco2e"])),
        ("Резерв B (15%), тCO₂-экв.", _number(units["buffer_tco2e"])),
        ("Потенциальные единицы Q", _number(units["units"])),
        ("Остаток округления, тCO₂-экв.", _number(units["rounding_residual_tco2e"], 6)),
    ]) + "</table>"


def _timeline_chart(points: list[dict[str, Any]], *, width: int = 620, height: int = 200) -> str:
    """Inline SVG of the annual stock curve: no script, no external resource, no library.

    The chart is drawn from the same timeline the table prints, so it cannot show a
    different curve. A flat series still gets a readable axis instead of a division by
    zero, and the years are printed so the picture is never the only source of a value.
    """
    if len(points) < 2:
        return "<p>Годовой ряд слишком короткий для графика.</p>"

    left, right, top, bottom = 58, 12, 14, 30
    plot_width = width - left - right
    plot_height = height - top - bottom
    values = [float(point["mean_tc_ha"]) for point in points]
    years = [int(point["year"]) for point in points]
    low, high = min(values), max(values)
    if high - low < 1e-9:
        low, high = low - 1.0, high + 1.0

    def x_of(index: int) -> float:
        return left + plot_width * index / (len(points) - 1)

    def y_of(value: float) -> float:
        return top + plot_height * (high - value) / (high - low)

    line = " ".join(f"{x_of(i):.1f},{y_of(value):.1f}" for i, value in enumerate(values))
    dots = "".join(
        f'<circle cx="{x_of(i):.1f}" cy="{y_of(value):.1f}" r="2.5" class="dot">'
        f"<title>{years[i]}: {value:.3f} т C/га</title></circle>"
        for i, value in enumerate(values)
    )
    ticks = "".join(
        f'<text x="{x_of(i):.1f}" y="{height - 10}" class="tick" text-anchor="middle">'
        f"{years[i]}</text>"
        for i in range(0, len(points), max(1, len(points) // 6))
    )
    grid = "".join(
        f'<line x1="{left}" y1="{y_of(value):.1f}" x2="{width - right}" '
        f'y2="{y_of(value):.1f}" class="grid"></line>'
        f'<text x="{left - 6}" y="{y_of(value) + 4:.1f}" class="tick" text-anchor="end">'
        f"{value:.1f}</text>"
        for value in (low, (low + high) / 2, high)
    )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Средний запас углерода по годам, т C/га">'
        f"{grid}{ticks}"
        f'<polyline points="{line}" class="curve"></polyline>{dots}</svg>'
    )


def _geometry_outline(geometry: dict[str, Any] | None, *, size: int = 180) -> str:
    """Inline SVG outline of the requested polygon, drawn from its own coordinates."""
    if not isinstance(geometry, dict):
        return ""
    kind = geometry.get("type")
    if kind == "Polygon":
        rings = geometry.get("coordinates") or []
    elif kind == "MultiPolygon":
        rings = [ring for polygon in geometry.get("coordinates") or [] for ring in polygon]
    else:
        return ""
    points = [point for ring in rings for point in ring]
    if len(points) < 3:
        return ""

    longitudes = [float(point[0]) for point in points]
    latitudes = [float(point[1]) for point in points]
    west, east = min(longitudes), max(longitudes)
    south, north = min(latitudes), max(latitudes)
    span = max(east - west, north - south, 1e-9)
    pad = 8

    def project(point: list[float]) -> str:
        x = pad + (size - 2 * pad) * (float(point[0]) - west) / span
        y = pad + (size - 2 * pad) * (north - float(point[1])) / span
        return f"{x:.1f},{y:.1f}"

    shapes = "".join(
        f'<polygon points="{" ".join(project(point) for point in ring)}" class="aoi"></polygon>'
        for ring in rings
        if len(ring) >= 3
    )
    return (
        f'<svg class="map" viewBox="0 0 {size} {size}" role="img" '
        f'aria-label="Контур запрошенного участка">{shapes}</svg>'
    )


def render_html(report: dict[str, Any]) -> str:
    """A standalone page: no script, no external resource, every user string escaped."""
    request = report["request"]
    interval = report["interval"]
    baseline = report["baseline"]
    units = report["units"]
    claim = report["claim"]
    area = report["area"] or {}
    optical = report["optical_quality"]

    outline = _geometry_outline(request.get("geometry"))
    chart = _timeline_chart(report["timeline"])

    timeline_rows = "".join(
        "<tr>"
        f"<td>{_escape(point['year'])}</td>"
        f"<td>{_number(point['mean_agb_t_ha'])}</td>"
        f"<td>{_number(point['mean_tc_ha'])}</td>"
        f"<td>{_number(point['total_tc'])}</td>"
        f"<td>{_number(point['covered_ha'])}</td>"
        "</tr>"
        for point in report["timeline"]
    ) or "<tr><td colspan=\"5\">годовой ряд не передан</td></tr>"

    sensitivity_rows = "".join(
        "<tr>"
        f"<td>{_escape(variant['spatial_dependence'])}</td>"
        f"<td>{_number(variant['temporal_correlation'], 1)}</td>"
        f"<td>{_number(variant['sd_tco2e'])}</td>"
        f"<td>{_number(variant['lower_tco2e'])}</td>"
        f"<td>{_number(variant['upper_tco2e'])}</td>"
        "</tr>"
        for variant in interval["sensitivity"]
    ) or "<tr><td colspan=\"5\">—</td></tr>"

    price_rows = "".join(
        f"<tr><td>{_number(value['price_rub'])}</td><td>{_number(value['value_rub'])}</td></tr>"
        for value in units["scenario_values"]
    ) or "<tr><td colspan=\"2\">—</td></tr>"

    source_rows = "".join(
        "<tr>"
        f"<td>{_escape(source['source_id'])}</td>"
        f"<td>{_escape(source['product'])}</td>"
        f"<td>{_escape(source['version'])}</td>"
        f"<td>{_escape(source['license_url'])}</td>"
        "</tr>"
        for source in report["provenance"]["sources"]
    ) or "<tr><td colspan=\"4\">—</td></tr>"

    file_rows = "".join(
        "<tr>"
        f"<td>{_escape(entry['relative_path'])}</td>"
        f"<td>{_escape(entry['checksum_status'])}</td>"
        f"<td class=\"hash\">{_escape(entry['declared_sha256'])}</td>"
        "</tr>"
        for entry in report["provenance"]["files"]
    ) or "<tr><td colspan=\"3\">—</td></tr>"

    note_items = "".join(
        f"<li><strong>{_escape(item['code'])}.</strong> {_escape(item['text'])}</li>"
        for item in report["notes"]
    )
    limitation_items = "".join(f"<li>{_escape(item)}</li>" for item in report["limitations"])

    optical_block = (
        "<p>Оптические снимки не передавались в этот расчёт.</p>"
        if optical is None
        else "<pre>" + _escape(json.dumps(optical, ensure_ascii=False, indent=1)) + "</pre>"
    )

    provisional = (
        ""
        if report["input_status"] == "RS_PAYLOAD"
        else "<p class=\"warn\">Входные пер-клеточные данные — предварительное локальное "
             "извлечение из официальных файлов, а не результат компонента RS.</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Углеродный паспорт участка {_escape(request['request_id'])}</title>
<style>
:root {{ color-scheme: light dark; --line: #c9ccd1; --warn: #8a5300; }}
body {{ font: 15px/1.55 system-ui, sans-serif; margin: 0 auto; max-width: 62rem; padding: 2rem 1rem; }}
h1 {{ font-size: 1.45rem; }}
h2 {{ font-size: 1.1rem; margin-top: 2rem; border-bottom: 1px solid var(--line); padding-bottom: .3rem; }}
table {{ border-collapse: collapse; width: 100%; margin: .6rem 0; }}
th, td {{ border: 1px solid var(--line); padding: .35rem .5rem; text-align: left; vertical-align: top; }}
table.kv th {{ width: 55%; font-weight: 500; }}
td, th {{ font-variant-numeric: tabular-nums; }}
.hash {{ font-family: ui-monospace, monospace; font-size: .8rem; word-break: break-all; }}
.warn {{ color: var(--warn); font-weight: 500; }}
pre {{ background: rgba(127,127,127,.12); padding: .6rem; overflow-x: auto; }}
svg.chart {{ width: 100%; max-width: 40rem; height: auto; }}
svg.map {{ width: 11rem; height: auto; float: right; margin: 0 0 .5rem 1rem; }}
.curve {{ fill: none; stroke: currentColor; stroke-width: 2; }}
.dot {{ fill: currentColor; }}
.grid {{ stroke: var(--line); stroke-width: 1; }}
.tick {{ font-size: 10px; fill: currentColor; opacity: .75; }}
.aoi {{ fill: rgba(127,127,127,.25); stroke: currentColor; stroke-width: 1.5; }}
footer {{ margin-top: 2.5rem; font-size: .85rem; }}
</style>
</head>
<body>
<h1>Углеродный паспорт участка {_escape(request['request_id'])}</h1>
<p class="hash">scientific_passport_content_hash: {_escape(report['passport_content_hash'])}<br>
source_manifest_hash: {_escape(report['hashes']['source_manifest_hash'])}<br>
integrity_manifest_hash: {_escape(report['manifest_hash'])}<br>
method_version: {_escape(report['method_version'])}</p>
{provisional}

<h2>Запрос и площадь</h2>
{outline}
<table class="kv">{_rows([
    ("Период", f"{_escape(request['year_start'])}–{_escape(request['year_end'])}"),
    ("Учитываемый пул", _escape(request["pool"])),
    ("Хеш геометрии", f"<span class=\"hash\">{_escape(request['geometry_hash'])}</span>"),
    ("Запрошенная площадь, га", _number(area.get("requested_ha"))),
    ("Расчётная площадь, га", _number(area.get("calculated_ha"))),
    ("Непокрытая площадь, га", _number(area.get("missing_ha"))),
    ("Покрытие биомассой", _number(report["coverage"]["biomass"], 6)),
    ("Покрытие базовой линией", _number(report["coverage"]["baseline"], 6)),
])}</table>

<h2>Оптическое качество</h2>
<p>Показано отдельно и не влияет на число единиц: облачность снимка не меняет модельную
оценку запаса биомассы.</p>
{optical_block}

<h2>Годовой ряд запаса</h2>
<p>Средний запас углерода, т C/га. График построен из той же таблицы, что напечатана ниже.</p>
{chart}
<table><thead><tr><th>Год</th><th>AGB, т/га</th><th>Углерод, т C/га</th>
<th>Запас, т C</th><th>Покрыто, га</th></tr></thead><tbody>{timeline_rows}</tbody></table>

<h2>Изменение запаса и сценарный интервал</h2>
<table class="kv">{_rows([
    ("Запас на начало, т C", _number(interval["stock_start_tc"])),
    ("Запас на конец, т C", _number(interval["stock_end_tc"])),
    ("Изменение запаса ΔC, т C", _number(interval["delta_stock_tc"])),
    ("E проекта, тCO₂-экв.", _number(interval["e_proj_tco2e"])),
    ("e, тCO₂-экв./га/год", _number(interval["e_per_ha_year_tco2e"], 6)),
    ("Стандартное отклонение, тCO₂-экв.", _number(interval["sd_tco2e"])),
    ("Нижняя граница L, тCO₂-экв.", _number(interval["lower_tco2e"])),
    ("Верхняя граница U, тCO₂-экв.", _number(interval["upper_tco2e"])),
    ("Пространственная зависимость", _escape(report["method_options"]["spatial_dependence"])),
    ("Временная корреляция ρ", _number(report["method_options"]["temporal_correlation"], 3)),
    ("Коэффициент охвата k", _number(report["method_options"]["coverage_factor"], 3)),
])}</table>
<p>Положительное E — потеря углерода из учитываемого пула, отрицательное — накопление.</p>

<h3>Чувствительность интервала к допущениям</h3>
<table><thead><tr><th>Пространственная зависимость</th><th>ρ</th><th>SD</th>
<th>L</th><th>U</th></tr></thead><tbody>{sensitivity_rows}</tbody></table>

<h2>Базовая линия</h2>
<table class="kv">{_rows([
    ("Источник", _escape(baseline["source"])),
    ("Изменение запаса базовой линии, т C/га", _number(baseline["delta_tc_ha"], 6)),
    ("E базовой линии, тCO₂-экв.", _number(baseline["e_base_tco2e"])),
    ("Утечка LK, тCO₂-экв.", _number(units["leakage_tco2e"])),
])}</table>

<h2>Вычеты, резерв и единицы</h2>
{_waterfall(report)}
<table><thead><tr><th>Сценарная цена, руб./ед.</th><th>Стоимость, руб.</th></tr></thead>
<tbody>{price_rows}</tbody></table>

<h2>Заявленный объём</h2>
<table class="kv">{_rows([
    ("Статус сравнения", _escape(_CLAIM_TEXT.get(claim["status"], claim["status"]))),
    ("Код статуса", _escape(claim["status"])),
    ("Причина", _escape(claim.get("reason")) or "—"),
    ("Источник заявления", _escape(claim["source"])),
    ("Заявлено, ед.", _number(claim["claimed_units"], 3)),
    ("Расчёт по условиям кейса, ед.", _number(claim["units"])),
    ("Разрыв, ед.", _number(claim["unsupported_gap"], 3)),
    ("Доля поддержки", _number(claim["supported_share"], 6)),
])}</table>

<h2>Пояснения</h2>
<ul>{note_items}</ul>

<h2>Ограничения</h2>
<ul>{limitation_items}</ul>

<h2>Источники, лицензии и версии</h2>
<table><thead><tr><th>Источник</th><th>Продукт</th><th>Версия</th><th>Лицензия</th></tr></thead>
<tbody>{source_rows}</tbody></table>
<table><thead><tr><th>Файл</th><th>Контрольная сумма</th><th>SHA-256</th></tr></thead>
<tbody>{file_rows}</tbody></table>

<footer>
<p>Статус расчёта единиц: {_escape(_STATUS_TEXT.get(units["status"], units["status"]))}.
Отчёт сформирован {_escape(report["run"]["created_at"])}, запуск
{_escape(report["run"]["run_id"])}. Отметка времени не входит в content_hash, поэтому
две сборки одного и того же расчёта различаются побайтно, но совпадают по содержанию.</p>
</footer>
</body>
</html>
"""
