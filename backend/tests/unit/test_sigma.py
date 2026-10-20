"""Phase B5: Sigma detections as ATT&CK mapping rules, and the subset refused outside it."""

from __future__ import annotations

import re

import pytest

from app.cyber import sigma
from app.cyber.attack import get_rules

RULE = {
    "title": "Certutil download",
    "tags": ["attack.command_and_control", "attack.t1105"],
    "detection": {
        "selection_image": {"Image|endswith": "\\certutil.exe"},
        "selection_cmd": {"CommandLine|contains": ["-urlcache", "-verifyctl"]},
        "condition": "selection_image and selection_cmd",
    },
}


def test_a_sigma_rule_becomes_one_mapping_rule_per_technique() -> None:
    [rule] = sigma.convert(RULE)
    assert rule["technique"] == "T1105" and rule["why"] == "Sigma: Certutil download"
    image, cmd = rule["all"]
    assert image["field"] == "image" and re.search(image["regex"], r"C:\Windows\certutil.exe")
    assert cmd["field"] == "cmd" and re.search(cmd["regex"], "certutil -urlcache -f http://x")


def test_or_makes_two_rules_and_exact_values_are_anchored() -> None:
    rule = {
        "tags": ["attack.t1021.001"],
        "detection": {"a": {"EventID": 4624}, "b": {"LogonType": 10}, "condition": "a or b"},
    }
    rules = sigma.convert(rule)
    assert len(rules) == 2 and rules[0]["all"] == [{"field": "event", "regex": "^4624$"}]


@pytest.mark.parametrize(
    "detection",
    [
        {"s": {"Image": "x"}, "condition": "not s"},
        {"s": {"Image|re": "x"}, "condition": "s"},
        {"s": {"Hashes": "x"}, "condition": "s"},
        {"s": {"Image": "x"}, "condition": "1 of s*"},
    ],
)
def test_constructs_outside_the_subset_are_refused(detection: dict[str, object]) -> None:
    with pytest.raises(sigma.Unsupported):
        sigma.convert({"tags": ["attack.t1105"], "detection": detection})


def test_the_shipped_sigma_rules_load_with_the_others() -> None:
    sigma_rules = [r for r in get_rules() if r.why.startswith("Sigma:")]
    assert {r.technique for r in sigma_rules} >= {"T1105", "T1053.005", "T1021.001", "T1218.005"}
