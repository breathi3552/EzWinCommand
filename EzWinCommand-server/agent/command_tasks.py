"""异步命令任务持久化与单 worker 执行服务。"""
from __future__ import annotations
import json, os, tempfile, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

TERMINAL = {"succeeded", "failed"}

def _now() -> datetime: return datetime.now(timezone.utc)
def _iso(d: datetime) -> str: return d.astimezone(timezone.utc).isoformat()
def _dt(s: str) -> datetime: return datetime.fromisoformat(s)

@dataclass
class TaskRecord:
    command_id: str
    owner_digest: str
    action: str
    sub_action: str | None
    params: dict[str, Any]
    status: str
    message: str | None
    data: dict[str, Any] | None
    error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    def to_dict(self):
        d = asdict(self)
        for k in ("created_at", "updated_at", "expires_at"): d[k] = _iso(d[k])
        return d
    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            raise ValueError("invalid task record")
        d = dict(d)
        for k in ("created_at", "updated_at", "expires_at"): d[k] = _dt(d[k])
        params = d.get("params")
        if params is None:
            params = {"sub_action": d.get("sub_action")} if d.get("sub_action") is not None else {}
        if not isinstance(params, dict):
            raise ValueError("invalid task params")
        d["params"] = params
        return cls(**d)

class CommandTaskStore:
    def __init__(self, path: str | Path, ttl_seconds: int = 600):
        self.path = Path(path); self.ttl = ttl_seconds; self._lock = threading.RLock(); self._records: dict[str,TaskRecord] = {}
        self._load(); self.recover(_now()); self.purge_expired(_now())
    def _load(self):
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}
                if not isinstance(raw, dict): raise ValueError("invalid task file")
                self._records = {}
                for key, value in raw.items():
                    try:
                        record = TaskRecord.from_dict(value)
                        if record.command_id == key: self._records[key] = record
                    except (KeyError, TypeError, ValueError, OverflowError):
                        continue
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                self._records = {}
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd,tmp = tempfile.mkstemp(prefix=self.path.name, dir=str(self.path.parent)); os.close(fd)
        try:
            Path(tmp).write_text(json.dumps({k:v.to_dict() for k,v in self._records.items()}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        finally:
            try: os.unlink(tmp)
            except OSError: pass
    def submit(self, owner_digest: str, action: str, params: dict[str,Any]):
        sub = params.get("sub_action") if isinstance(params,dict) else None; now = _now()
        with self._lock:
            for r in self._records.values():
                if r.action == action and r.sub_action == sub and r.status not in TERMINAL:
                    return r, False
            safe_params = dict(params) if isinstance(params, dict) else {}
            r = TaskRecord("cmd_"+uuid.uuid4().hex, owner_digest, action, sub, safe_params, "queued", None, None, None, now, now, now+timedelta(seconds=self.ttl))
            self._records[r.command_id] = r; self._save(); return r, True
    def get_for_owner(self, command_id, owner_digest):
        with self._lock:
            r=self._records.get(command_id); return r if r and r.owner_digest == owner_digest and (r.status not in TERMINAL or r.expires_at > _now()) else None
    def update(self, command_id: str, **changes):
        with self._lock:
            r=self._records[command_id]
            for k,v in changes.items(): setattr(r,k,v)
            r.updated_at = _now()
            if r.status in TERMINAL: r.expires_at = r.updated_at + timedelta(seconds=self.ttl)
            self._save(); return r
    def recover(self, now):
        with self._lock:
            for r in list(self._records.values()):
                if r.status == "running":
                    r.status="failed"; r.error={"code":"service_restarted","message":"服务重启导致任务未完成"}; r.message=r.error["message"]; r.updated_at=now; r.expires_at=now+timedelta(seconds=self.ttl)
                elif r.status == "queued":
                    continue
            self._save()
    def purge_expired(self, now):
        with self._lock:
            old=len(self._records); self._records={k:v for k,v in self._records.items() if v.status not in TERMINAL or v.expires_at>now}; n=old-len(self._records)
            if n: self._save()
            return n

class AsyncCommandService:
    def __init__(self, dispatcher, store: CommandTaskStore):
        self.dispatcher=dispatcher; self.store=store; self.executor=ThreadPoolExecutor(max_workers=1); self._enqueue_queued()
    def _enqueue_queued(self):
        for r in list(self.store._records.values()):
            if r.status == "queued": self.executor.submit(self._run, r.command_id, r.action, r.params)
    def submit(self, owner_digest, action, params):
        r,new=self.store.submit(owner_digest,action,params)
        if new: self.executor.submit(self._run,r.command_id,action,params)
        return r,new
    def _run(self, cid, action, params):
        try:
            self.store.update(cid,status="running")
            result=self.dispatcher.execute(action,params)
            if result.success: self.store.update(cid,status="succeeded",message=result.message,data=result.data,error=None)
            else: self.store.update(cid,status="failed",message=result.message,error={"code":"command_failed","message":result.message})
        except Exception as exc:
            self.store.update(cid,status="failed",message="命令执行失败",error={"code":"command_exception","message":"命令执行失败"})
    def get(self, command_id, owner_digest): return self.store.get_for_owner(command_id,owner_digest)
