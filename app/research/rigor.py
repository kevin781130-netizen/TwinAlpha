import numpy as np


class ResearchRigor:
    def __init__(self, min_samples: int = 30):
        self.min_samples = min_samples
        self.test_ledger: list[dict] = []

    def permutation_test(self, factor_values, forward_returns,
                         n_permutations=1000, alternative="two-sided") -> dict:
        valid = ~(np.isnan(factor_values) | np.isnan(forward_returns))
        f = factor_values[valid]
        r = forward_returns[valid]

        n = len(f)
        if n < self.min_samples:
            return {"test": "permutation", "status": "INSUFFICIENT_SAMPLES",
                    "n": n, "min_required": self.min_samples}

        from scipy.stats import spearmanr
        actual_ic, _ = spearmanr(f, r)

        perm_ics = np.zeros(n_permutations)
        for i in range(n_permutations):
            perm_r = np.random.permutation(r)
            perm_ic, _ = spearmanr(f, perm_r)
            perm_ics[i] = perm_ic

        if alternative == "two-sided":
            p_value = np.mean(np.abs(perm_ics) >= np.abs(actual_ic))
        elif alternative == "greater":
            p_value = np.mean(perm_ics >= actual_ic)
        else:
            p_value = np.mean(perm_ics <= actual_ic)

        result = {
            "test": "permutation",
            "actual_ic": round(float(actual_ic), 6),
            "perm_mean": round(float(np.mean(perm_ics)), 6),
            "perm_std": round(float(np.std(perm_ics)), 6),
            "p_value": round(float(p_value), 6),
            "n_samples": n, "n_permutations": n_permutations,
            "significant": bool(p_value < 0.05),
        }
        self.test_ledger.append(result)
        return result

    def multiple_testing_correction(self, method: str = "bh") -> dict:
        if not self.test_ledger:
            return {"error": "no tests in ledger"}

        p_values = [t["p_value"] for t in self.test_ledger if "p_value" in t]
        n_tests = len(p_values)
        if n_tests == 0:
            return {"error": "no valid p-values"}

        if method == "bonferroni":
            corrected = [min(p * n_tests, 1.0) for p in p_values]
        elif method == "bh":
            sorted_idx = np.argsort(p_values)
            sorted_p = np.array(p_values)[sorted_idx]
            corrected_sorted = sorted_p * n_tests / (np.arange(n_tests) + 1)
            corrected_sorted = np.minimum.accumulate(corrected_sorted[::-1])[::-1]
            corrected = np.zeros(n_tests)
            corrected[sorted_idx] = corrected_sorted
        else:
            corrected = p_values

        results = []
        for i, t in enumerate(self.test_ledger):
            if "p_value" not in t:
                continue
            results.append({
                "factor": t.get("factor", f"test_{i}"),
                "raw_p": t["p_value"],
                "corrected_p": round(float(corrected[i]), 6),
                "significant_after_correction": bool(corrected[i] < 0.05),
            })

        return {"method": method, "n_tests": n_tests, "results": results,
                "bonferroni_threshold": 0.05 / n_tests}

    def full_report(self, factor_name, factor_values, forward_returns) -> dict:
        perm = self.permutation_test(factor_values, forward_returns)
        correction = self.multiple_testing_correction()
        return {
            "factor": factor_name,
            "permutation_test": perm,
            "multiple_testing": correction,
            "verdict": "SIGNIFICANT" if perm.get("significant") else "NOT_SIGNIFICANT",
        }
