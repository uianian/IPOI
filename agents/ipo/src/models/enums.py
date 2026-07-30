from enum import Enum


class AgentRole(str, Enum):
    LEGAL = "legal"
    FINANCE = "finance"
    SENTIMENT = "sentiment"
    MASTER = "master"


class RiskLevel(str, Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class MarketTemperature(str, Enum):
    VERY_COLD = "very_cold"
    COLD = "cold"
    NEUTRAL = "neutral"
    HOT = "hot"
    VERY_HOT = "very_hot"


class SeverityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConflictType(str, Enum):
    SEMANTIC = "semantic"
    DIVERGENCE = "divergence"
    EVIDENCE_GAP = "evidence_gap"


class DebateStance(str, Enum):
    ASSERT = "assert"
    CHALLENGE = "challenge"
    CONCEDE = "concede"
    CLARIFY = "clarify"


class StepType(str, Enum):
    RETRIEVE = "retrieve"
    EXTRACT = "extract"
    ANALYZE = "analyze"
    VALIDATE = "validate"
    DEBATE = "debate"
    FUSE = "fuse"
    REPORT = "report"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"