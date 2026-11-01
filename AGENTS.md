# Strategy research packages

Use C:/Users/lepoc/.codex/skills/karpathy-guidelines/SKILL.md for code. Read the target framework's AGENTS.md and docs/STRATEGY_TEMPLATE.md in ../trader-mayne-framework; follow its risk and review boundaries. The template explicitly requires subagent specification review.

Each pack is independent: packs/<slug>/user_data/strategies/<Class>.py, packs/<slug>/tests/test_<slug>.py, packs/<slug>/docs/STRATEGY.md, TESTING.md, VALIDATION.md. Write the complete Chinese specification BEFORE implementation. Copy the matching source research report from the parent project to docs/RESEARCH.md; never include full raw third-party subtitles. Evidence labels: verified fact / source opinion / model inference / unknown. Numeric thresholds are unvalidated examples unless specifically proven.

Inherit FrameworkStrategy. Only override populate_indicators, informative methods, populate_entry_trend, populate_exit_trend, take_profit_legs and strategy_exit. Do not change framework risk/configuration, override protected callbacks, place trades, change approved status or touch credentials. Exact allowed pairs BTC/USDT:USDT and ETH/USDT:USDT only. Keep all three research stress scenarios. No short/option code masquerading as supported framework functionality. State all missing features and proxy transformations.

Specs must define causal timing, closed data, absolute stop, executable exit hooks, required data/timeframes, cost and execution limitations, parameter table, falsification and install/test steps. Test meaningful positive/negative signals, future perturbation/prefix stability, missing data, precision/edge cases and inherited callback identity. Use actual freqtrade 2026.9 from ../trader-mayne-framework/.venv/Scripts/python.exe, not fake imports.

No market profitability or full G0 claim from unit tests. Each pack's initial research idea key is its slug; actual target registry id is generated on installation before backtesting; never invent a registered id. Do not overwrite research/ideas.jsonl. Do not modify another agent's pack. Root integration owns shared files, manifests, remote publishing, archives and installer.
