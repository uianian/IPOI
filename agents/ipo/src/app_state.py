from src.cache.redis_client import RedisClient
from src.db.database import Database
from src.llm.client import VLLMClient
from src.retrieval.store import DocumentIndexStore
from src.skills.registry import SkillRegistry

redis_client = RedisClient()
database = Database()
skill_registry = SkillRegistry()
vllm_client = VLLMClient()
document_index_store = DocumentIndexStore(vllm_client)
