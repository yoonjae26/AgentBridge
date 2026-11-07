# Claude pilot run (real data, n = 1)

`agentbridge benchmark run bugfix-002 -c claude-single -c claude-multi` on 2026-11-07
(UTC), Claude Code 2.1.303 on a Pro subscription, Windows 11.

| | claude-single | claude-multi |
|---|---:|---:|
| Hidden tests passed | 5/5 | 5/5 |
| Wall time (s) | 14.9 | 74.7 |
| Estimated cost (USD, CLI estimate) | 0.37 | 0.75 |
| Input / output tokens | 227,093 / 1,214 | 473,102 / 4,717 |

One easy task, one repetition. Both configurations solved it; the multi-agent workflow
took about 5x longer and about 2x the estimated cost. This is a pilot that exercises
the pipeline end to end — **not** evidence about multi- vs single-agent performance.
