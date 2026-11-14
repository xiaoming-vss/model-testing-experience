"""The semantic release gate cannot pass incomplete or model-only judgments."""
import unittest

from scripts.evaluate_case_visualization import evaluate


class VisualizationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.samples = [{"id": str(i)} for i in range(50)]
        self.reviews = [{"id": str(i), "reviewer": "human-reviewer", "suitable": i < 40,
                         "usable": i < 32, "severeErrorCount": 0,
                         "evidence": "saved-output.json: checked frozen expected text"}
                        for i in range(50)]

    def test_exact_threshold_passes(self):
        report = evaluate(self.samples, self.reviews)
        self.assertTrue(report["passed"])
        self.assertEqual(report["effectiveCoverage"], 0.8)

    def test_missing_reviews_cannot_pass(self):
        self.assertFalse(evaluate(self.samples, [])['passed'])
        self.assertFalse(evaluate(self.samples, self.reviews[:-1])['passed'])

    def test_serious_error_on_unsuitable_sample_blocks_release(self):
        self.reviews[-1]['severeErrorCount'] = 1
        self.assertFalse(evaluate(self.samples, self.reviews)['passed'])

    def test_no_suitable_samples_is_not_full_coverage(self):
        for review in self.reviews:
            review['suitable'] = False
        self.assertFalse(evaluate(self.samples, self.reviews)['passed'])

    def test_without_human_reviewer_rejected(self):
        self.reviews[0]['reviewer'] = ''
        with self.assertRaises(ValueError):
            evaluate(self.samples, self.reviews)
