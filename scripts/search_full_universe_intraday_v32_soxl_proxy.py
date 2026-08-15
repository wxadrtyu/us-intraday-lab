"""SOXL-only proxy search retaining XLK-generated causal signals."""

from __future__ import annotations

import search_full_universe_intraday_v23_beta_residual as v23
import search_full_universe_intraday_v28_proxy_leverage as v28

if __name__ == "__main__":
    v28.PAIRS = ((4, 10),)
    v23.SLOTS = v28.SLOTS
    v23.CUBE_CLASS = v28.Cube
    v23.CANDIDATE_PREFIX = "lev-v32p-"
    v23._specifications = v28._specifications
    v23.main()
