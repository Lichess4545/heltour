"""
TRF16 (FIDE Tournament Report Format) writer/serializer.

Accepts TRF16Header, Dict[int, TRF16Player], Dict[str, TRF16Team]
and produces a TRF16 format string that round-trips through TRF16Parser.
"""

from typing import Dict, List, Optional, Tuple

from heltour.tournament_core.trf16 import TRF16Header, TRF16Player, TRF16Team

# Parser requires lines >= 90 chars
_MIN_PLAYER_LINE_LEN = 90


def write_trf16(
    header: TRF16Header,
    players: Dict[int, TRF16Player],
    teams: Optional[Dict[str, TRF16Team]] = None,
) -> str:
    lines: List[str] = []
    _write_header(lines, header)
    _write_players(lines, players)
    if teams:
        _write_teams(lines, teams)
    return "\n".join(lines)


def _write_header(lines: List[str], h: TRF16Header) -> None:
    lines.append(f"012 {h.tournament_name}")
    lines.append(f"022 {h.city}")
    lines.append(f"032 {h.federation}")
    lines.append(f"042 {_format_date(h.start_date)}")
    lines.append(f"052 {_format_date(h.end_date)}")
    lines.append(f"062 {h.num_players} ({h.num_rated_players})")
    lines.append(f"072 {h.num_rated_players}")
    lines.append(f"082 {h.num_teams}")
    lines.append(f"092 {h.tournament_type}")
    lines.append(f"102 {h.chief_arbiter}")
    lines.append(f"112 {', '.join(h.deputy_arbiters)}")
    lines.append(f"122 {h.time_control}")
    lines.append(f"142 {h.num_rounds}")
    if h.round_dates:
        date_strs = "  ".join(_format_short_date(d) for d in h.round_dates)
        lines.append(f"132 {date_strs}")


def _write_players(lines: List[str], players: Dict[int, TRF16Player]) -> None:
    for start_num in sorted(players):
        lines.append(_format_player_line(start_num, players[start_num]))


def _write_teams(lines: List[str], teams: Dict[str, TRF16Team]) -> None:
    for team in teams.values():
        ids_str = "  ".join(f"{pid:4d}" for pid in team.player_ids)
        lines.append(f"013 {team.name}  {ids_str}")


def _format_player_line(start_num: int, p: TRF16Player) -> str:
    # Title: parser always reads parts[2] as title, so must be non-empty
    title = p.title if p.title else "-"
    # Rating: zero-padded to 4 digits so parser detects end-of-name
    rating_str = f"{p.rating:04d}"
    # Federation: must be non-empty token so parser doesn't skip a field
    federation = p.federation if p.federation else "---"
    # FIDE ID: must be non-empty token, right-justified in 11 chars
    fide_id = p.fide_id if p.fide_id else "0"
    fide_padded = f"{fide_id:>11s}"
    # Name: padded wide for readability
    name = p.name if p.name else "Unknown"
    name_padded = f"{name:<33s}"
    # Points: always include decimal so parser detects it
    points_str = f"{p.points:4.1f}"

    # Birth date: always occupy 10 chars (parser detects presence via "/")
    if p.birth_year:
        birth_field = f"{p.birth_year}/01/01"
    else:
        birth_field = ""
    birth_padded = f"{birth_field:>10s}"

    # Start number must be at positions 4-7 for line[4:8] extraction
    # Field widths chosen so base line (before results) exceeds 90 chars,
    # avoiding dependence on trailing-space padding which TRF16Parser.strip() removes.
    line = (
        f"001 {start_num:4d} {title:<2s} {name_padded}"
        f" {rating_str} {federation} {fide_padded} {birth_padded}"
        f" {points_str} {p.rank:4d}"
    )

    for result in p.results:
        line += _format_result_triplet(result)

    return line


def _format_result_triplet(result: Tuple[Optional[int], str, str]) -> str:
    opponent_id, color, res = result
    if opponent_id is None:
        # Byes: must be "0000" for parser's special-case detection
        opp_str = "0000"
    elif opponent_id == 0:
        # Forfeit: "0000" so parser treats as forfeit win/loss
        opp_str = "0000"
    else:
        opp_str = f"{opponent_id:4d}"
    return f"  {opp_str} {color} {res}"


def _format_date(dt) -> str:
    return dt.strftime("%Y/%m/%d")


def _format_short_date(dt) -> str:
    return dt.strftime("%d/%m/%y")
