from __future__ import annotations

import csv
import json
import logging
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

NEWS_FIELDS = [
    "query",
    "关键词",
    "新闻标题",
    "新闻内容",
    "发布时间",
    "文章来源",
    "新闻链接",
    "抓取方式",
    "抓取时间",
]


def _value(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        for name in names:
            if obj.get(name) not in (None, ""):
                return obj[name]
        return None
    for name in names:
        value = getattr(obj, name, None)
        if value not in (None, ""):
            return value
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y年%m月%d日",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(text[:32], fmt).date()
        except ValueError:
            continue
    return None


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


class _PublishedDateHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[tuple[str, str]] = []
        self._json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag.lower() == "meta":
            name = (
                values.get("property")
                or values.get("name")
                or values.get("itemprop")
            ).lower()
            if name in {
                "article:published_time",
                "og:published_time",
                "datepublished",
                "date",
                "pubdate",
                "publishdate",
                "publish_date",
            } and values.get("content"):
                self.candidates.append((values["content"], f"html_meta:{name}"))
        elif tag.lower() == "time" and values.get("datetime"):
            self.candidates.append((values["datetime"], "html_time"))
        elif tag.lower() == "script" and "ld+json" in values.get("type", "").lower():
            self._json_ld = True
            self._json_ld_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._json_ld:
            self._json_ld = False
            raw = "".join(self._json_ld_parts).strip()
            try:
                self._collect_json_ld(json.loads(raw))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

    def handle_data(self, data: str) -> None:
        if self._json_ld:
            self._json_ld_parts.append(data)

    def _collect_json_ld(self, value: Any) -> None:
        if isinstance(value, dict):
            published = value.get("datePublished")
            if published:
                self.candidates.append((str(published), "json_ld:datePublished"))
            for nested in value.values():
                self._collect_json_ld(nested)
        elif isinstance(value, list):
            for nested in value:
                self._collect_json_ld(nested)


def _extract_published_date(
    *,
    metadata: Any,
    search_value: Any,
    raw_html: str,
    markdown: str,
    url: str,
) -> tuple[date | None, str | None]:
    metadata_names = (
        "published_time",
        "publishedTime",
        "published_date",
        "publishedDate",
        "datePublished",
        "article:published_time",
        "og:published_time",
        "date",
    )
    parsed = _parse_date(_value(metadata, *metadata_names))
    if parsed:
        return parsed, "firecrawl_metadata"
    parsed = _parse_date(search_value)
    if parsed:
        return parsed, "search_result"

    if raw_html:
        parser = _PublishedDateHTMLParser()
        try:
            parser.feed(raw_html)
        except Exception:
            parser.candidates = []
        for value, source in parser.candidates:
            parsed = _parse_date(value)
            if parsed:
                return parsed, source

    header = markdown[:4000]
    labeled_patterns = (
        r"(?:发布时间|发布日期|发布于|刊登日期|Published|Posted|Publication date)\s*[:：]?\s*"
        r"(20\d{2}[年/.-]\s*\d{1,2}[月/.-]\s*\d{1,2}日?)",
        r"(?:发布时间|发布日期|发布于|刊登日期)\s*[:：]?\s*"
        r"(20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
    )
    for pattern in labeled_patterns:
        match = re.search(pattern, header, flags=re.IGNORECASE)
        if match and (parsed := _parse_date(re.sub(r"\s+", "", match.group(1)))):
            return parsed, "markdown_labeled_date"
    first_lines = "\n".join(header.splitlines()[:12])
    match = re.search(r"\b(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})\b", first_lines)
    if match and (parsed := _parse_date(match.group(1))):
        return parsed, "markdown_header_date"

    path = urlparse(url).path
    for pattern in (
        r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|[-_.])",
        r"/(20\d{2})[-_](\d{1,2})[-_](\d{1,2})(?:[-_.]|/)",
        r"(?:/|[-_])(20\d{2})(\d{2})(\d{2})(?:[-_.]|/|$)",
    ):
        match = re.search(pattern, path)
        if match:
            try:
                return date(*(int(part) for part in match.groups())), "url_date"
            except ValueError:
                continue
    return None, None


def _is_homepage_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path in {"", "/"} and not parsed.query


class FirecrawlNewsCollector:
    """Discover and cache verifiably pre-listing article bodies.

    Search is only URL discovery. Every selected URL is passed through
    Firecrawl ``scrape`` with ``markdown`` and ``only_main_content``. An article
    is cached only when a publication date can be verified and is no later than
    the market snapshot's ``as_of_date``.
    """

    def __init__(self, settings: dict[str, Any], *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("enabled"))

    def public_status(self) -> dict[str, Any]:
        """Return configuration state without exposing credentials."""
        return {
            "enabled": self.enabled,
            "requested_enabled": bool(self.settings.get("requested_enabled")),
            "configured": bool(self.settings.get("configured")),
            "fetch_policy": self.settings.get("fetch_policy"),
            "settings_path": self.settings.get("settings_path"),
            "local_settings_path": self.settings.get("local_settings_path"),
        }

    def redact_error(self, value: Any) -> str:
        message = str(value)
        key = str(self.settings.get("api_key") or "")
        return message.replace(key, "[redacted]") if key else message

    def collect(
        self,
        *,
        company: str,
        stock_code: str,
        listing_date: date,
        as_of_date: date,
        news_dir: Path | str,
    ) -> dict[str, Any]:
        news_path = Path(news_dir)
        output_path = news_path / f"{stock_code}.csv"
        raw_path = self.raw_cache_path(
            stock_code=stock_code,
            as_of_date=as_of_date,
            news_dir=news_path,
        )
        status = self.public_status()
        status.update(
            {
                "attempted": False,
                "queries": [],
                "search_requests": 0,
                "search_result_limit": 0,
                "search_hits": 0,
                "unique_urls": 0,
                "filtered_homepage_urls": 0,
                "scrape_request_limit": 0,
                "scrape_requests": 0,
                "scraped_urls": 0,
                "accepted_articles": 0,
                "rejected_after_cutoff": 0,
                "rejected_before_window": 0,
                "rejected_missing_date": 0,
                "rejected_empty_content": 0,
                "raw_cache_used": False,
                "raw_articles": 0,
                "raw_cache_file": str(raw_path),
                "cache_file": str(output_path),
                "errors": [],
            }
        )
        cache_cfg = self.settings.get("cache") or {}
        if (
            bool(cache_cfg.get("reuse_raw_results", True))
            and str(self.settings.get("fetch_policy") or "on_missing") != "always"
            and raw_path.is_file()
        ):
            try:
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
                if (
                    str(payload.get("stock_code")) == stock_code
                    and str(payload.get("as_of_date")) == as_of_date.isoformat()
                    and self._raw_cache_matches_window(payload, as_of_date=as_of_date)
                ):
                    status["raw_cache_used"] = True
                    status["skip_reason"] = "reused_raw_firecrawl_cache"
                    return self._finalize_payload(
                        payload,
                        status=status,
                        output_path=output_path,
                        raw_path=raw_path,
                        as_of_date=as_of_date,
                    )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                status["errors"].append(f"raw_cache_read_failed:{type(exc).__name__}:{exc}")
        if not self.enabled:
            status["skip_reason"] = (
                "firecrawl_api_key_missing"
                if status["requested_enabled"] and not status["configured"]
                else "firecrawl_disabled"
            )
            return status

        status["attempted"] = True
        client = self._get_client()
        search_cfg = self.settings.get("search") or {}
        scrape_cfg = self.settings.get("scrape") or {}
        template = str(
            search_cfg.get("query_template")
            or '"{company}" 风险 争议 监管 舆论 新闻'
        )
        variables = {
            "company": company,
            "stock_code": stock_code,
            "listing_date": listing_date.isoformat(),
            "as_of_date": as_of_date.isoformat(),
            "year": str(as_of_date.year),
        }

        discovered: dict[str, dict[str, Any]] = {}
        max_urls = min(10, int(search_cfg.get("max_urls") or 10))
        search_limit = min(10, int(search_cfg.get("limit_per_query") or 10))
        status["search_result_limit"] = search_limit
        sources = list(search_cfg.get("sources") or ["web"])
        status["search_sources"] = sources
        tbs = None
        legacy_years = search_cfg.get("historical_lookback_years")
        configured_lookback_days = (
            int(search_cfg["lookback_days"])
            if search_cfg.get("lookback_days") is not None
            else int(legacy_years) * 365 if legacy_years is not None else 365
        )
        lookback_days = max(1, configured_lookback_days)
        window_start = as_of_date - timedelta(days=lookback_days)
        status["window_start"] = window_start.isoformat()
        if bool(search_cfg.get("use_tbs_date_filter", True)):
            tbs = (
                "cdr:1,"
                f"cd_min:{window_start.strftime('%m/%d/%Y')},"
                f"cd_max:{as_of_date.strftime('%m/%d/%Y')}"
            )
        status["tbs"] = tbs
        try:
            query = template.format(**variables)
        except (KeyError, ValueError) as exc:
            status["errors"].append(f"invalid_query_template:{exc}")
            return status
        status["queries"].append(query)
        payload: dict[str, Any] = {
            "version": "firecrawl-raw-v1",
            "stock_code": stock_code,
            "company": company,
            "listing_date": listing_date.isoformat(),
            "as_of_date": as_of_date.isoformat(),
            "window_start": window_start.isoformat(),
            "query": query,
            "sources": sources,
            "tbs": tbs,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed": False,
            "articles": [],
            "errors": [],
        }
        self._write_raw_cache(raw_path, payload)
        try:
            status["search_requests"] = 1
            search_options: dict[str, Any] = {
                "sources": sources,
                "limit": search_limit,
                "location": str(search_cfg.get("location") or "Hong Kong"),
                "ignore_invalid_urls": True,
                "timeout": int(search_cfg.get("timeout_ms") or 60000),
            }
            if tbs:
                search_options["tbs"] = tbs
            excluded = list(search_cfg.get("exclude_domains") or [])
            if excluded:
                search_options["exclude_domains"] = excluded
            results = client.search(query, **search_options)
        except Exception as exc:
            logger.warning("Firecrawl search failed for %s: %s", query, exc)
            message = self.redact_error(f"search_failed:{type(exc).__name__}:{exc}")
            status["errors"].append(message)
            payload["errors"].append(message)
            payload["completed"] = True
            self._write_raw_cache(raw_path, payload)
            return self._finalize_payload(
                payload,
                status=status,
                output_path=output_path,
                raw_path=raw_path,
                as_of_date=as_of_date,
            )
        bucket_order = [name for name in ("news", "web") if name in sources]
        bucket_order.extend(name for name in sources if name not in bucket_order)
        for bucket_name in bucket_order:
            bucket = _value(results, bucket_name) or []
            for item in bucket:
                status["search_hits"] += 1
                url = str(_value(item, "url") or "").strip()
                if not url.startswith(("http://", "https://")) or url in discovered:
                    continue
                discovered[url] = {
                    "query": query,
                    "url": url,
                    "title": str(_value(item, "title") or "").strip(),
                    "description": str(
                        _value(item, "description", "snippet", "summary") or ""
                    ).strip(),
                    "published_at": _value(
                        item,
                        "published_date",
                        "publishedDate",
                        "published_time",
                        "publishedTime",
                        "date",
                    ),
                }
                if len(discovered) >= max_urls:
                    break
            if len(discovered) >= max_urls:
                break
        status["unique_urls"] = len(discovered)
        for candidate in discovered.values():
            search_published_at = candidate.get("published_at")
            article = {
                **{key: value for key, value in candidate.items() if key != "published_at"},
                "search_published_at": search_published_at,
                "scrape_status": "pending",
                "scraped_at": None,
                "markdown": "",
                "raw_html": "",
                "metadata": {},
                "published_at": None,
                "date_source": None,
                "accepted_for_scoring": False,
                "rejection_reason": None,
                "scrape_error": None,
            }
            if _is_homepage_url(str(article["url"])):
                article["scrape_status"] = "filtered"
                article["rejection_reason"] = "homepage_url"
                status["filtered_homepage_urls"] += 1
            payload["articles"].append(article)
        self._write_raw_cache(raw_path, payload)

        scrape_limit = min(10, int(scrape_cfg.get("max_requests") or 10))
        status["scrape_request_limit"] = scrape_limit
        candidates = [
            article for article in payload["articles"]
            if article.get("scrape_status") == "pending"
        ][:scrape_limit]
        for article in candidates:
            try:
                status["scrape_requests"] += 1
                doc = client.scrape(
                    article["url"],
                    formats=["markdown", "rawHtml"],
                    only_main_content=bool(scrape_cfg.get("only_main_content", True)),
                    timeout=int(scrape_cfg.get("timeout_ms") or 30000),
                    max_age=int(scrape_cfg.get("max_age_ms") or 86400000),
                    store_in_cache=True,
                )
                status["scraped_urls"] += 1
            except Exception as exc:
                logger.warning("Firecrawl scrape failed for %s: %s", article["url"], exc)
                message = self.redact_error(
                    f"scrape_failed:{article['url']}:{type(exc).__name__}:{exc}"
                )
                status["errors"].append(message)
                payload["errors"].append(message)
                article["scrape_status"] = "failed"
                article["scrape_error"] = message
                article["rejection_reason"] = "scrape_failed"
                payload["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._write_raw_cache(raw_path, payload)
                continue
            metadata = _value(doc, "metadata") or {}
            markdown = str(_value(doc, "markdown") or "").strip()
            raw_html = str(_value(doc, "raw_html", "rawHtml") or "").strip()
            article.update(
                {
                    "scrape_status": "success",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "markdown": markdown[: int(scrape_cfg.get("max_raw_content_chars") or 100000)],
                    "raw_html": raw_html[: int(scrape_cfg.get("max_raw_html_chars") or 250000)],
                    "metadata": _json_safe(metadata),
                    "title": str(_value(metadata, "title", "ogTitle") or article["title"]).strip(),
                    "source": str(
                        _value(metadata, "source", "siteName", "ogSiteName")
                        or urlparse(str(article["url"])).netloc
                    ).strip(),
                }
            )
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_raw_cache(raw_path, payload)

        payload["completed"] = True
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_raw_cache(raw_path, payload)
        return self._finalize_payload(
            payload,
            status=status,
            output_path=output_path,
            raw_path=raw_path,
            as_of_date=as_of_date,
        )

    @staticmethod
    def raw_cache_path(
        *,
        stock_code: str,
        as_of_date: date,
        news_dir: Path | str,
    ) -> Path:
        return Path(news_dir) / "raw" / f"{stock_code}_{as_of_date.isoformat()}_firecrawl.json"

    def has_reusable_raw_cache(
        self,
        *,
        stock_code: str,
        as_of_date: date,
        news_dir: Path | str,
    ) -> bool:
        cache_cfg = self.settings.get("cache") or {}
        raw_path = self.raw_cache_path(
            stock_code=stock_code,
            as_of_date=as_of_date,
            news_dir=news_dir,
        )
        if not bool(cache_cfg.get("reuse_raw_results", True)) or not raw_path.is_file():
            return False
        try:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return (
            str(payload.get("stock_code")) == stock_code
            and str(payload.get("as_of_date")) == as_of_date.isoformat()
            and self._raw_cache_matches_window(payload, as_of_date=as_of_date)
        )

    def _raw_cache_matches_window(
        self,
        payload: dict[str, Any],
        *,
        as_of_date: date,
    ) -> bool:
        search_cfg = self.settings.get("search") or {}
        legacy_years = search_cfg.get("historical_lookback_years")
        configured_lookback_days = (
            int(search_cfg["lookback_days"])
            if search_cfg.get("lookback_days") is not None
            else int(legacy_years) * 365 if legacy_years is not None else 365
        )
        expected_start = as_of_date - timedelta(days=max(1, configured_lookback_days))
        return str(payload.get("window_start") or "") == expected_start.isoformat()

    def _finalize_payload(
        self,
        payload: dict[str, Any],
        *,
        status: dict[str, Any],
        output_path: Path,
        raw_path: Path,
        as_of_date: date,
    ) -> dict[str, Any]:
        accepted: list[dict[str, str]] = []
        articles = list(payload.get("articles") or [])
        status["raw_articles"] = len(articles)
        status["raw_cache_complete"] = bool(payload.get("completed"))
        status["cached_search_hits"] = len(articles)
        search_cfg = self.settings.get("search") or {}
        legacy_years = search_cfg.get("historical_lookback_years")
        configured_lookback_days = (
            int(search_cfg["lookback_days"])
            if search_cfg.get("lookback_days") is not None
            else int(legacy_years) * 365 if legacy_years is not None else 365
        )
        lookback_days = max(1, configured_lookback_days)
        window_start = as_of_date - timedelta(days=lookback_days)
        status["window_start"] = window_start.isoformat()
        status["raw_successful_articles"] = sum(
            article.get("scrape_status") == "success" for article in articles
        )
        status["filtered_homepage_urls"] = sum(
            article.get("rejection_reason") == "homepage_url" for article in articles
        )
        max_chars = int((self.settings.get("scrape") or {}).get("max_content_chars") or 8000)
        for article in articles:
            if article.get("scrape_status") != "success":
                continue
            markdown = str(article.get("markdown") or "").strip()
            if not markdown:
                article["accepted_for_scoring"] = False
                article["rejection_reason"] = "empty_content"
                status["rejected_empty_content"] += 1
                continue
            published, date_source = _extract_published_date(
                metadata=article.get("metadata") or {},
                search_value=article.get("search_published_at"),
                raw_html=str(article.get("raw_html") or ""),
                markdown=markdown,
                url=str(article.get("url") or ""),
            )
            article["published_at"] = published.isoformat() if published else None
            article["date_source"] = date_source
            if published is None:
                article["accepted_for_scoring"] = False
                article["rejection_reason"] = "missing_publication_date"
                status["rejected_missing_date"] += 1
                continue
            if published > as_of_date:
                article["accepted_for_scoring"] = False
                article["rejection_reason"] = "after_as_of_date"
                status["rejected_after_cutoff"] += 1
                continue
            if published < window_start:
                article["accepted_for_scoring"] = False
                article["rejection_reason"] = "before_window_start"
                status["rejected_before_window"] += 1
                continue
            article["accepted_for_scoring"] = True
            article["rejection_reason"] = None
            accepted.append(
                {
                    "query": str(payload.get("stock_code") or ""),
                    "关键词": str(article.get("query") or payload.get("query") or ""),
                    "新闻标题": str(article.get("title") or ""),
                    "新闻内容": markdown[:max_chars],
                    "发布时间": published.isoformat(),
                    "文章来源": str(article.get("source") or urlparse(str(article.get("url") or "")).netloc),
                    "新闻链接": str(article.get("url") or ""),
                    "抓取方式": f"firecrawl_search+scrape;date={date_source}",
                    "抓取时间": str(article.get("scraped_at") or payload.get("updated_at") or ""),
                }
            )
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_raw_cache(raw_path, payload)
        if accepted:
            self._write_cache(output_path, accepted)
        status["accepted_articles"] = len(accepted)
        status["raw_cache_file"] = str(raw_path)
        status["cache_file"] = str(output_path)
        status["errors"] = list(
            dict.fromkeys([*status.get("errors", []), *payload.get("errors", [])])
        )[:20]
        return status

    @staticmethod
    def _write_raw_cache(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=path.parent,
                prefix=f".{path.stem}.",
                suffix=".tmp",
            ) as target:
                temp_name = target.name
                json.dump(_json_safe(payload), target, ensure_ascii=False, indent=2)
                target.write("\n")
            Path(temp_name).replace(path)
        finally:
            if temp_name:
                temporary = Path(temp_name)
                if temporary.exists():
                    temporary.unlink()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from firecrawl import Firecrawl
        except ImportError as exc:
            raise RuntimeError(
                "Firecrawl is enabled but firecrawl-py is not installed; "
                "run pip install -r agents/hk_ipo_risk/requirements.txt"
            ) from exc
        kwargs: dict[str, Any] = {"api_key": self.settings.get("api_key")}
        api_url = str(self.settings.get("api_url") or "").rstrip("/")
        if api_url and api_url != "https://api.firecrawl.dev":
            kwargs["api_url"] = api_url
        self._client = Firecrawl(**kwargs)
        return self._client

    def _write_cache(self, path: Path, articles: list[dict[str, str]]) -> None:
        rows: list[dict[str, str]] = []
        if bool((self.settings.get("cache") or {}).get("merge_existing", True)) and path.is_file():
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                for row in csv.DictReader(source):
                    rows.append({field: str(row.get(field) or "") for field in NEWS_FIELDS})
        by_url = {row.get("新闻链接", ""): row for row in rows if row.get("新闻链接")}
        for article in articles:
            by_url[article["新闻链接"]] = article
        no_url_rows = [row for row in rows if not row.get("新闻链接")]
        merged = no_url_rows + list(by_url.values())

        path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
                newline="",
                delete=False,
                dir=path.parent,
                prefix=f".{path.stem}.",
                suffix=".tmp",
            ) as target:
                temp_name = target.name
                writer = csv.DictWriter(target, fieldnames=NEWS_FIELDS)
                writer.writeheader()
                writer.writerows(merged)
            Path(temp_name).replace(path)
        finally:
            if temp_name:
                temporary = Path(temp_name)
                if temporary.exists():
                    temporary.unlink()
