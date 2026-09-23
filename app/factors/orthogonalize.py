import numpy as np
import pandas as pd


class FactorOrthogonalizer:
    @staticmethod
    def symmetric(factors: pd.DataFrame) -> pd.DataFrame:
        X = factors.dropna()
        if X.empty or len(X) < 3:
            return factors

        X_std = (X - X.mean()) / (X.std() + 1e-9)
        cov = np.cov(X_std.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        idx = eigenvalues.argsort()[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        D_inv_sqrt = np.diag(1.0 / np.sqrt(np.abs(eigenvalues) + 1e-9))
        S = eigenvectors @ D_inv_sqrt @ eigenvectors.T

        result = X_std.values @ S
        return pd.DataFrame(result, index=X_std.index, columns=factors.columns)

    @staticmethod
    def gram_schmidt(factors: pd.DataFrame, base_col: str | None = None) -> pd.DataFrame:
        X = factors.dropna()
        if X.empty:
            return factors

        cols = list(X.columns)
        if base_col and base_col in cols:
            cols.remove(base_col)
            cols = [base_col] + cols

        X_std = (X[cols] - X[cols].mean()) / (X[cols].std() + 1e-9)
        result = pd.DataFrame(index=X_std.index, columns=cols, dtype=float)

        for i, col in enumerate(cols):
            v = X_std[col].values.copy()
            for j in range(i):
                prev = result[cols[j]].values
                proj = (v @ prev) / (prev @ prev + 1e-9)
                v = v - proj * prev
            result[col] = v
        return result

    @staticmethod
    def pca(factors: pd.DataFrame, n_components: int | None = None) -> pd.DataFrame:
        X = factors.dropna()
        if X.empty:
            return factors

        X_std = (X - X.mean()) / (X.std() + 1e-9)
        cov = np.cov(X_std.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        idx = eigenvalues.argsort()[::-1]
        eigenvectors = eigenvectors[:, idx]

        if n_components is None:
            n_components = len(factors.columns)
        n_components = min(n_components, len(eigenvectors.T))
        components = eigenvectors[:, :n_components]
        result = X_std.values @ components

        cols = [f"PC{i + 1}" for i in range(n_components)]
        return pd.DataFrame(result, index=X_std.index, columns=cols)
