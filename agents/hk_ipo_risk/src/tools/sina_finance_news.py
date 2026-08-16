from __future__ import annotations

import csv
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.tools.firecrawl_news import NEWS_FIELDS, _parse_date


def _path(value: Any, dotted: str) -> Any:
    current = value
    if not dotted:
        return current
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _write_news_cache(path: Path, articles: list[dict[str, str]], *, merge: bool) -> None:
    rows: list[dict[str, str]] = []
    if merge and path.is_file():
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            rows.extend(
                {field: str(row.get(field) or "") for field in NEWS_FIELDS}
                for row in csv.DictReader(source)
            )
    by_url = {row["新闻链接"]: row for row in rows if row.get("新闻链接")}
    for article in articles:
        by_url[article["新闻链接"]] = article
    merged = [row for row in rows if not row.get("新闻链接")] + list(by_url.values())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", delete=False,
            dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp",
        ) as target:
            temporary = Path(target.name)
            writer = csv.DictWriter(target, fieldnames=NEWS_FIELDS)
            writer.writeheader()
            writer.writerows(merged)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class SinaFinanceNewsCollector:
    """Configurable adapter for a licensed/authorized Sina Finance news JSON API.

    Sina API variants differ across deployments. Endpoint, auth placement,
    request parameter names and response field paths therefore live entirely
    in YAML. Strict publication-date cutoff is enforced after normalization.
    """

    def __init__(self, settings: dict[str, Any], *, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    def public_status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.settings.get("enabled")),
            "requested_enabled": bool(self.settings.get("requested_enabled")),
            "configured": bool(self.settings.get("configured")),
            "settings_path": self.settings.get("settings_path"),
            "local_settings_path": self.settings.get("local_settings_path"),
        }

    async def collect(
        self,
        *,
        company: str,
        stock_code: str,
        as_of_date: date,
        news_dir: Path | str,
    ) -> dict[str, Any]:
        status = self.public_status()
        status.update({"attempted": False, "received": 0, "accepted_articles": 0,
                       "rejected_after_cutoff": 0, "rejected_missing_date": 0,
                       "rejected_empty_content": 0, "errors": []})
        if not self.settings.get("enabled"):
            status["skip_reason"] = "sina_api_not_configured" if status["requested_enabled"] else "sina_disabled"
            return status
        status["attempted"] = True
        request_cfg = self.settings.get("request") or {}
        auth_cfg = self.settings.get("auth") or {}
        params = dict(request_cfg.get("static_params") or {})
        params[str(request_cfg.get("query_param") or "q")] = f'"{company}" {stock_code} IPO 上市'
        params[str(request_cfg.get("limit_param") or "limit")] = int(request_cfg.get("limit") or 20)
        headers: dict[str, str] = {}
        key = str(self.settings.get("api_key") or "")
        if key:
            auth_value = f"{auth_cfg.get('prefix') or ''}{key}"
            if str(auth_cfg.get("location") or "header") == "query":
                params[str(auth_cfg.get("name") or "apikey")] = auth_value
            else:
                headers[str(auth_cfg.get("name") or "Authorization")] = auth_value
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=float(request_cfg.get("timeout_seconds") or 30))
        try:
            response = await client.request(
                str(self.settings.get("method") or "GET").upper(),
                str(self.settings["base_url"]), params=params, headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            message = str(exc).replace(key, "[redacted]") if key else str(exc)
            status["errors"].append(f"request_failed:{type(exc).__name__}:{message}")
            return status
        finally:
            if owns_client:
                await client.aclose()

        response_cfg = self.settings.get("response") or {}
        fields = response_cfg.get("fields") or {}
        items = _path(payload, str(response_cfg.get("items_path") or ""))
        if not isinstance(items, list):
            status["errors"].append("response_items_not_list")
            return status
        status["received"] = len(items)
        accepted: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            published = _parse_date(_path(item, str(fields.get("published_at") or "published_at")))
            if published is None:
                status["rejected_missing_date"] += 1
                continue
            if published > as_of_date:
                status["rejected_after_cutoff"] += 1
                continue
            content = str(_path(item, str(fields.get("content") or "content")) or "").strip()
            if not content:
                status["rejected_empty_content"] += 1
                continue
            url = str(_path(item, str(fields.get("url") or "url")) or "").strip()
            if not url:
                continue
            accepted.append({
                "query": stock_code,
                "关键词": f"{company} {stock_code}",
                "新闻标题": str(_path(item, str(fields.get("title") or "title")) or "").strip(),
                "新闻内容": content,
                "发布时间": published.isoformat(),
                "文章来源": str(_path(item, str(fields.get("source") or "source")) or "新浪财经").strip(),
                "新闻链接": url,
                "抓取方式": "sina_finance_api",
                "抓取时间": datetime.now(timezone.utc).isoformat(),
            })
        output_path = Path(news_dir) / f"{stock_code}.csv"
        if accepted:
            _write_news_cache(
                output_path, accepted,
                merge=bool((self.settings.get("cache") or {}).get("merge_existing", True)),
            )
        status["accepted_articles"] = len(accepted)
        status["cache_file"] = str(output_path)
        return status

