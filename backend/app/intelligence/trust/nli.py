"""An entailment model as a third, non-LLM opinion on a claim (v4 Phase 2).

B1 showed what neither existing check could do: credit a conclusion drawn across two documents.
The lexical checker supports a sentence from one line at a time; the model verifier is the same
small model that wrote the claim. A natural-language-inference model reads the cited lines together
as a premise and the claim as a hypothesis and says entailment, neutral or contradiction - trained
for exactly that question, and independent of the model that reasoned.

`cross-encoder/nli-deberta-v3-xsmall` (Apache-2.0), its 87 MB int8 ONNX export, on CPU through
onnxruntime and the `tokenizers` library that the `media` extra already installs - no PyTorch.
Downloaded once into `.agent/media-cache/models/`, a volume, so a redeploy does not fetch it again.
Off when `NLI_MODEL` is empty, and absent (never failing a check) when the packages or the download
are not available.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.common import JarvisModel

log = get_logger(__name__)

ONNX_FILE = "onnx/model_quint8_avx2.onnx"
MAX_TOKENS = 512


class Entailment(JarvisModel):
    entailment: float
    neutral: float
    contradiction: float

    @property
    def label(self) -> str:
        best = max(
            ("entailment", self.entailment),
            ("neutral", self.neutral),
            ("contradiction", self.contradiction),
            key=lambda pair: pair[1],
        )
        return best[0]


class _Model:
    def __init__(self, session: Any, tokenizer: Any, labels: dict[int, str]) -> None:
        self._session = session
        self._tokenizer = tokenizer
        self._labels = labels
        self._inputs = {i.name for i in session.get_inputs()}

    def __call__(self, premise: str, hypothesis: str) -> Entailment:
        import numpy as np

        encoded = self._tokenizer.encode(premise, hypothesis)
        feed = {
            "input_ids": np.array([encoded.ids], dtype=np.int64),
            "attention_mask": np.array([encoded.attention_mask], dtype=np.int64),
        }
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.array([encoded.type_ids], dtype=np.int64)
        logits = self._session.run(None, feed)[0][0]
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        named = {self._labels[i]: float(p) for i, p in enumerate(probs)}
        return Entailment(
            entailment=named.get("entailment", 0.0),
            neutral=named.get("neutral", 0.0),
            contradiction=named.get("contradiction", 0.0),
        )


@lru_cache(maxsize=1)
def _load(repo: str) -> _Model | None:
    try:
        import json

        import onnxruntime
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
    except ImportError:
        log.info("nli_unavailable", reason="onnxruntime, tokenizers or huggingface_hub missing")
        return None
    cache = get_settings().agent_dir / "media-cache" / "models"
    try:
        model = hf_hub_download(repo, ONNX_FILE, cache_dir=cache)
        tokenizer_file = hf_hub_download(repo, "tokenizer.json", cache_dir=cache)
        config = json.loads(Path(hf_hub_download(repo, "config.json", cache_dir=cache)).read_text())
    except Exception as exc:  # noqa: BLE001 - offline, or the repository moved
        log.warning("nli_download_failed", repo=repo, error=f"{type(exc).__name__}: {exc}")
        return None
    tokenizer = Tokenizer.from_file(tokenizer_file)
    tokenizer.enable_truncation(MAX_TOKENS)
    labels = {int(k): str(v).lower() for k, v in config.get("id2label", {}).items()}
    session = onnxruntime.InferenceSession(model, providers=["CPUExecutionProvider"])
    log.info("nli_loaded", repo=repo)
    return _Model(session, tokenizer, labels)


async def entailment(premise: str, hypothesis: str) -> Entailment | None:
    """How the cited text bears on the claim, or None when no NLI model is available."""
    repo = get_settings().nli_model
    if not repo or not premise.strip() or not hypothesis.strip():
        return None
    model = await asyncio.to_thread(_load, repo)
    if model is None:
        return None
    return await asyncio.to_thread(model, premise, hypothesis)
