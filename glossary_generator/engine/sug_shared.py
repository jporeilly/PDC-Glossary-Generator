"""Shared constants for the suggester role modules (carved 1.38.18).

SENS_RANK/RANK_SENS moved here from the GENERATE section: they were the
single edge that made suggest->generate->links->suggest a cycle."""
DOMAIN = "General"
GEN_TS = "2026-06-18T12:00:00.000Z"
SENS_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
RANK_SENS = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}
