import os
import json

from typing import List, Dict, Any
from redis import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MEMORY_TTL_SECONDS = int(os.getenv("MEMORY_TTL_SECONDS", "21600"))  # 6h default

r = Redis.from_url(REDIS_URL, decode_responses=True)


def _history_key(session_id: str) -> str:
    return f"cookbook:{session_id}:history"


def _constraints_key(session_id: str) -> str:
    return f"cookbook:{session_id}:constraints"


def touch_session(session_id: str) -> None:
    # Продлеваем TTL, чтобы данные жили пока вкладка активна
    r.expire(_history_key(session_id), MEMORY_TTL_SECONDS)
    r.expire(_constraints_key(session_id), MEMORY_TTL_SECONDS)


def append_history(session_id: str, role: str, content: str, limit: int = 3) -> None:

    key = _history_key(session_id)
    item = json.dumps({"role": role, "content": content}, ensure_ascii=False)

    pipe = r.pipeline()
    pipe.rpush(key, item)
    pipe.ltrim(key, -limit, -1)
    pipe.expire(key, MEMORY_TTL_SECONDS)
    pipe.execute()


def get_history(session_id: str) -> List[Dict[str, str]]:
    key = _history_key(session_id)
    raw = r.lrange(key, 0, -1)
    out = []
    for s in raw:
        try:
            out.append(json.loads(s))
        except Exception:
            continue
    return out


def get_constraints(session_id: str) -> Dict[str, Any]:
    key = _constraints_key(session_id)
    data = r.get(key)
    if not data:
        return {"allergies": [], "intolerances": [], "avoid": []}
    try:
        return json.loads(data)
    except Exception:
        return {"allergies": [], "intolerances": [], "avoid": []}


def set_constraints(session_id: str, constraints: Dict[str, Any]) -> None:
    key = _constraints_key(session_id)
    r.set(key, json.dumps(constraints, ensure_ascii=False))
    r.expire(key, MEMORY_TTL_SECONDS)


def merge_constraints(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:

    def norm_list(x):
        if not x:
            return []
        if isinstance(x, list):
            return [str(i).strip() for i in x if str(i).strip()]
        return []

    merged = {}
    for k in ["allergies", "intolerances", "avoid"]:
        merged[k] = sorted(set(norm_list(old.get(k)) + norm_list(new.get(k))))
    return merged
