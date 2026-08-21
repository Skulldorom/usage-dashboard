"""Analytics engine for provider usage snapshots.

Treats ``UsageSnapshot`` rows as observations of provider state and derives
historical analytics (trends, peaks, comparisons, pacing, forecasts) from a
normalized observation layer. The normalization/aggregation logic is kept free
of SQLAlchemy and FastAPI imports so it can be unit-tested in isolation.
"""
