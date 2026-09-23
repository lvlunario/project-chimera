from contextlib import redirect_stdout
from decimal import Decimal, localcontext
from hashlib import sha256
import io
import json
import subprocess
import sys
import unittest

from chimera import (FaultError, FaultPlan, TelemetryError, evaluate_link_margin,
                     fault_manifest, inject_link_csv, parse_link_csv)


SOURCE = (b"timestamp_utc,link_margin_db\n"
          b"2026-09-22T00:00:00Z,4.0\n2026-09-22T00:00:01Z,3.0\n")


def plan(items=()):
    return FaultPlan.from_json(json.dumps({
        "schema_version": 1, "model": "sample-replacement-v1", "replacements": list(items)
    }))


class FaultTests(unittest.TestCase):
    def test_exact_repeatable_vector_preserves_source(self):
        config = plan([{"sample_index": 2, "link_margin_db": "2.0"}])
        expected = SOURCE.replace(b"01Z,3.0", b"01Z,2.0")
        self.assertEqual(expected, inject_link_csv(SOURCE, config))
        self.assertEqual(expected, inject_link_csv(SOURCE, FaultPlan(config.to_json())))
        self.assertIn(b"01Z,3.0", SOURCE)
        self.assertEqual(sha256(config.to_json().encode()).hexdigest(), config.sha256)
        report = evaluate_link_margin(parse_link_csv(expected), 3)
        self.assertEqual([{"sample_index": 2, "timestamp_utc": "2026-09-22T00:00:01Z",
                           "link_margin_db": "2.0"}], report.to_dict()["failing_samples"])

    def test_order_is_canonical_and_views_are_detached(self):
        items = [{"sample_index": 2, "link_margin_db": "2"},
                 {"sample_index": 1, "link_margin_db": "1"}]
        left, right = plan(items), plan(reversed(items))
        self.assertEqual(left, right)
        left.to_dict()["replacements"].clear()
        self.assertEqual(2, len(left.to_dict()["replacements"]))
        self.assertNotEqual(left.sha256, plan().sha256)

    def test_no_fault_control_and_canonical_csv_formatting(self):
        self.assertEqual(SOURCE, inject_link_csv(SOURCE, plan()))
        self.assertEqual(SOURCE, inject_link_csv(SOURCE.replace(b"\n", b"\r\n"), plan()))
        self.assertTrue(evaluate_link_margin(parse_link_csv(inject_link_csv(SOURCE, plan())), 3).passed)

    def test_replacement_is_exact_independent_of_decimal_context(self):
        value = "2.999999999999999999999999999999999999"
        config = plan([{"sample_index": 2, "link_margin_db": value}])
        with localcontext() as context:
            context.prec = 2
            derived = inject_link_csv(SOURCE, config)
        self.assertIn(value.encode(), derived)
        self.assertFalse(evaluate_link_margin(parse_link_csv(derived), Decimal("3")).passed)

    def test_manifest_source_plan_output_identity_and_detachment(self):
        config = plan([{"sample_index": 2, "link_margin_db": "2"}])
        manifest = fault_manifest(SOURCE, config)
        self.assertIs(manifest["synthetic"], True)
        self.assertEqual(sha256(SOURCE).hexdigest(), manifest["source"]["input_sha256"])
        self.assertEqual(config.sha256, manifest["fault_plan_sha256"])
        self.assertEqual(config.to_dict(), manifest["fault_plan"])
        self.assertEqual(sha256(inject_link_csv(SOURCE, config)).hexdigest(),
                         manifest["derived"]["input_sha256"])
        manifest["fault_plan"]["replacements"].clear()
        self.assertEqual(1, len(config.to_dict()["replacements"]))

    def test_invalid_plan_shapes_versions_and_duplicate_keys(self):
        documents = [None, [], {}, {"schema_version": True, "model": "sample-replacement-v1", "replacements": []},
                     {"schema_version": 2, "model": "sample-replacement-v1", "replacements": []},
                     {"schema_version": 1, "model": "arbitrary-code", "replacements": []},
                     {"schema_version": 1, "model": "sample-replacement-v1", "replacements": {}, "extra": 1}]
        for document in documents:
            with self.subTest(document), self.assertRaises(FaultError):
                FaultPlan(json.dumps(document))
        for text in (None, b"{}", "{", "\ud800", '{"schema_version":1,"schema_version":1}', "[" * 2000):
            with self.subTest(repr(text)), self.assertRaises(FaultError):
                FaultPlan(text)

    def test_invalid_replacement_indices_values_and_fields(self):
        for index in (True, 0, -1, 10001, 1.0, "1"):
            with self.subTest(index), self.assertRaises(FaultError):
                plan([{"sample_index": index, "link_margin_db": "2"}])
        for value in (None, 2, True, "NaN", "Inf", " 2", "2 ", "١", "1_000", "9" * 129):
            with self.subTest(value), self.assertRaises(FaultError):
                plan([{"sample_index": 1, "link_margin_db": value}])
        for items in ([{}], [None], [{"sample_index": 1, "link_margin_db": "2", "extra": 1}],
                      [{"sample_index": 1, "link_margin_db": "2"}] * 2):
            with self.subTest(items), self.assertRaises(FaultError):
                plan(items)

    def test_plan_byte_and_replacement_bounds(self):
        with self.assertRaises(FaultError):
            FaultPlan(" " * 65537)
        with self.assertRaises(FaultError):
            plan([{"sample_index": i + 1, "link_margin_db": "2"} for i in range(1001)])
        bounded = plan([{"sample_index": i + 1, "link_margin_db": "2"} for i in range(1000)])
        self.assertEqual(1000, len(bounded.to_dict()["replacements"]))

    def test_source_invalid_out_of_range_and_changed_identity(self):
        with self.assertRaises(FaultError):
            inject_link_csv(SOURCE, plan([{"sample_index": 3, "link_margin_db": "2"}]))
        with self.assertRaises(FaultError):
            inject_link_csv(SOURCE, {})
        for source in (b"", b"bad", SOURCE.replace(b"4.0", b"NaN"), "not bytes", b"x" * 1048577):
            with self.subTest(type(source)), self.assertRaises(TelemetryError):
                inject_link_csv(source, plan())
        with self.assertRaisesRegex(TelemetryError, "identity changed"):
            inject_link_csv(SOURCE, plan(), expected_sha256="0" * 64)

    def test_demo_durable_handoff_and_optimized_mode(self):
        from examples.fault_demo import main
        output = io.StringIO()
        with redirect_stdout(output):
            main()
        self.assertIn("COM-LINK-001 FAIL", output.getvalue())
        result = subprocess.run([sys.executable, "-O", "-m", "examples.fault_demo"],
                                capture_output=True, text=True, check=True)
        self.assertIn("reopen invokes none", result.stdout)


if __name__ == "__main__":
    unittest.main()
