#!/usr/bin/env python3
"""
Streaming audit for the Online Retail event dataset.

Why this script exists:
- The source CSVs are very large (tens of millions of rows each).
- A standard `pandas.read_csv()` approach can exhaust memory quickly.
- This script scans line by line and produces a compact audit report.
"""

from __future__ import annotations

import csv
import heapq
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


DATA_FILES = [
    Path("2019-Oct.csv"),
    Path("2019-Nov.csv"),
]


class KMVSketch:
    """Approximate distinct counter using k-minimum hash values."""

    def __init__(self, k: int = 4096) -> None:
        self.k = k
        self._heap: List[int] = []
        self._values = set()

    @staticmethod
    def _hash_value(value: str) -> int:
        digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big")

    def add(self, value: str) -> None:
        hashed = self._hash_value(value)
        if hashed in self._values:
            return
        if len(self._heap) < self.k:
            heapq.heappush(self._heap, -hashed)
            self._values.add(hashed)
            return

        current_max = -self._heap[0]
        if hashed >= current_max:
            return

        removed = -heapq.heapreplace(self._heap, -hashed)
        self._values.remove(removed)
        self._values.add(hashed)

    def merge(self, other: "KMVSketch") -> None:
        for hashed in other._values:
            if hashed in self._values:
                continue
            if len(self._heap) < self.k:
                heapq.heappush(self._heap, -hashed)
                self._values.add(hashed)
                continue
            current_max = -self._heap[0]
            if hashed >= current_max:
                continue
            removed = -heapq.heapreplace(self._heap, -hashed)
            self._values.remove(removed)
            self._values.add(hashed)

    def estimate(self) -> int:
        if not self._heap:
            return 0
        if len(self._heap) < self.k:
            return len(self._values)

        kth_smallest = -self._heap[0]
        normalized = kth_smallest / ((1 << 64) - 1)
        if normalized == 0:
            return len(self._values)
        return int((self.k - 1) / normalized)


@dataclass
class FileAudit:
    file_name: str
    row_count: int = 0
    min_event_time: str | None = None
    max_event_time: str | None = None
    event_type_counts: Counter = field(default_factory=Counter)
    missing_counts: Counter = field(default_factory=Counter)
    zero_price_count: int = 0
    negative_price_count: int = 0
    high_price_count: int = 0
    user_sketch: KMVSketch = field(default_factory=KMVSketch)
    session_sketch: KMVSketch = field(default_factory=KMVSketch)
    top_prices: List[Tuple[float, str, str, str]] = field(default_factory=list)

    def register_top_price(
        self, price: float, product_id: str, brand: str, category_code: str
    ) -> None:
        item = (price, product_id, brand or "<missing>", category_code or "<missing>")
        if len(self.top_prices) < 5:
            heapq.heappush(self.top_prices, item)
            return
        if item[0] > self.top_prices[0][0]:
            heapq.heapreplace(self.top_prices, item)


def normalize_value(raw: str | None) -> str:
    if raw is None:
        return ""
    return raw.strip()


def scan_file(path: Path) -> FileAudit:
    audit = FileAudit(file_name=path.name)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            audit.row_count += 1

            event_time = normalize_value(row.get("event_time"))
            if event_time:
                if audit.min_event_time is None or event_time < audit.min_event_time:
                    audit.min_event_time = event_time
                if audit.max_event_time is None or event_time > audit.max_event_time:
                    audit.max_event_time = event_time

            for column, value in row.items():
                if normalize_value(value) == "":
                    audit.missing_counts[column] += 1

            event_type = normalize_value(row.get("event_type"))
            audit.event_type_counts[event_type] += 1

            user_id = normalize_value(row.get("user_id"))
            if user_id:
                audit.user_sketch.add(user_id)

            user_session = normalize_value(row.get("user_session"))
            if user_session:
                audit.session_sketch.add(user_session)

            raw_price = normalize_value(row.get("price"))
            if raw_price:
                price = float(raw_price)
                if price == 0:
                    audit.zero_price_count += 1
                if price < 0:
                    audit.negative_price_count += 1
                if price > 10000:
                    audit.high_price_count += 1
                audit.register_top_price(
                    price=price,
                    product_id=normalize_value(row.get("product_id")),
                    brand=normalize_value(row.get("brand")),
                    category_code=normalize_value(row.get("category_code")),
                )

    return audit


def combine(audits: Iterable[FileAudit]) -> Dict[str, object]:
    audits = list(audits)
    combined_missing = Counter()
    combined_events = Counter()
    min_event_time = None
    max_event_time = None
    total_rows = 0
    total_zero_price = 0
    total_negative_price = 0
    total_high_price = 0
    all_users = KMVSketch()
    all_sessions = KMVSketch()
    top_prices: List[Tuple[float, str, str, str, str]] = []

    for audit in audits:
        total_rows += audit.row_count
        total_zero_price += audit.zero_price_count
        total_negative_price += audit.negative_price_count
        total_high_price += audit.high_price_count
        combined_missing.update(audit.missing_counts)
        combined_events.update(audit.event_type_counts)
        all_users.merge(audit.user_sketch)
        all_sessions.merge(audit.session_sketch)

        if audit.min_event_time and (min_event_time is None or audit.min_event_time < min_event_time):
            min_event_time = audit.min_event_time
        if audit.max_event_time and (max_event_time is None or audit.max_event_time > max_event_time):
            max_event_time = audit.max_event_time

        for price, product_id, brand, category_code in audit.top_prices:
            item = (price, audit.file_name, product_id, brand, category_code)
            if len(top_prices) < 10:
                heapq.heappush(top_prices, item)
                continue
            if item[0] > top_prices[0][0]:
                heapq.heapreplace(top_prices, item)

    return {
        "total_rows": total_rows,
        "min_event_time": min_event_time,
        "max_event_time": max_event_time,
        "event_type_counts": combined_events,
        "missing_counts": combined_missing,
        "zero_price_count": total_zero_price,
        "negative_price_count": total_negative_price,
        "high_price_count": total_high_price,
        "distinct_users": all_users.estimate(),
        "distinct_sessions": all_sessions.estimate(),
        "top_prices": sorted(top_prices, reverse=True),
    }


def percentage(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return (count / total) * 100


def print_file_summary(audit: FileAudit) -> None:
    print(f"\n=== {audit.file_name} ===")
    print(f"Rows: {audit.row_count:,}")
    print(f"Event window: {audit.min_event_time} -> {audit.max_event_time}")
    print(f"Approx. distinct users: {audit.user_sketch.estimate():,}")
    print(f"Approx. distinct sessions: {audit.session_sketch.estimate():,}")
    print("Event mix:")
    for event_type, count in audit.event_type_counts.most_common():
        print(f"  - {event_type}: {count:,} ({percentage(count, audit.row_count):.2f}%)")
    print("Missing values:")
    for column, count in audit.missing_counts.most_common():
        print(f"  - {column}: {count:,} ({percentage(count, audit.row_count):.2f}%)")
    print(
        "Price checks: "
        f"zero={audit.zero_price_count:,}, "
        f"negative={audit.negative_price_count:,}, "
        f">10k={audit.high_price_count:,}"
    )
    print("Top prices:")
    for price, product_id, brand, category_code in sorted(audit.top_prices, reverse=True):
        print(
            f"  - {price:,.2f} | product_id={product_id} | "
            f"brand={brand} | category={category_code}"
        )


def print_combined_summary(summary: Dict[str, object]) -> None:
    total_rows = summary["total_rows"]
    print("\n=== Combined Summary ===")
    print(f"Rows: {total_rows:,}")
    print(f"Event window: {summary['min_event_time']} -> {summary['max_event_time']}")
    print(f"Distinct users across both files: {summary['distinct_users']:,}")
    print(f"Distinct sessions across both files: {summary['distinct_sessions']:,}")
    print("Event mix:")
    for event_type, count in summary["event_type_counts"].most_common():
        print(f"  - {event_type}: {count:,} ({percentage(count, total_rows):.2f}%)")
    print("Missing values:")
    for column, count in summary["missing_counts"].most_common():
        print(f"  - {column}: {count:,} ({percentage(count, total_rows):.2f}%)")
    print(
        "Price checks: "
        f"zero={summary['zero_price_count']:,}, "
        f"negative={summary['negative_price_count']:,}, "
        f">10k={summary['high_price_count']:,}"
    )
    print("Top prices across both files:")
    for price, file_name, product_id, brand, category_code in summary["top_prices"]:
        print(
            f"  - {price:,.2f} | file={file_name} | product_id={product_id} | "
            f"brand={brand} | category={category_code}"
        )


def main() -> None:
    audits = [scan_file(path) for path in DATA_FILES]
    for audit in audits:
        print_file_summary(audit)
    print_combined_summary(combine(audits))


if __name__ == "__main__":
    main()
