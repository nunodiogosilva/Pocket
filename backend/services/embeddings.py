import threading
from functools import lru_cache
import numpy as np
from model2vec import StaticModel
from config import EMBEDDING_MODEL

# model2vec reconfigures its shared tokenizer on every encode() call, so calls must not overlap
_encode_lock = threading.Lock()


@lru_cache(maxsize=1)
def get_model() -> StaticModel:
    # Static (lookup-table) embeddings: ~30 MB and no PyTorch, so it fits the Pi's RAM budget
    return StaticModel.from_pretrained(EMBEDDING_MODEL)


def embed(texts: list[str]) -> np.ndarray:
    """Return one L2-normalised float32 vector per text."""
    model = get_model()
    with _encode_lock:
        return model.encode(texts).astype(np.float32, copy=False)
