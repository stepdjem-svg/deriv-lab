import random
import unittest

from lab import judge


class JudgeMathTests(unittest.TestCase):
    def test_bar_matches_tests_log_convention(self):
        self.assertAlmostEqual(judge.z_threshold(1), 1.96, places=2)
        self.assertAlmostEqual(judge.z_threshold(4), 2.50, places=2)  # the "4 tests -> 2.50" rule
        self.assertGreater(judge.z_threshold(20), judge.z_threshold(4))

    def test_break_even_and_ev(self):
        self.assertAlmostEqual(judge.break_even(1.0, 1.9), 0.5263, places=3)
        p0 = judge.break_even(1.0, 1.9)
        self.assertAlmostEqual(judge.ev_per_stake(p0, p0), 0.0, places=9)
        self.assertLess(judge.ev_per_stake(0.5, p0), 0)

    def test_required_trades_order_of_magnitude(self):
        n3 = judge.required_trades(0.526, 0.03)
        n5 = judge.required_trades(0.526, 0.05)
        # one-sided 5% test, 80% power: about 1,700 trades for a 3-point edge (about 2,100 with a two-sided test)
        self.assertTrue(1500 <= n3 <= 2300, n3)
        self.assertTrue(550 <= n5 <= 900, n5)
        self.assertGreater(n3, n5)

    def test_drawdown(self):
        self.assertEqual(judge.max_drawdown([1, 1, -1, -1, -1, 2]), 3)
        self.assertEqual(judge.max_drawdown([1, 1, 1]), 0)

    def test_lucky_small_sample_is_not_a_candidate(self):
        r = judge.evaluate(wins=22, n=30, p0=0.526, n_tests=4)  # 73% on 30 trades
        self.assertNotEqual(r["verdict"], "candidate")
        self.assertEqual(r["verdict"], "inconclusive")
        self.assertNotIn("profitable", str(r))

    def test_missing_control_or_oos_blocks_candidate(self):
        r = judge.evaluate(wins=430, n=700, p0=0.526, n_tests=1)  # 61%: great number, no control, no oos
        self.assertNotEqual(r["verdict"], "candidate")


class JudgeSimulationTests(unittest.TestCase):
    """The judge itself is tested: it must reject pure noise and detect a planted edge."""

    def run_sims(self, true_rate, runs=1500, n=700, p0=0.526, n_tests=4):
        rng = random.Random(7)
        hits = 0
        for _ in range(runs):
            w = sum(rng.random() < true_rate for _ in range(n))
            c = sum(rng.random() < 0.5 for _ in range(n))
            oos = sum(rng.random() < true_rate for _ in range(300))
            r = judge.evaluate(w, n, p0, n_tests, control=(c, n), out_of_sample=(oos, 300), edge_of_interest=0.06)
            hits += r["verdict"] == "candidate"
        return hits / runs

    def test_pure_noise_is_almost_never_a_candidate(self):
        self.assertLess(self.run_sims(true_rate=0.526), 0.02)  # even exactly at break-even
        self.assertLess(self.run_sims(true_rate=0.50), 0.005)  # a real coin flip

    def test_planted_edge_is_found(self):
        self.assertGreater(self.run_sims(true_rate=0.62), 0.80)


if __name__ == "__main__":
    unittest.main()
