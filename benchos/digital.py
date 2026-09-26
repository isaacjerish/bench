"""Attach declared locations to raw digital evidence; never infer continuity."""

from itertools import combinations


def describe_capture(raw: dict, declared: dict) -> dict:
    taps = {}
    for name, reading in raw["taps"].items():
        location = declared.get(name, {})
        connected = location.get("state") == "connected"
        taps[name] = {**reading, "declared_state": location.get("state", "undeclared"),
                      "usable_for_diagnosis": connected,
                      "declared_net": location.get("net") if connected else None,
                      "endpoint": location.get("endpoint") if connected else None}
    comparisons = []
    for (a, first), (b, second) in combinations(declared.items(), 2):
        if first.get("net") != second.get("net"):
            continue
        item = {"net": first["net"], "taps": [a, b], "continuity_verified": False}
        if any(name not in taps or not taps[name]["usable_for_diagnosis"] for name in (a, b)):
            item.update(assessment="unverified", detail="Both endpoints need confirmed tap connections and a capture.")
        elif first.get("endpoint") == second.get("endpoint"):
            item.update(assessment="unverified", detail="Both declarations identify the same endpoint.")
        else:
            active = [taps[name]["edges"] > 0 for name in (a, b)]
            if all(active):
                item.update(assessment="activity_at_both", detail="Both endpoints showed transitions; counts do not prove delivery of the same data or continuity.")
            elif any(active):
                item.update(assessment="activity_mismatch", detail="Only one endpoint showed transitions. Check the connecting wire and both sense branches, then repeat; capture can miss edges.")
            else:
                item.update(assessment="static", detail="No transitions observed at either endpoint. Idle traffic, a held line, or missed activity remain possible.")
        comparisons.append(item)
    expectations = []
    for name, location in declared.items():
        maximum = location.get("max_transitions_per_s")
        if maximum is None:
            continue
        item = {"tap": name, "net": location["net"], "max_transitions_per_s": maximum,
                "scope": "Upper bound on observed transitions only; does not prove the load works."}
        if name not in taps or not taps[name]["usable_for_diagnosis"] or not raw.get("window_ms"):
            item.update(state="unverified", detail="No usable capture for this declared input.")
        else:
            rate = taps[name]["edges"] * 1000 / raw["window_ms"]
            item.update(state="pass" if rate <= maximum else "fail",
                        observed_transitions_per_s=round(rate, 2),
                        detail=f"Observed approximately {rate:.2f} transitions/s; declared upper bound {maximum:g}/s. Check the signal and sense branch if exceeded.")
        expectations.append(item)
    return {**raw, "taps": taps, "comparisons": comparisons, "expectations": expectations,
            "wiring_source": "user_declared",
            "continuity_verified": False,
            "limitations": "Approximate interrupt counts with overlapping windows and small start/stop skew; no waveform, edge correlation, or protocol decode."}
