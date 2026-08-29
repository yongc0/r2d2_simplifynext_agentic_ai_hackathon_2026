"""Command-line entry points.

    uv run -m src.cli.encounter --seed 42     one encounter, verbose, with its trace
    uv run -m src.cli.simulate --weeks 6      the full six-week simulation

Both are thin: they assemble a `SparkRuntime` and drive the same graph and the
same engine the evaluation uses. Nothing is demonstrated here that the
evaluation does not also run.
"""
