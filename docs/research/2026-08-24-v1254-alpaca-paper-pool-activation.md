# v1254 Alpaca Paper pool activation

## Outcome

The user authorized `lev-v1254-de6c18bd7658f359` for Alpaca Paper observation on 2026-08-24.
The account-level pool now allocates 25% each to v247, v449, v798 and v1254, with the existing 0.99
cash-only gross buffer. The route remains locked to `https://paper-api.alpaca.markets`; no
real-money route was added.

The already-running 2026-08-24 three-member session was not restarted or reconfigured. v1254 first
becomes eligible in the entry runner on 2026-08-25. The new four-member closeout task is eligible at
03:45:45 on 2026-08-25 and can safeguard any positions opened by the 2026-08-24 runner.

## 2026-08-24 execution status

As of 2026-08-24 21:15 Asia/Shanghai:

- the three-member entry task had started at 20:00 and remained running;
- its future schedule was disabled without terminating the active process;
- the append-only ledger contained one `ACCOUNT_BOUNDARY` startup event at 20:00:06;
- Alpaca Paper reported zero positions and zero open orders;
- the market was still closed and the first strategy decision window was later in the session.

Therefore the executor did run, but it had not emitted a signal or submitted an order at the
observation cutoff.

## v1254 execution parity

v1254 uses a prior-close four-factor state consisting of sector breadth, risk-asset agreement,
inverse sector dispersion and inverse SPY volatility. When the score is below the frozen threshold,
the strategy keeps 100% of its allocation in v45. When allowed, it substitutes 16% of v45 with the
frozen v449/v60 component.

The Paper-frame calculation was compared with the research cube for the five latest comparable
sessions from 2026-08-06 through 2026-08-12. Every absolute error was at most `1.11e-16`.

## Scheduler state

- New entry task: `USIntradayLab-V247-V449-V798-V1254-AlpacaPaperPool`, next run 2026-08-25 20:00.
- New closeout task: `USIntradayLab-V247-V449-V798-V1254-AlpacaPaperPool-Closeout`, next run
  2026-08-25 03:45:45.
- The old three-member entry task remains alive only for its in-progress 2026-08-24 session and has
  no future trigger.
- The old three-member closeout task is disabled rather than deleted.

All prior Paper ledger rows and candidate failure labels remain unchanged.
