"""Full offline top-k evaluation and an uncached inference benchmark."""

from time import perf_counter

import numpy as np

from .recommender import candidate_positions


QUALITY_METRICS = ("precision_at_5", "recall_at_5", "hit_rate_at_5", "ndcg_at_5")
K = 5
DISCOUNTS = 1.0 / np.log2(np.arange(2, K + 2))


def ranking_metrics(predictions, relevant):
    hits = [row in relevant for row in predictions]
    hit_count = sum(hits)
    dcg = sum(discount for hit, discount in zip(hits, DISCOUNTS) if hit)
    ideal_dcg = DISCOUNTS[:min(len(relevant), K)].sum()
    return (
        hit_count / K,
        hit_count / len(relevant),
        float(hit_count > 0),
        dcg / ideal_dcg,
    )


def timing_summary(durations):
    times_ms = np.asarray(durations) * 1000
    return {
        "mean_inference_ms": float(times_ms.mean()),
        "p95_inference_ms": float(np.percentile(times_ms, 95)),
    }


def benchmark(recommender, users_by_seed, limit=200):
    cases = [case for users in users_by_seed.values() for case in users]
    sampled_indices = np.random.default_rng(42).choice(
        len(cases), size=min(limit, len(cases)), replace=False
    )
    timings = {"knn": [], "popularity": []}
    popularity = recommender.popularity_order

    for index in sampled_indices:
        case = cases[index]
        excluded = set(case.seen_rows)

        start = perf_counter()
        rows, _ = recommender.rank(case.seed_row)
        candidate_positions(rows, excluded, K)
        timings["knn"].append(perf_counter() - start)

        start = perf_counter()
        candidate_positions(popularity, excluded, K)
        timings["popularity"].append(perf_counter() - start)

    return len(sampled_indices), {name: timing_summary(times) for name, times in timings.items()}


def evaluate(recommender, users_by_seed):
    evaluated_users = sum(map(len, users_by_seed.values()))
    if not evaluated_users:
        raise ValueError("No users have a relevant movie in both chronological splits.")

    totals = {"knn": np.zeros(len(QUALITY_METRICS)), "popularity": np.zeros(len(QUALITY_METRICS))}
    popularity = recommender.popularity_order

    # Rank each distinct seed once, then exclude the early history separately for each user.
    for seed, cases in users_by_seed.items():
        neighbors, _ = recommender.rank(seed)
        for case in cases:
            excluded = set(case.seen_rows)
            neighbors_top = neighbors[candidate_positions(neighbors, excluded, K)]
            popularity_top = popularity[candidate_positions(popularity, excluded, K)]
            totals["knn"] += ranking_metrics(neighbors_top, case.relevant_rows)
            totals["popularity"] += ranking_metrics(popularity_top, case.relevant_rows)

    timing_requests, timings = benchmark(recommender, users_by_seed)
    return {
        "evaluated_users": evaluated_users,
        "distinct_seed_movies": len(users_by_seed),
        "timing_requests_per_method": timing_requests,
        "metrics": {
            name: {
                **dict(zip(QUALITY_METRICS, scores / evaluated_users)),
                **timings[name],
            }
            for name, scores in totals.items()
        },
    }
