#!/usr/bin/env python3
"""Deterministic renderer for the A-share sector-leading-signal report.

The renderer deliberately consumes only structured decisions, market metrics,
grounded claims and source candidates.  In particular, model-authored
``driver`` and ``summary`` fields are never rendered.  Keeping this module free
of network and model calls makes the published Markdown reproducible from a
frozen snapshot.
"""

from __future__ import annotations

import math
import statistics
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any, Iterable


EVIDENCE_CATEGORIES = ("S", "O", "E")
SW_SOURCE_URL = "https://www.swsresearch.com/institute_sw/allIndex/releasedIndex"


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    rendered = str(value).strip()
    return rendered or default


def _cell(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fmt_pct(value: Any, digits: int = 2) -> str:
    parsed = _safe_float(value)
    return "未计算" if parsed is None else f"{parsed * 100:+.{digits}f}%"


def _fmt_ratio(value: Any) -> str:
    parsed = _safe_float(value)
    return "未计算" if parsed is None else f"{parsed * 100:.1f}%"


def _fmt_percentile(value: Any) -> str:
    parsed = _safe_float(value)
    return "未计算" if parsed is None else f"{parsed:.1f}%"


def _fmt_utilization(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "未提供"
    # Ratios are represented as 0..1; callers may also supply an already
    # percent-scaled value for human-oriented run status.
    return f"{parsed * 100:.1f}%" if abs(parsed) <= 1 else f"{parsed:.1f}%"


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _link(label: Any, url: Any) -> str:
    safe_label = _text(label, "来源").replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("|", "\\|")
    raw_url = _text(url, "")
    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return safe_label
    safe_url = raw_url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    return f"[{safe_label}]({safe_url})"


def _unique_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item.upper() == "NONE" or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value, key=str)
    return [value]


def _candidate_index(candidates: dict[str, list[dict]], code: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in candidates.get(code, []) or []:
        if not isinstance(item, dict):
            continue
        candidate_id = _text(item.get("id"), "").upper()
        if candidate_id:
            result[candidate_id] = item
    return result


def _evidence_ids(item: dict) -> list[str]:
    values: list[Any] = []
    for key in ("evidence_ids", "evidence_refs", "refs"):
        values.extend(_values(item.get(key)))
    result: list[str] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("evidence_id") or value.get("id") or value.get("ref")
        rendered = _text(value, "").upper()
        if rendered and rendered not in result:
            result.append(rendered)
    return result


def _contrary_ids(item: dict) -> list[str]:
    values: list[Any] = []
    for key in ("contrary_evidence_ids", "contrary_ids", "counter_evidence_ids"):
        values.extend(_values(item.get(key)))
    return _unique_strings(
        (value.get("id") or value.get("evidence_id")) if isinstance(value, dict) else value
        for value in values
    )


def _normalise_claims(item: dict) -> list[dict]:
    """Return grounded, displayable claims without consulting free prose fields."""

    raw_claims: list[Any] = []
    for key in ("claims", "partial_claims", "claim_details"):
        raw_claims.extend(_values(item.get(key)))
    claims: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in raw_claims:
        if isinstance(raw, str):
            claim = {"text": raw}
        elif isinstance(raw, dict):
            claim = raw
        else:
            continue
        text = _text(
            claim.get("claim")
            or claim.get("text")
            or claim.get("fact")
            or claim.get("statement"),
            "",
        )
        evidence_id = _text(
            claim.get("evidence_id") or claim.get("id") or claim.get("ref"), ""
        ).upper()
        category = _text(claim.get("category") or claim.get("type"), "").upper()
        entity = _text(claim.get("entity") or claim.get("subject"), "")
        if not any((text, evidence_id, category, entity)):
            continue
        key = (text, evidence_id, category, entity)
        if key in seen:
            continue
        seen.add(key)
        claims.append(
            {
                "text": text,
                "evidence_id": evidence_id,
                "category": category if category in EVIDENCE_CATEGORIES else "",
                "entity": entity,
                "url": claim.get("url"),
                "title": claim.get("title"),
                "pub_date": claim.get("pub_date") or claim.get("published_at"),
            }
        )
    return claims


def _claim_refs(item: dict, candidates: dict[str, list[dict]], code: str) -> list[dict]:
    index = _candidate_index(candidates, code)
    refs: list[dict] = []
    seen: set[str] = set()
    for evidence_id in _evidence_ids(item):
        candidate = index.get(evidence_id)
        if candidate is not None and evidence_id not in seen:
            refs.append(candidate)
            seen.add(evidence_id)
    for claim in _normalise_claims(item):
        evidence_id = claim["evidence_id"]
        candidate = index.get(evidence_id)
        if candidate is not None and evidence_id not in seen:
            refs.append(candidate)
            seen.add(evidence_id)
        elif not evidence_id and claim.get("url"):
            synthetic = {
                "id": "",
                "title": claim.get("title") or claim.get("text") or "claim来源",
                "url": claim.get("url"),
                "pub_date": claim.get("pub_date"),
            }
            key = str(synthetic["url"])
            if key not in seen:
                refs.append(synthetic)
                seen.add(key)
    return refs


def _category_values(item: dict) -> list[str]:
    categories = _unique_strings(_values(item.get("categories")))
    for claim in _normalise_claims(item):
        if claim["category"]:
            categories.append(claim["category"])
    return [category for category in _unique_strings(categories) if category in EVIDENCE_CATEGORIES]


def _entity_values(item: dict) -> list[str]:
    entities = _unique_strings(_values(item.get("entities")))
    entities.extend(claim["entity"] for claim in _normalise_claims(item) if claim["entity"])
    return _unique_strings(entities)


def _distinct_urls(item: dict, candidates: dict[str, list[dict]], code: str) -> list[str]:
    return _unique_strings(ref.get("url") for ref in _claim_refs(item, candidates, code) if ref.get("url"))


def _breadth_available(metric: dict) -> bool:
    breadth = metric.get("breadth")
    if not isinstance(breadth, dict):
        return False
    if "available" in breadth:
        return bool(breadth.get("available"))
    ratios = breadth.get("ratios") or []
    return bool(ratios) and _safe_float(ratios[0]) is not None


def _market_parts(metric: dict) -> list[tuple[str, str, bool | None]]:
    breadth_state: bool | None = bool(metric.get("breadth_ok")) if _breadth_available(metric) else None
    return [
        ("相对", "通过" if bool(metric.get("relative_ok")) else "未通过", bool(metric.get("relative_ok"))),
        ("广度", "通过" if breadth_state else ("未通过" if breadth_state is False else "未计算"), breadth_state),
        ("成交", "通过" if bool(metric.get("turnover_ok")) else "未通过", bool(metric.get("turnover_ok"))),
    ]


def _market_pass_count(metric: dict) -> int:
    return sum(state is True for _, _, state in _market_parts(metric))


def _market_label(metric: dict) -> str:
    return " / ".join(f"{name}{label}" for name, label, _ in _market_parts(metric))


def _rank(metric: dict) -> int:
    value = metric.get("rank_20d")
    parsed = _safe_int(value, 10**9)
    return parsed if parsed > 0 else 10**9


def _is_crowded(metric: dict) -> bool:
    return bool(_text(metric.get("crowding_state"), ""))


def _gate(item: dict) -> str:
    return _text(item.get("gate"), "WATCH").upper()


def _quality_flags(item: dict) -> list[str]:
    return _unique_strings(_values(item.get("quality_flags")))


def _evidence_gap_parts(item: dict, candidates: dict[str, list[dict]], code: str) -> list[str]:
    categories = _category_values(item)
    entities = _entity_values(item)
    urls = _distinct_urls(item, candidates, code)
    contrary = _contrary_ids(item)
    flags = _quality_flags(item)
    gate_blockers = _unique_strings(_values(item.get("gate_blockers")))
    missing_categories = max(0, 2 - len(categories))
    missing_entities = max(0, 2 - len(entities))
    missing_urls = max(0, 2 - len(urls))
    parts = [
        f"类别：{','.join(categories) if categories else '无'}（还缺{missing_categories}类）",
        f"主体：{len(entities)}/2（还缺{missing_entities}个）",
        f"独立URL：{len(urls)}/2（还缺{missing_urls}个）",
        f"相反证据：{str(len(contrary)) + '条' if contrary else '无'}",
        f"质量旗标：{','.join(flags) if flags else '无'}",
    ]
    if _text(item.get("decision_source"), "") == "rules_recovery":
        eligible_categories = _unique_strings(_values(item.get("gate_eligible_categories")))
        eligible_entities = _unique_strings(_values(item.get("gate_eligible_entities")))
        eligible_urls = _safe_int(item.get("gate_eligible_url_count"))
        parts.append(
            "规则恢复可入门O/E："
            f"类别{','.join(eligible_categories) if eligible_categories else '无'}；"
            f"成分公司主体{len(eligible_entities)}/2；独立URL{eligible_urls}/2；"
            f"阻断：{'；'.join(gate_blockers) if gate_blockers else '无'}"
        )
    return parts


def _gap_count(item: dict, candidates: dict[str, list[dict]], code: str) -> int:
    return (
        max(0, 2 - len(_category_values(item)))
        + max(0, 2 - len(_entity_values(item)))
        + max(0, 2 - len(_distinct_urls(item, candidates, code)))
        + len(_contrary_ids(item))
        + len(_quality_flags(item))
        + len(_unique_strings(_values(item.get("gate_blockers"))))
    )


def _near_miss_key(code: str, evidence: dict[str, dict], candidates: dict[str, list[dict]], metrics: dict[str, dict]) -> tuple:
    item = evidence.get(code, {})
    metric = metrics.get(code, {})
    return (
        -_market_pass_count(metric),
        _gap_count(item, candidates, code),
        len(_quality_flags(item)),
        -len(_category_values(item)),
        -len(_entity_values(item)),
        -len(_distinct_urls(item, candidates, code)),
        _rank(metric),
        code,
    )


def _render_claims(lines: list[str], code: str, item: dict, candidates: dict[str, list[dict]]) -> None:
    index = _candidate_index(candidates, code)
    claims = _normalise_claims(item)
    if claims:
        lines.append("- 已绑定的部分claim：")
        for claim in claims:
            candidate = index.get(claim["evidence_id"], {})
            text = claim["text"] or candidate.get("title") or claim["evidence_id"] or "结构化claim"
            url = claim.get("url") or candidate.get("url")
            source = _link(text, url)
            tags = " / ".join(part for part in (claim["category"], claim["entity"]) if part)
            published = claim.get("pub_date") or candidate.get("pub_date") or candidate.get("published_at")
            suffix = "；" + _cell(tags) if tags else ""
            suffix += f"；{_cell(str(published)[:10])}" if published else ""
            lines.append(f"  - {source}{suffix}")
        return

    # A WATCH decision with no structured claim should still let the reader
    # inspect what the collector saw, while clearly separating candidates from
    # evidence admitted by the gate.
    raw_candidates = [item for item in (candidates.get(code, []) or []) if isinstance(item, dict)]
    raw_candidates.sort(
        key=lambda row: (
            -((_parse_date(row.get("pub_date") or row.get("published_at")) or date.min).toordinal()),
            _text(row.get("id")),
            _text(row.get("title")),
        )
    )
    if raw_candidates:
        lines.append("- 未被证据门采用的候选标题（最多2条）：")
        for candidate in raw_candidates[:2]:
            published = candidate.get("pub_date") or candidate.get("published_at")
            suffix = f"（{_cell(str(published)[:10])}）" if published else ""
            lines.append(f"  - {_link(candidate.get('title'), candidate.get('url'))}{suffix}")
    else:
        lines.append("- 未被证据门采用的候选标题：无候选可展示。")


def _render_event_result(value: Any) -> str:
    if not isinstance(value, dict):
        return "未完成"
    result = _fmt_pct(value.get("return"))
    rank = value.get("rank")
    return f"{result} / 第{rank}" if rank else result


def _run_outcome(run_quality: dict) -> tuple[str, str]:
    outcome = _text(run_quality.get("outcome") or run_quality.get("status"), "normal").lower()
    eligibility = _text(run_quality.get("sample_eligibility"), "").lower()
    if "stale" in outcome:
        return "上游行情滞后", "停止正式出信号、停止写入前瞻账本；本页只保留数据质量诊断。"
    if "repair" in outcome or "repair" in eligibility or "excluded" in eligibility:
        return "修复回填（不计前瞻）", "本期用于修复和方法诊断，不进入前瞻命中率、召回率或激活分母。"
    if outcome in {"failed", "error", "blocked"}:
        return "运行失败", "不发布正式信号，不写入前瞻账本；需先处理运行错误。"
    return "正式前瞻样本", "按冻结规则发布；新增激活从下一共同交易日开盘代理记账。"


def format_report(
    report_date: str,
    strategy_version: str,
    industries: list[dict],
    evidence: dict[str, dict],
    candidates: dict[str, list[dict]],
    metrics: dict[str, dict],
    radar: list[str],
    states: dict[str, str],
    new_activations: list[str],
    holds: list[str],
    ledger: dict,
    model: str,
    lookback_days: int,
    run_quality: dict | None = None,
) -> str:
    """Render one deterministic, audit-oriented Markdown weekly report.

    The positional arguments intentionally match the former in-script renderer;
    ``run_quality`` is optional so callers can migrate without changing their
    frozen report invocation in the same commit.
    """

    run_quality = dict(run_quality or {})
    names = {str(item.get("code")): _text(item.get("name"), str(item.get("code"))) for item in industries}
    codes = [str(item.get("code")) for item in industries]
    pass_codes = [code for code in codes if _gate(evidence.get(code, {})) == "PASS"]
    crowded_codes = [code for code in codes if _is_crowded(metrics.get(code, {}))]
    expected_date = run_quality.get("expected_market_date") or run_quality.get("expected_date")
    source_date = run_quality.get("source_market_date") or run_quality.get("actual_market_date") or report_date
    status_label, action = _run_outcome(run_quality)
    parsed_report_date = _parse_date(report_date)
    window_start = (parsed_report_date - timedelta(days=6)).isoformat() if parsed_report_date else "未计算"

    candidate_count = run_quality.get("candidate_count")
    if candidate_count is None:
        candidate_count = sum(len(items or []) for items in candidates.values())
    claims_count = run_quality.get("claim_count")
    if claims_count is None:
        claims_count = sum(len(_normalise_claims(evidence.get(code, {}))) for code in codes)
    refs_count = run_quality.get("evidence_ref_count")
    if refs_count is None:
        refs_count = sum(len(_evidence_ids(evidence.get(code, {}))) for code in codes)
    covered_count = sum(bool(candidates.get(code)) for code in codes)

    valid_returns = [
        value
        for code in codes
        if (value := _safe_float(metrics.get(code, {}).get("return_20d"))) is not None
    ]
    positive_count = sum(value > 0 for value in valid_returns)
    median_return = statistics.median(valid_returns) if valid_returns else None
    market_sorted = sorted(codes, key=lambda code: (_rank(metrics.get(code, {})), code))
    top_market = market_sorted[:3]
    breadth_unknown = sum(not _breadth_available(metrics.get(code, {})) for code in codes)

    quality_eligible = [code for code in pass_codes if len(_quality_flags(evidence.get(code, {}))) < 2]
    noncrowded = [code for code in quality_eligible if not _is_crowded(metrics.get(code, {}))]
    market_confirmed = [code for code in noncrowded if _market_pass_count(metrics.get(code, {})) >= 2]
    engine_version = _text(run_quality.get("evidence_engine_version"), "未提供")
    engine_sha = _text(run_quality.get("engine_sha256"), "")
    engine_label = engine_version + (f" @ {engine_sha[:12]}" if engine_sha else "")

    lines = [
        f"# A股产业领先信号周报｜{report_date}",
        "",
        "> 产业证据与市场确认分开审计。PASS不等于买入；行业指数不可直接交易；本报告不构成投资建议。",
        "",
        "## 运行质量与本周动作",
        "",
        "| 项目 | 结果 |",
        "|---|---|",
        f"| 样本性质 | **{status_label}** |",
        f"| 本周动作 | {_cell(action)} |",
        f"| 观察窗口 | {window_start} 至 {report_date} |",
        f"| 行情应到 / 实到 | {_cell(expected_date or '未提供')} / {_cell(source_date or '未提供')} |",
        f"| 策略版本 | `{_cell(strategy_version)}` |",
        f"| 证据引擎 | `{_cell(engine_label)}` |",
        f"| 候选 / claim / 采用引用 | {candidate_count} / {claims_count} / {refs_count} |",
        f"| 候选行业覆盖 | {covered_count}/{len(codes)} |",
        f"| 语义利用率 | {_fmt_utilization(run_quality.get('semantic_utilization'))} |",
        f"| 新激活 / 持有确认 | {len(new_activations)} / {len(holds)} |",
    ]
    if run_quality.get("simulated_activations"):
        simulated = [names.get(str(code), str(code)) for code in run_quality["simulated_activations"]]
        lines.append(f"| 修复样本模拟激活（不记账） | {_cell('、'.join(simulated))} |")
    checked_at = run_quality.get("checked_at") or run_quality.get("generated_at")
    if checked_at:
        lines.append(f"| 本次检查时间 | {_cell(checked_at)} |")
    source_errors = run_quality.get("source_error_total")
    if source_errors is not None:
        lines.append(f"| 数据源错误 | {_safe_int(source_errors)} |")
    recovery_batches = _safe_int(run_quality.get("ai_recovery_batches"))
    if recovery_batches:
        lines.append(f"| 模型协议规则恢复 | {recovery_batches} 批；仅采用标题、实体、时点与TTL均通过脚本校验的字段 |")

    if new_activations:
        lines += ["", "本周新增激活：" + "、".join(names.get(code, code) for code in new_activations) + "。"]
    elif status_label == "正式前瞻样本":
        lines += ["", "本周没有候选同时通过证据、质量、防追高与市场三选二，不为凑数激活。"]

    lines += [
        "",
        "## 市场概览",
        "",
        "| 指标 | 结果 |",
        "|---|---|",
        f"| 20日上涨行业 | {positive_count}/{len(valid_returns)}（其余未计算{len(codes) - len(valid_returns)}） |",
        f"| 31行业20日中位数 | {_fmt_pct(median_return)} |",
        f"| 防追高行业 | {len(crowded_codes)} |",
        f"| 广度未计算 | {breadth_unknown}/{len(codes)}；未计算不视为失败 |",
    ]
    if top_market:
        top_text = "；".join(
            f"{names.get(code, code)} {_fmt_pct(metrics.get(code, {}).get('return_20d'))}（第{_rank(metrics.get(code, {})) if _rank(metrics.get(code, {})) < 10**9 else '-'}）"
            for code in top_market
        )
        lines.append(f"| 20日排名前三 | {_cell(top_text)} |")

    lines += [
        "",
        "## 信号漏斗",
        "",
        "| 阶段 | 行业数 | 说明 |",
        "|---|---:|---|",
        f"| 有候选输入 | {covered_count} | 共{candidate_count}条候选 |",
        f"| 硬证据PASS | {len(pass_codes)} | 至少2类、2主体、2个独立URL、2个事件簇，且含成分公司 |",
        f"| 质量可用 | {len(quality_eligible)} | 少于2个质量旗标 |",
        f"| 排除拥挤后 | {len(noncrowded)} | 不新增追逐成熟周期或短期急涨 |",
        f"| 市场三选二 | {len(market_confirmed)} | 未计算的广度不计通过、也不计失败 |",
        f"| 雷达 / 新激活 | {len(radar)} / {len(new_activations)} | 雷达上限8，新激活上限3 |",
        "",
    ]

    if radar:
        lines += [
            "## 已通过证据门的雷达",
            "",
            "| 雷达序号 | 行业 | S/O/E | 主体 | 独立URL | 市场三项 | 20日排名 | 状态 |",
            "|---:|---|---|---:|---:|---|---:|---|",
        ]
        for position, code in enumerate(radar, 1):
            item = evidence.get(code, {})
            metric = metrics.get(code, {})
            rank = _rank(metric)
            lines.append(
                f"| {position} | {names.get(code, code)} | {','.join(_category_values(item)) or '-'} | "
                f"{len(_entity_values(item))} | {len(_distinct_urls(item, candidates, code))} | "
                f"{_cell(_market_label(metric))} | {rank if rank < 10**9 else '-'} | {_cell(states.get(code, '-'))} |"
            )
        lines.append("")
        for code in radar:
            item = evidence.get(code, {})
            lines += [f"### {names.get(code, code)}｜结构化证据审计", ""]
            lines.append("- 证据缺口/核对：" + "；".join(_evidence_gap_parts(item, candidates, code)) + "。")
            _render_claims(lines, code, item, candidates)
            lines.append("")
    else:
        lines += [
            "## 证据门结果",
            "",
            "本期 **0 个行业通过硬证据门**。因此不生成空的Top 8表或空证据链，以下直接展示最值得补证的行情近失配。",
            "",
        ]

    near_misses = [
        code
        for code in codes
        if _gate(evidence.get(code, {})) != "PASS"
        and not _is_crowded(metrics.get(code, {}))
        and _market_pass_count(metrics.get(code, {})) >= 2
    ]
    near_misses.sort(key=lambda code: _near_miss_key(code, evidence, candidates, metrics))
    lines += ["## 行情领先但证据未闭环（近失配 Top 5）", ""]
    if near_misses:
        lines.append("排序依次考虑市场通过数、证据缺口、质量旗标、证据覆盖、20日排名和行业代码；同一快照结果固定。")
        lines.append("")
        for position, code in enumerate(near_misses[:5], 1):
            item = evidence.get(code, {})
            metric = metrics.get(code, {})
            rank = _rank(metric)
            lines += [
                f"### {position}. {names.get(code, code)}",
                "",
                f"- 行情：20日{_fmt_pct(metric.get('return_20d'))}、排名第{rank if rank < 10**9 else '未计算'}；{_market_label(metric)}。",
                "- 证据缺口：" + "；".join(_evidence_gap_parts(item, candidates, code)) + "。",
            ]
            _render_claims(lines, code, item, candidates)
            lines.append("")
    else:
        lines += ["没有同时满足“WATCH、非拥挤、市场至少两项通过”的行业。", ""]

    evidence_leading = [
        code
        for code in pass_codes
        if not _is_crowded(metrics.get(code, {})) and _market_pass_count(metrics.get(code, {})) < 2
    ]
    evidence_leading.sort(key=lambda code: (_market_pass_count(metrics.get(code, {})), _rank(metrics.get(code, {})), code))
    lines += ["## 证据领先、市场尚未确认", ""]
    if evidence_leading:
        lines += ["| 行业 | S/O/E | 主体 / URL | 市场三项 | 处理 |", "|---|---|---|---|---|"]
        for code in evidence_leading:
            item = evidence.get(code, {})
            lines.append(
                f"| {names.get(code, code)} | {','.join(_category_values(item)) or '-'} | "
                f"{len(_entity_values(item))} / {len(_distinct_urls(item, candidates, code))} | "
                f"{_cell(_market_label(metrics.get(code, {})))} | 继续观察，不提前激活 |"
            )
    else:
        lines.append("本期无“证据PASS但市场少于两项确认”的非拥挤行业。")

    lines += ["", "## 拥挤防追高", ""]
    if crowded_codes:
        lines += ["| 20日排名 | 行业 | 拥挤状态 | 触发原因 | 证据门 | 处理 |", "|---:|---|---|---|---|---|"]
        for code in sorted(crowded_codes, key=lambda value: (_rank(metrics.get(value, {})), value)):
            metric = metrics.get(code, {})
            rank = _rank(metric)
            lines.append(
                f"| {rank if rank < 10**9 else '-'} | {names.get(code, code)} | {_cell(metric.get('crowding_state'))} | "
                f"{_cell(metric.get('crowding_reason'))} | {_gate(evidence.get(code, {}))} | 禁止新增，不等于看空 |"
            )
    else:
        lines.append("本期没有行业触发E30、延续拥挤或短期急涨防追高条件。")

    lines += [
        "",
        "## 前瞻激活账本",
        "",
        "收益从信号后的下一共同交易日开盘代理计算；20/60日窗口未完成时不能提前判为成功或失败。修复回填样本不进入该分母。",
        "",
        "| 信号日 | 行业 | 代理入场日 | 20日收益 / 排名 | 60日收益 / 排名 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    events = ledger.get("events") or []
    if events:
        for event in events:
            lines.append(
                f"| {_cell(event.get('signal_date'))} | {_cell(event.get('name') or names.get(str(event.get('code')), event.get('code')))} | "
                f"{_cell(event.get('entry_date') or '待定')} | {_render_event_result(event.get('future_20d'))} | "
                f"{_render_event_result(event.get('future_60d'))} | {_cell(event.get('status') or '观察中')} |"
            )
    else:
        lines.append("| - | 暂无激活 | - | - | - | 等待正式前瞻样本 |")

    hold_events = ledger.get("hold_observations") or []
    lines += [
        "",
        "### 持有确认观察（不进入新激活分母）",
        "",
        "| 确认日 | 行业 | 代理起点 | 20日收益 / 排名 | 60日收益 / 排名 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    if hold_events:
        for event in hold_events:
            lines.append(
                f"| {_cell(event.get('signal_date'))} | {_cell(event.get('name') or names.get(str(event.get('code')), event.get('code')))} | "
                f"{_cell(event.get('entry_date') or '待定')} | {_render_event_result(event.get('future_20d'))} | "
                f"{_render_event_result(event.get('future_60d'))} | {_cell(event.get('status') or '观察中')} |"
            )
    else:
        lines.append("| - | 暂无持有确认 | - | - | - | 等待样本 |")

    closures = ledger.get("cycle_closures") or []
    if closures:
        lines += ["", "### 已关闭周期", "", "| 行业 | 激活日 | 关闭日 | 原因 |", "|---|---|---|---|"]
        for item in closures:
            lines.append(
                f"| {_cell(item.get('name') or names.get(str(item.get('code')), item.get('code')))} | "
                f"{_cell(item.get('signal_date'))} | {_cell(item.get('close_date'))} | {_cell(item.get('reason'))} |"
            )

    lines += [
        "",
        "## 31行业完整附录",
        "",
        "| 20日排名 | 行业 | 5日 | 20日 | 相对20日 | 成交分位 | 广度 | 市场通过数 | 证据门 | S/O/E | 主体 / URL | 拥挤 | 状态 |",
        "|---:|---|---:|---:|---:|---:|---|---:|---|---|---|---|---|",
    ]
    for code in market_sorted:
        metric = metrics.get(code, {})
        item = evidence.get(code, {})
        breadth = metric.get("breadth") if isinstance(metric.get("breadth"), dict) else {}
        ratios = breadth.get("ratios") or []
        breadth_text = _fmt_ratio(ratios[0]) if _breadth_available(metric) and ratios else "未计算"
        rank = _rank(metric)
        lines.append(
            f"| {rank if rank < 10**9 else '-'} | {names.get(code, code)} | {_fmt_pct(metric.get('return_5d'))} | "
            f"{_fmt_pct(metric.get('return_20d'))} | {_fmt_pct(metric.get('relative_20d'))} | "
            f"{_fmt_percentile(metric.get('turnover_percentile'))} | {breadth_text} | {_market_pass_count(metric)} | "
            f"{_gate(item)} | {','.join(_category_values(item)) or '-'} | "
            f"{len(_entity_values(item))} / {len(_distinct_urls(item, candidates, code))} | "
            f"{_cell(metric.get('crowding_state'))} | {_cell(states.get(code, '-'))} |"
        )

    lines += [
        "",
        "## 固定规则与数据限制",
        "",
        "1. 硬证据PASS要求结构化claim覆盖S/O/E至少两类、两个独立主体、两个不同URL和两个事件簇，且至少一个主体为申万成分公司；标题候选本身不等于已采用证据。",
        "2. 市场激活三选二：20日相对收益转正或持续改善；成分股站上60日均线比例连续两周上升；成交额占比上升且低于自身近三年85%分位。广度未计算时记为未知，不记失败。",
        "3. 防追高任一命中即禁止新增：本年已触及E30；上年涨幅至少50%且当前20日前8；当前20日前3且涨幅至少15%。防追高不等于看空。",
        "4. 证据与市场是两道独立门：WATCH即使行情领先也只能进入近失配，PASS但市场不足两项只能进入等待确认。",
        f"5. 候选新闻回看{lookback_days}日；claim仍受各字段TTL和报告截止时点约束。模型`{_cell(model)}`只能分类冻结候选，不能补写事实。",
        "6. 收盘后形成正式信号，下一共同交易日开盘仅作统一诊断代理；未计滑点、费用、涨跌停、容量和个股治理风险。",
        "7. 每期冻结候选、结构化claim、行情派生值、状态、运行质量和哈希；修复回填或上游滞后样本不得混入前瞻统计。",
        "",
        f"行情来源：[申万指数官方数据]({SW_SOURCE_URL})。",
        "",
        f"公开输入快照：[查看本期snapshot](./snapshots/{report_date}.json)。",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["format_report"]
