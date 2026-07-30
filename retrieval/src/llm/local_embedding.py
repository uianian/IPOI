from __future__ import annotations

import logging
import os
import shutil
import ssl
from pathlib import Path
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)

_MODELSCOPE_MODELS = {
    "BAAI/bge-small-zh-v1.5": "Xorbits/bge-small-zh-v1.5",
    "BAAI/bge-large-zh-v1.5": "Xorbits/bge-large-zh-v1.5",
    "BAAI/bge-base-zh-v1.5": "Xorbits/bge-base-zh-v1.5",
}

_VALID_MODEL_FILES = {"config.json", "model.safetensors", "pytorch_model.bin", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.txt", "modules.json", "sentence_bert_config.json"}


def _is_valid_model_dir(path: Path) -> bool:
    if not (path / "config.json").exists():
        return False
    try:
        import json
        with open(path / "config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        return "model_type" in cfg
    except Exception:
        return False


def _disable_ssl_verify() -> None:
    if os.environ.get("_IPO_SSL_DISABLED"):
        return
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
        os.environ["CURL_CA_BUNDLE"] = ""
        os.environ["REQUESTS_CA_BUNDLE"] = ""
        os.environ["SSL_CERT_FILE"] = ""
        os.environ["_IPO_SSL_DISABLED"] = "1"
        logger.info("已禁用 SSL 证书验证（公司代理环境）")
    except Exception as e:
        logger.warning(f"禁用 SSL 验证失败: {e}")


class LocalEmbeddingFallback:
    def __init__(self) -> None:
        self._model: Any = None
        self._model_name: str = settings.llm.fallback_embedding_model
        self._cache_dir: str = os.path.expanduser(settings.llm.fallback_embedding_cache)
        self._dim: int | None = None
        self._available: bool | None = None
        self._loading: bool = False

    @property
    def available(self) -> bool | None:
        return self._available

    @property
    def dimension(self) -> int | None:
        return self._dim

    def _download_via_modelscope(self, model_dir: Path) -> bool:
        ms_model_id = _MODELSCOPE_MODELS.get(self._model_name)
        if not ms_model_id:
            logger.info(f"ModelScope 无对应模型映射: {self._model_name}，跳过")
            return False

        try:
            from modelscope import snapshot_download

            _disable_ssl_verify()
            logger.info(f"[ModelScope] 下载模型: {ms_model_id} -> {model_dir}")
            snapshot_download(ms_model_id, cache_dir=str(model_dir))
            if _is_valid_model_dir(model_dir):
                logger.info(f"[ModelScope] 下载完成: {model_dir}")
                return True
            logger.warning(f"[ModelScope] 下载完成但模型目录不完整: {model_dir}")
            return False
        except ImportError:
            logger.warning("modelscope 未安装，跳过 ModelScope 下载源")
            return False
        except Exception as e:
            logger.warning(f"[ModelScope] 下载失败: {e}")
            return False

    def _download_via_hf(self, model_dir: Path) -> bool:
        mirror = settings.llm.fallback_embedding_mirror
        try:
            from huggingface_hub import snapshot_download

            _disable_ssl_verify()
            kwargs: dict[str, Any] = {
                "repo_id": self._model_name,
                "local_dir": str(model_dir),
            }
            if mirror:
                kwargs["endpoint"] = mirror
                logger.info(f"[HuggingFace 镜像] 下载模型: {self._model_name} (mirror={mirror}) -> {model_dir}")
            else:
                logger.info(f"[HuggingFace] 下载模型: {self._model_name} -> {model_dir}")

            snapshot_download(**kwargs)
            if _is_valid_model_dir(model_dir):
                logger.info(f"[HuggingFace] 下载完成: {model_dir}")
                return True
            logger.warning(f"[HuggingFace] 下载完成但模型目录不完整: {model_dir}")
            return False
        except ImportError:
            logger.warning("huggingface_hub 未安装，跳过 HuggingFace 下载源")
            return False
        except Exception as e:
            logger.warning(f"[HuggingFace] 下载失败: {e}")
            return False

    def _download_model(self, model_dir: Path) -> bool:
        ms_dir = model_dir / "modelscope"
        hf_dir = model_dir / "huggingface"

        try:
            if self._download_via_modelscope(ms_dir):
                return True
        except Exception:
            pass
        if ms_dir.exists():
            logger.info("清理 ModelScope 残留文件")
            shutil.rmtree(ms_dir, ignore_errors=True)

        try:
            if self._download_via_hf(hf_dir):
                return True
        except Exception:
            pass
        if hf_dir.exists():
            logger.info("清理 HuggingFace 残留文件")
            shutil.rmtree(hf_dir, ignore_errors=True)

        logger.error("所有下载源均失败，无法获取 fallback embedding 模型")
        return False

    def _patch_model_dir(self, model_path: Path) -> None:
        pooling_dir = model_path / "1_Pooling"
        pooling_config = pooling_dir / "config.json"
        if pooling_dir.exists() and pooling_config.exists():
            return

        transformer_config = model_path / "config.json"
        if not transformer_config.exists():
            return

        try:
            import json
            with open(transformer_config, encoding="utf-8") as f:
                cfg = json.load(f)
            hidden_size = cfg.get("hidden_size") or cfg.get("d_model")
            if not hidden_size:
                return

            pooling_dir.mkdir(parents=True, exist_ok=True)
            if not pooling_config.exists():
                with open(pooling_config, "w", encoding="utf-8") as f:
                    json.dump({
                        "word_embedding_dimension": hidden_size,
                        "embedding_dimension": hidden_size,
                        "pooling_mode_cls_token": True,
                        "pooling_mode_mean_tokens": False,
                        "pooling_mode_max_tokens": False,
                        "pooling_mode_mean_sqrt_len_tokens": False,
                        "pooling_mode_weightedmean_tokens": False,
                        "pooling_mode_lasttoken": False,
                        "include_prompt": True,
                    }, f, indent=2)
                logger.info(f"已自动生成 1_Pooling/config.json (dim={hidden_size})")

            normalize_dir = model_path / "2_Normalize"
            normalize_config = normalize_dir / "config.json"
            if not normalize_dir.exists():
                normalize_dir.mkdir(parents=True, exist_ok=True)
            if not normalize_config.exists():
                with open(normalize_config, "w", encoding="utf-8") as f:
                    json.dump({"normalize": True}, f, indent=2)
                logger.info("已自动生成 2_Normalize/config.json")

        except Exception as e:
            logger.warning(f"自动补丁模型配置失败: {e}")

    def _find_valid_model_path(self, cache_root: Path) -> Path | None:
        if _is_valid_model_dir(cache_root):
            return cache_root
        for subdir in ("modelscope", "huggingface"):
            candidate = cache_root / subdir
            if _is_valid_model_dir(candidate):
                return candidate
            # ModelScope nests under models/<id>/snapshots/<rev>/
            if candidate.exists():
                for cfg in candidate.rglob("config.json"):
                    parent = cfg.parent
                    if _is_valid_model_dir(parent):
                        return parent
        return None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return

        if self._available is False:
            return

        if self._loading:
            return

        self._loading = True

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.error(
                "sentence-transformers 未安装，无法使用本地 fallback embedding。"
                "请运行: pip install sentence-transformers"
            )
            self._available = False
            self._loading = False
            return

        try:
            cache_path = Path(self._cache_dir)
            cache_path.mkdir(parents=True, exist_ok=True)

            model_path = self._find_valid_model_path(cache_path)

            if model_path is not None:
                logger.info(f"从本地缓存加载 fallback embedding 模型: {model_path}")
            else:
                if not self._download_model(cache_path):
                    self._available = False
                    self._loading = False
                    return
                model_path = self._find_valid_model_path(cache_path)
                if model_path is None:
                    logger.error("下载完成但找不到有效模型文件")
                    self._available = False
                    self._loading = False
                    return

            self._patch_model_dir(model_path)

            self._model = SentenceTransformer(str(model_path), device="cpu")
            test_emb = self._model.encode(["test"], normalize_embeddings=True)
            self._dim = test_emb.shape[1]
            self._available = True
            logger.info(f"本地 fallback embedding 模型就绪, dim={self._dim}")

        except Exception as e:
            logger.error(f"加载本地 fallback embedding 模型失败: {e}")
            self._available = False
            self._model = None
        finally:
            self._loading = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()

        if not self._available or self._model is None:
            raise RuntimeError(
                f"本地 fallback embedding 模型不可用 (model={self._model_name})"
            )

        import asyncio

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            self._encode_batch,
            texts,
        )

        return embeddings

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        batch_size = 64
        all_embs: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embs = self._model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=len(batch),
            )
            all_embs.extend(embs.tolist())

        return all_embs