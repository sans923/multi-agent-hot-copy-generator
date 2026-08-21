"""无模型副作用的记忆检索离线评测：相关性与租户隔离同时计分。"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


def _dcg(relevance: list[int]) -> float:
    return sum(
        value / math.log2(index + 2)
        for index, value in enumerate(relevance)
    )


def evaluate_retrieval(
    cases: Iterable[Mapping[str, Any]],
    *,
    k: int = 5,
) -> dict[str, Any]:
    """计算宏平均 Recall@K、MRR、nDCG@K，并把跨租户结果单独判为失败。"""
    if k < 1:
        raise ValueError("k 必须大于等于 1")
    case_list = list(cases)
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    leaks = 0
    details: list[dict[str, Any]] = []

    for case in case_list:
        relevant = {int(item) for item in case.get("relevant_ids", [])}
        retrieved = [int(item) for item in case.get("retrieved_ids", [])[:k]]
        hits = [1 if item in relevant else 0 for item in retrieved]
        recall = len(relevant.intersection(retrieved)) / len(relevant) if relevant else 1.0
        first_hit = next((index for index, hit in enumerate(hits, start=1) if hit), None)
        reciprocal_rank = 1.0 / first_hit if first_hit else 0.0
        ideal = [1] * min(len(relevant), k)
        ideal_dcg = _dcg(ideal)
        ndcg = _dcg(hits) / ideal_dcg if ideal_dcg else 1.0

        expected_user_id = case.get("expected_user_id")
        user_ids = list(case.get("retrieved_user_ids", []))[:k]
        case_leaks = sum(user_id != expected_user_id for user_id in user_ids)
        leaks += case_leaks
        recalls.append(recall)
        reciprocal_ranks.append(reciprocal_rank)
        ndcgs.append(ndcg)
        details.append({
            "case_id": str(case.get("case_id", "")),
            "recall_at_k": round(recall, 4),
            "reciprocal_rank": round(reciprocal_rank, 4),
            "ndcg_at_k": round(ndcg, 4),
            "cross_tenant_leaks": case_leaks,
        })

    count = len(case_list)
    mean = lambda values: round(sum(values) / count, 4) if count else None
    return {
        "cases": count,
        "k": k,
        "recall_at_k": mean(recalls),
        "mrr": mean(reciprocal_ranks),
        "ndcg_at_k": mean(ndcgs),
        "cross_tenant_leaks": leaks,
        "tenant_isolation_passed": leaks == 0,
        "details": details,
    }
