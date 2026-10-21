"""Optional local timings and counters; never add performance data to model context."""

from contextlib import contextmanager
from time import perf_counter


@contextmanager
def measure(metrics, name):
    """Accumulate inclusive stage time; nesting the same stage counts only once.

    Different stages may overlap (verification occurs within search/package), so
    stage values must not be summed to claim end-to-end latency.
    """
    if metrics is None:
        yield
        return
    active = metrics.setdefault("_active_stages", set())
    outer = name not in active
    if outer:
        active.add(name)
    started = perf_counter()
    try:
        yield
    finally:
        if outer:
            stages = metrics.setdefault("stages_ms", {})
            stages[name] = stages.get(name, 0.0) + (perf_counter() - started) * 1000
            active.remove(name)
        if not active:
            metrics.pop("_active_stages", None)


def count(metrics, name, amount=1):
    if metrics is not None:
        counters = metrics.setdefault("counts", {})
        counters[name] = counters.get(name, 0) + amount
