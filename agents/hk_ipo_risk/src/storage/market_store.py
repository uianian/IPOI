from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class PostgresMarketStore:
    """Append-only PostgreSQL store for scores, evidence, debates and tool calls."""

    def __init__(self, postgres_url: str, *, schema: str = "market_agent") -> None:
        if not postgres_url:
            raise ValueError("postgres_url is required")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise ValueError(f"invalid PostgreSQL schema: {schema!r}")
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
        except ImportError as exc:
            raise RuntimeError("SQLAlchemy and asyncpg are required for PostgreSQL persistence") from exc
        self.schema = schema
        if postgres_url.startswith("postgres://"):
            postgres_url = "postgresql+asyncpg://" + postgres_url[len("postgres://"):]
        elif postgres_url.startswith("postgresql://"):
            postgres_url = "postgresql+asyncpg://" + postgres_url[len("postgresql://"):]
        self._engine = create_async_engine(postgres_url, pool_pre_ping=True)

    async def initialize(self) -> None:
        from sqlalchemy import text

        ddl = self._ddl()
        async with self._engine.begin() as connection:
            for statement in ddl:
                await connection.execute(text(statement))

    async def close(self) -> None:
        await self._engine.dispose()

    async def persist_prelisting_result(
        self,
        result: dict[str, Any],
        *,
        artifact_json: str | None = None,
        artifact_report: str | None = None,
    ) -> str:
        from sqlalchemy import text

        run_id = str(uuid.uuid4())
        features = result.get("features") or {}
        assessment = features.get("prelisting_day1_risk") or {}
        stock_code = str(features.get("stock_code") or "")
        evidence = (result.get("evidence_summary") or {}).get("evidence_ledger") or []
        evidence += (result.get("evidence_summary") or {}).get("historical_risk_evidence") or []
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    f"""INSERT INTO {self.schema}.market_runs
                    (run_id, doc_id, stock_code, phase, checkpoint, as_of_date, status, metadata)
                    VALUES (:run_id, :doc_id, :stock_code, 'prelisting', NULL, :as_of_date, 'completed', CAST(:metadata AS jsonb))"""
                ),
                {
                    "run_id": run_id,
                    "doc_id": result.get("doc_id"),
                    "stock_code": stock_code,
                    "as_of_date": assessment.get("as_of_date"),
                    "metadata": _json({"risk_anchor": "issue_price", "return_base": "first_trading_day_open"}),
                },
            )
            await self._insert_score(connection, run_id, assessment)
            await self._insert_evidence(connection, run_id, "prelisting", evidence)
            if artifact_json or artifact_report:
                await connection.execute(
                    text(
                        f"""INSERT INTO {self.schema}.market_artifacts
                        (artifact_id, run_id, json_path, report_path, content_hash)
                        VALUES (:artifact_id, :run_id, :json_path, :report_path, :content_hash)"""
                    ),
                    {
                        "artifact_id": str(uuid.uuid4()),
                        "run_id": run_id,
                        "json_path": artifact_json,
                        "report_path": artifact_report,
                        "content_hash": hashlib.sha256(_json(result).encode("utf-8")).hexdigest(),
                    },
                )
        return run_id

    async def persist_postlisting_checkpoints(
        self,
        *,
        doc_id: str,
        stock_code: str,
        checkpoints: list[dict[str, Any]],
    ) -> list[str]:
        from sqlalchemy import text

        run_ids: list[str] = []
        async with self._engine.begin() as connection:
            for checkpoint in checkpoints:
                run_id = str(uuid.uuid4())
                run_ids.append(run_id)
                await connection.execute(
                    text(
                        f"""INSERT INTO {self.schema}.market_runs
                        (run_id, doc_id, stock_code, phase, checkpoint, as_of_date, status, metadata)
                        VALUES (:run_id, :doc_id, :stock_code, 'postlisting', :checkpoint,
                                :as_of_date, 'completed', CAST(:metadata AS jsonb))"""
                    ),
                    {
                        "run_id": run_id,
                        "doc_id": doc_id,
                        "stock_code": stock_code,
                        "checkpoint": checkpoint.get("checkpoint"),
                        "as_of_date": checkpoint.get("observation_date"),
                        "metadata": _json({"trading_day": checkpoint.get("trading_day")}),
                    },
                )
                await self._insert_score(
                    connection,
                    run_id,
                    {
                        "score_name": "realized_market_risk_score",
                        "score": checkpoint.get("realized_risk_score"),
                        "risk_level": checkpoint.get("risk_level"),
                        "score_version": checkpoint.get("score_version"),
                        "evidence_ids": checkpoint.get("evidence_ids") or [],
                        **checkpoint,
                    },
                )
                evidence = [metric for metric in checkpoint.get("metrics") or []]
                await self._insert_evidence(
                    connection,
                    run_id,
                    str(checkpoint.get("checkpoint") or "postlisting"),
                    evidence,
                )
        return run_ids

    async def query_evidence(
        self,
        *,
        doc_id: str,
        stock_code: str,
        phase: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import text

        sql = f"""SELECT e.evidence_id, e.phase, e.observation_date, e.source, e.payload,
                          r.run_id, r.as_of_date
                   FROM {self.schema}.market_evidence e
                   JOIN {self.schema}.market_runs r ON r.run_id=e.run_id
                   WHERE r.doc_id=:doc_id AND r.stock_code=:stock_code
                     AND (:phase IS NULL OR e.phase=:phase)
                   ORDER BY e.created_at DESC LIMIT :limit"""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                text(sql),
                {"doc_id": doc_id, "stock_code": stock_code, "phase": phase, "limit": min(limit, 500)},
            )
            return [dict(row._mapping) for row in result]

    async def save_debate_round(
        self,
        *,
        run_id: str,
        debate_id: str,
        round_number: int,
        challenge: str,
        response: dict[str, Any],
    ) -> None:
        from sqlalchemy import text

        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    f"""INSERT INTO {self.schema}.market_debate_rounds
                    (debate_round_id, debate_id, run_id, round_number, challenge, response)
                    VALUES (:id, :debate_id, :run_id, :round_number, :challenge, CAST(:response AS jsonb))"""
                ),
                {
                    "id": str(uuid.uuid4()),
                    "debate_id": debate_id,
                    "run_id": run_id,
                    "round_number": round_number,
                    "challenge": challenge,
                    "response": _json(response),
                },
            )

    async def save_tool_call(
        self,
        *,
        debate_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        from sqlalchemy import text

        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    f"""INSERT INTO {self.schema}.market_tool_calls
                    (tool_call_id, debate_id, tool_name, arguments, result)
                    VALUES (:id, :debate_id, :tool_name, CAST(:arguments AS jsonb), CAST(:result AS jsonb))"""
                ),
                {
                    "id": str(uuid.uuid4()),
                    "debate_id": debate_id,
                    "tool_name": tool_name,
                    "arguments": _json(arguments),
                    "result": _json(result),
                },
            )

    async def _insert_score(self, connection: Any, run_id: str, score: dict[str, Any]) -> None:
        from sqlalchemy import text

        await connection.execute(
            text(
                f"""INSERT INTO {self.schema}.market_score_versions
                (score_id, run_id, score_name, score_value, risk_level, score_version,
                 evidence_ids, payload)
                VALUES (:score_id, :run_id, :score_name, :score_value, :risk_level,
                        :score_version, :evidence_ids, CAST(:payload AS jsonb))"""
            ),
            {
                "score_id": str(uuid.uuid4()),
                "run_id": run_id,
                "score_name": score.get("score_name") or "unknown",
                "score_value": score.get("score") if score.get("score") is not None else score.get("realized_risk_score"),
                "risk_level": score.get("risk_level"),
                "score_version": score.get("score_version"),
                "evidence_ids": list(score.get("evidence_ids") or []),
                "payload": _json(score),
            },
        )

    async def _insert_evidence(
        self,
        connection: Any,
        run_id: str,
        phase: str,
        evidence: list[dict[str, Any]],
    ) -> None:
        from sqlalchemy import text

        for item in evidence:
            evidence_id = str(item.get("evidence_id") or item.get("field") or uuid.uuid4())
            payload = _json(item)
            await connection.execute(
                text(
                    f"""INSERT INTO {self.schema}.market_evidence
                    (evidence_pk, run_id, evidence_id, phase, observation_date, source,
                     content_hash, payload)
                    VALUES (:pk, :run_id, :evidence_id, :phase, :observation_date, :source,
                            :content_hash, CAST(:payload AS jsonb))"""
                ),
                {
                    "pk": str(uuid.uuid4()),
                    "run_id": run_id,
                    "evidence_id": evidence_id,
                    "phase": phase,
                    "observation_date": item.get("observation_date") or item.get("history_end"),
                    "source": item.get("source") or item.get("derived_file") or "market_agent",
                    "content_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                    "payload": payload,
                },
            )

    def _ddl(self) -> list[str]:
        s = self.schema
        return [
            f"CREATE SCHEMA IF NOT EXISTS {s}",
            f"""CREATE TABLE IF NOT EXISTS {s}.market_runs (
                run_id uuid PRIMARY KEY, doc_id text NOT NULL, stock_code varchar(5) NOT NULL,
                phase text NOT NULL, checkpoint text, as_of_date date, status text NOT NULL,
                metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb, created_at timestamptz NOT NULL DEFAULT now())""",
            f"""CREATE INDEX IF NOT EXISTS ix_market_runs_lookup
                ON {s}.market_runs (doc_id, stock_code, phase, checkpoint, created_at DESC)""",
            f"""CREATE TABLE IF NOT EXISTS {s}.market_score_versions (
                score_id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES {s}.market_runs(run_id),
                score_name text NOT NULL, score_value double precision, risk_level text,
                score_version text, evidence_ids text[] NOT NULL DEFAULT ARRAY[]::text[],
                payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
            f"""CREATE TABLE IF NOT EXISTS {s}.market_evidence (
                evidence_pk uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES {s}.market_runs(run_id),
                evidence_id text NOT NULL, phase text NOT NULL, observation_date date, source text,
                content_hash char(64) NOT NULL, payload jsonb NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now())""",
            f"""CREATE INDEX IF NOT EXISTS ix_market_evidence_lookup
                ON {s}.market_evidence (run_id, phase, evidence_id)""",
            f"""CREATE TABLE IF NOT EXISTS {s}.market_artifacts (
                artifact_id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES {s}.market_runs(run_id),
                json_path text, report_path text, content_hash char(64),
                created_at timestamptz NOT NULL DEFAULT now())""",
            f"""CREATE TABLE IF NOT EXISTS {s}.market_debate_rounds (
                debate_round_id uuid PRIMARY KEY, debate_id text NOT NULL,
                run_id uuid NOT NULL REFERENCES {s}.market_runs(run_id), round_number integer NOT NULL,
                challenge text NOT NULL, response jsonb NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now())""",
            f"""CREATE TABLE IF NOT EXISTS {s}.market_tool_calls (
                tool_call_id uuid PRIMARY KEY, debate_id text NOT NULL, tool_name text NOT NULL,
                arguments jsonb NOT NULL, result jsonb NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now())""",
        ]

