"""Report renderers.

Both renderers are pure functions of a `FinalReport`. Nothing is computed here and no model
is called, so the same stored run always produces the same document — which is what makes a
report something you can cite in a meeting rather than a fresh opinion each time you ask.
"""

from __future__ import annotations

from app.schemas.result import FinalReport, SectionKind
from app.schemas.trust import TrustStatus

RULE = "=" * 78

# Characters models routinely emit that a cp1252 console cannot print (BUG-001). The
# narrative is the one part of a report that is model-written, so it is the one part that
# can carry them - and a report that renders as "Aurora?s" undermines the document it is
# trying to make authoritative.
_SUBSTITUTIONS = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "…": "...",
    " ": " ",
}


def ascii_safe(text: str) -> str:
    """Render model prose printable on any console, without silently losing characters."""
    for source, replacement in _SUBSTITUTIONS.items():
        text = text.replace(source, replacement)
    return text.encode("ascii", "replace").decode("ascii")


def _section_name(section: SectionKind) -> str:
    return section.value.replace("_", " ").lower()


def to_markdown(report: FinalReport) -> str:
    """Render the report as Markdown, ASCII only (BUG-001)."""
    lines: list[str] = [
        "# Investigation Report",
        "",
        f"**Run:** `{report.run_id}`  ",
        f"**Objective:** {report.objective}  ",
        f"**Generated:** {report.generated_at:%Y-%m-%d %H:%M UTC}  ",
        f"**Overall confidence:** {report.overall_confidence:.2f} "
        f"(mean across {len(report.verified_findings)} verified finding(s))",
        "",
        "---",
        "",
    ]

    for section in report.sections:
        if section.kind is SectionKind.LIMITATIONS:
            continue  # rendered from the structured list below, not the placeholder
        lines.append(f"## {section.heading}")
        lines.append("")
        if section.narrative:
            lines.append(ascii_safe(section.narrative))
            lines.append("")
        for item in section.items:
            lines.append(f"- {item}")
        if section.items:
            lines.append("")

    if report.narrative_checks:
        lines.append("## How grounded the narrative is")
        lines.append("")
        lines.append(
            "The summary and reasoning above are the only text a model wrote. Each sentence was "
            "checked against the lines the findings cite (Member 4's answer evaluator)."
        )
        lines.append("")
        for check in report.narrative_checks:
            lines.append(f"- **{_section_name(check.section)}**: {check.overall.value}")
            for sentence in check.sentences:
                if sentence.status is TrustStatus.SUPPORTED:
                    continue
                values = (
                    f" - not in evidence: {', '.join(sentence.ungrounded)}"
                    if sentence.ungrounded
                    else ""
                )
                lines.append(
                    f'  - {sentence.status.value}: "{ascii_safe(sentence.sentence)}"{values}'
                )
        lines.append("")

    lines.append("## Limitations")
    lines.append("")
    if report.limitations:
        lines.append("The following constrain how far the findings above can be relied on.")
        lines.append("")
        for limitation in report.limitations:
            cause = f" _({limitation.cause})_" if limitation.cause else ""
            lines.append(f"- {limitation.description}{cause}")
    else:
        lines.append("No limitations were recorded for this run.")
    lines.append("")

    return "\n".join(lines)


def to_text(report: FinalReport) -> str:
    """Plain-text rendering for the terminal."""
    lines = [
        RULE,
        "INVESTIGATION REPORT",
        RULE,
        f"run        : {report.run_id}",
        f"objective  : {report.objective}",
        f"confidence : {report.overall_confidence:.2f} "
        f"(mean across {len(report.verified_findings)} verified)",
        "",
    ]

    for section in report.sections:
        if section.kind is SectionKind.LIMITATIONS:
            continue
        lines.append(section.heading.upper())
        lines.append("-" * len(section.heading))
        if section.narrative:
            lines.append(ascii_safe(section.narrative))
            lines.append("")
        for item in section.items:
            lines.append(f"  - {item}")
        lines.append("")

    if report.narrative_checks:
        lines.append("NARRATIVE CHECK")
        lines.append("-" * len("NARRATIVE CHECK"))
        for check in report.narrative_checks:
            weak = [s for s in check.sentences if s.status is not TrustStatus.SUPPORTED]
            lines.append(
                f"  {_section_name(check.section):<18} {check.overall.value}"
                f"  ({len(check.sentences) - len(weak)} of {len(check.sentences)} supported)"
            )
            for sentence in weak:
                values = (
                    f" [not in evidence: {', '.join(sentence.ungrounded)}]"
                    if sentence.ungrounded
                    else ""
                )
                lines.append(
                    f"    - {sentence.status.value}: {ascii_safe(sentence.sentence)[:90]}{values}"
                )
        lines.append("")

    lines.append("LIMITATIONS")
    lines.append("-" * len("LIMITATIONS"))
    for limitation in report.limitations or []:
        cause = f"  ({limitation.cause})" if limitation.cause else ""
        lines.append(f"  - {limitation.description}{cause}")
    if not report.limitations:
        lines.append("  - none recorded")
    lines.append(RULE)

    return "\n".join(lines)


def to_dict(report: FinalReport) -> dict[str, object]:
    """The JSON shape the API and the frontend consume (Phases 19 and 21)."""
    return report.model_dump(mode="json")
