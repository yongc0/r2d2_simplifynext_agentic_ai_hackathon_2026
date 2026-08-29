"""The three-arm evaluation.

    uv run -m eval.run_arms      Spark vs random vs naive interest-similarity
    uv run -m eval.report        the metric tables for the slides

docs/ARCHITECTURE.md §19. Two things about this harness are load-bearing:

**All three arms share one eligibility filter and one simulated world.** The
arms differ by a single field of `SparkRuntime`. If they disagreed about who is
*allowed* to be matched, the comparison would measure the filter rather than the
matcher.

**The comparison is pre-registered.** CLAUDE.md: *if the Match Agent does not
beat random assignment on mutual connect rate, we report it.* The report prints
whichever answer the numbers give, with a significance test, and says plainly
when a difference is not distinguishable from noise.
"""
