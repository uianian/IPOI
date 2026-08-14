from __future__ import annotations

import csv
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import IPOI_ROOT
from src.models.market import MarketEvidence, MarketSnapshot


DEFAULT_FEATURES_CSV = IPOI_ROOT / "market" / "data" / "derived" / "ipo_sentiment_features.csv"
DEFAULT_NEWS_DIR = IPOI_ROOT / "market" / "data" / "external" / "news"

FORBIDDEN_PREFIXES = ("outcome_",)
POINTER_FIELDS = {"news_rows", "news_earliest", "news_latest"}
IDENTIFIER_FIELDS = {
    "stock_code",
    "windcode",
    "company",
    "listing_date",
    "as_of_date",
    "market_observation_date",
    "industry",
    "hsics_l1_name",
    "industry_source",
    "industry_return_source",
    "hsics_index_code",
    "hsics_index_name",
    "hs_sector_index",
    "subscription_source",
}


def normalize_stock_code(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits or len(digits) > 5:
        raise ValueError(f"invalid Hong Kong stock code: {value!r}")
    return digits.zfill(5)


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _coerce(value: Any) -> float | str | bool | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "nat", "none", "null"}:
        return None
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except ValueError:
        return text


class MarketDataLoader:
    """Read the offline IPO snapshot and enforce the pre-listing cutoff contract."""

    def __init__(
        self,
        features_csv: Path | str = DEFAULT_FEATURES_CSV,
        *,
        news_dir: Path | str = DEFAULT_NEWS_DIR,
        strict_cutoff: bool = True,
    ) -> None:
        self.features_csv = Path(features_csv)
        self.news_dir = Path(news_dir)
        self.strict_cutoff = strict_cutoff

    def load_snapshot(self, stock_code: str) -> MarketSnapshot:
        code5 = normalize_stock_code(stock_code)
        if not self.features_csv.is_file():
            raise FileNotFoundError(f"market feature table not found: {self.features_csv}")

        row: dict[str, str] | None = None
        with self.features_csv.open("r", encoding="utf-8-sig", newline="") as f:
            for candidate in csv.DictReader(f):
                try:
                    candidate_code = normalize_stock_code(candidate.get("stock_code", ""))
                except ValueError:
                    continue
                if candidate_code == code5:
                    row = candidate
                    break
        if row is None:
            raise KeyError(f"stock_code {code5} not found in {self.features_csv}")

        listing_date = _parse_date(row.get("listing_date"))
        if listing_date is None:
            raise ValueError(f"invalid listing_date for {code5}: {row.get('listing_date')!r}")
        expected_cutoff = listing_date - timedelta(days=1)
        declared_as_of = _parse_date(row.get("as_of_date"))
        observation_date = _parse_date(row.get("market_observation_date"))
        quality_flags: list[str] = []
        cutoff_verified = declared_as_of is not None
        as_of_date = declared_as_of or expected_cutoff

        if declared_as_of is None:
            quality_flags.append("legacy_snapshot_missing_as_of_date")
        if as_of_date > expected_cutoff:
            quality_flags.append("snapshot_after_prelisting_cutoff")
            cutoff_verified = False
        if observation_date and observation_date > expected_cutoff:
            quality_flags.append("market_observation_after_prelisting_cutoff")
            cutoff_verified = False
        if self.strict_cutoff and not cutoff_verified:
            raise ValueError(
                f"unverified market cutoff for {code5}; rebuild market features with the "
                "pre-listing as_of_date contract or set strict_cutoff=False for diagnostics"
            )

        features: dict[str, float | str | bool | None] = {}
        missing: list[str] = []
        evidence: list[MarketEvidence] = []
        for field, raw in row.items():
            if field in IDENTIFIER_FIELDS or field in POINTER_FIELDS:
                continue
            if field.startswith(FORBIDDEN_PREFIXES):
                continue
            value = _coerce(raw)
            features[field] = value
            if value is None:
                missing.append(field)
                continue
            evidence.append(
                MarketEvidence(
                    source=str(self.features_csv),
                    field=field,
                    value=value,
                    observation_date=observation_date or as_of_date,
                    note="pre-listing structured market snapshot",
                )
            )

        return MarketSnapshot(
            stock_code=code5,
            company=str(row.get("company") or ""),
            listing_date=listing_date,
            as_of_date=as_of_date,
            market_observation_date=observation_date,
            industry=str(row.get("industry") or "") or None,
            hsics_l1_name=str(row.get("hsics_l1_name") or "") or None,
            industry_source=str(row.get("industry_source") or "") or None,
            industry_return_source=str(row.get("industry_return_source") or "") or None,
            hsics_index_code=str(row.get("hsics_index_code") or "") or None,
            hsics_index_name=str(row.get("hsics_index_name") or "") or None,
            subscription_source=str(row.get("subscription_source") or "") or None,
            features=features,
            missing_fields=missing,
            quality_flags=quality_flags,
            cutoff_verified=cutoff_verified,
            evidence=evidence,
        )

    def inspect_news_availability(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        """Describe why local public opinion is usable or unavailable."""
        path = self.news_dir / f"{snapshot.stock_code}.csv"
        result: dict[str, Any] = {
            "file": str(path),
            "exists": path.is_file(),
            "total_rows": 0,
            "pre_cutoff_rows": 0,
            "earliest_date": None,
            "latest_date": None,
        }
        if not path.is_file():
            result["unavailable_reason"] = "local_news_file_missing"
            return result
        dates: list[date] = []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                result["total_rows"] += 1
                published = _parse_date(row.get("发布时间") or row.get("published_at"))
                if published is None:
                    continue
                dates.append(published)
                if published <= snapshot.as_of_date:
                    result["pre_cutoff_rows"] += 1
        if dates:
            result["earliest_date"] = min(dates)
            result["latest_date"] = max(dates)
        if result["pre_cutoff_rows"] == 0:
            result["unavailable_reason"] = (
                "all_local_news_after_as_of_date"
                if dates
                else "local_news_dates_missing_or_invalid"
            )
        return result

    def load_news_candidates(self, snapshot: MarketSnapshot) -> list[dict[str, Any]]:
        """Return dated pre-cutoff candidates; relevance still requires LLM review."""
        path = self.news_dir / f"{snapshot.stock_code}.csv"
        if not path.is_file():
            return []
        candidates: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                published = _parse_date(row.get("发布时间") or row.get("published_at"))
                if published is None or published > snapshot.as_of_date:
                    continue
                candidates.append(
                    {
                        "title": row.get("新闻标题") or row.get("title") or "",
                        "summary": (
                            row.get("正文")
                            or row.get("content")
                            or row.get("新闻内容")
                            or row.get("summary")
                            or ""
                        )[:8000],
                        "published_at": published.isoformat(),
                        "source": row.get("文章来源") or row.get("source") or "",
                        "url": row.get("新闻链接") or row.get("url") or "",
                    }
                )
        return candidates

