"""Shared constants for the suggester role modules (carved 1.38.18).

SENS_RANK/RANK_SENS moved here from the GENERATE section: they were the
single edge that made suggest->generate->links->suggest a cycle."""
import re as _re

DOMAIN = "General"
GEN_TS = "2026-06-18T12:00:00.000Z"
SENS_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
RANK_SENS = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}

# Units are CLASS knowledge (ppm means parts-per-million in any estate) —
# recognising a unit-bearing measure name is not estate hardcoding, the same
# doctrine that allows email/zip shapes. Shared by the nature classifier
# (unit-named bounded measures default to AUTO detection at suggest time)
# and the drafter's recommended-flip star (for rows harvested before that
# default existed). Normalise the name to _tokens before matching.
UNIT_NAME = _re.compile(
    r"\((?:ppm|ppb|ntu|psi|gpm|mg/?l|ug/?l|kwh|%|percent)\)"
    r"|(?:^|_)(?:ph|ppm|ppb|ntu|psi|gpm|kwh|pct|percent)(?:_|$)", _re.I)
