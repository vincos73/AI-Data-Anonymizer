from __future__ import annotations

import unittest

from privacy_guardian.models import Finding
from scripts.evaluate_multisector_corpus import expected_value_status


class MultisectorCorpusEvaluatorTest(unittest.TestCase):
    def test_repeated_value_may_be_covered_by_more_than_one_sensitive_type(self) -> None:
        text = "Bologna\nResidenza: Via Bologna 3"
        findings = [
            Finding("LOCATION", 0, 7, 0.9),
            Finding("ADDRESS", 19, len(text), 0.9),
        ]

        self.assertEqual(
            expected_value_status(text, findings, "Bologna", "LOCATION"),
            "detected",
        )

    def test_partial_coverage_is_reported_as_a_leak(self) -> None:
        text = "Fascicolo RG 4567/2026"
        start = text.index("RG 4567/2026")
        findings = [Finding("ADDRESS", start, start + 2, 0.8)]

        self.assertEqual(
            expected_value_status(
                text,
                findings,
                "RG 4567/2026",
                "PROTOCOL_CASE_NUMBER",
            ),
            "leaked",
        )

    def test_terminal_organization_period_may_remain_outside_span(self) -> None:
        text = "Rete Sicura S.p.A."
        findings = [Finding("ORGANIZATION", 0, len(text) - 1, 0.9)]

        self.assertEqual(
            expected_value_status(text, findings, text, "ORGANIZATION"),
            "detected",
        )


if __name__ == "__main__":
    unittest.main()
