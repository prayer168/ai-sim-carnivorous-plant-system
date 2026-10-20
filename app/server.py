from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
import csv
import io
import zipfile
import math
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("AI_SIM_DB", ROOT / "data" / "ai_sim.sqlite3"))
HOST = os.environ.get("AI_SIM_HOST", "127.0.0.1")
PORT = int(os.environ.get("AI_SIM_PORT", "8000"))
DB_LOCK = threading.RLock()
ROLES = {
    "teacher-demo-token": {"role": "teacher", "class_id": "C01"},
    "student-g01-demo-token": {"role": "student", "class_id": "C01", "group_id": "G01", "student_id": "S001", "zone_ids": ["Z01"]},
    "student-g02-demo-token": {"role": "student", "class_id": "C01", "group_id": "G02", "student_id": "S002", "zone_ids": ["Z02"]},
    "research-demo-token": {"role": "researcher", "class_id": "C01"},
    "device-demo-token": {"role": "device", "class_id": "C01"},
    "teacher-other-class-demo-token": {"role": "teacher", "class_id": "C02"},
}
QUALITY = {"valid", "missing", "out_of_range", "suspect", "uncalibrated", "duplicate", "clock_skew"}
MATRIX = {f"M{i:02d}" for i in range(1, 26)}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_utc()).astimezone(timezone.utc).isoformat()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def initialize() -> None:
    with DB_LOCK, connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS zones(id TEXT PRIMARY KEY, level_index INTEGER NOT NULL, position_index INTEGER NOT NULL, environment_cluster_id TEXT NOT NULL, light_group_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, zone_id TEXT NOT NULL REFERENCES zones(id), installed_at TEXT NOT NULL, removed_at TEXT, token_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS readings(id TEXT PRIMARY KEY, device_id TEXT NOT NULL REFERENCES devices(id), zone_id TEXT NOT NULL REFERENCES zones(id), observed_at TEXT NOT NULL, received_at TEXT NOT NULL, metric TEXT NOT NULL, value REAL, unit TEXT NOT NULL, quality_flag TEXT NOT NULL, calibration_ref TEXT, idempotency_key TEXT NOT NULL, payload_hash TEXT NOT NULL, UNIQUE(device_id,idempotency_key));
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, class_id TEXT NOT NULL, matrix_code TEXT NOT NULL, title TEXT NOT NULL, prompt TEXT NOT NULL, prompt_version TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS responses(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), student_id TEXT NOT NULL, group_id TEXT NOT NULL, phase TEXT NOT NULL, version_no INTEGER NOT NULL, content TEXT NOT NULL, submitted_at TEXT NOT NULL, UNIQUE(task_id,student_id,phase,version_no));
        CREATE TABLE IF NOT EXISTS consents(student_id TEXT NOT NULL, scope TEXT NOT NULL, permission INTEGER NOT NULL, consent_version TEXT NOT NULL, PRIMARY KEY(student_id,scope));
        CREATE TABLE IF NOT EXISTS scores(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, student_id TEXT NOT NULL, teacher_id TEXT NOT NULL, rubric TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS annotations(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, student_id TEXT NOT NULL, zone_id TEXT NOT NULL, plant_id TEXT NOT NULL, captured_at TEXT NOT NULL, sha256 TEXT NOT NULL, device_category TEXT NOT NULL, license TEXT NOT NULL, labels TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, actor_role TEXT NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL, target_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_at TEXT NOT NULL, details TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, task_id TEXT NOT NULL REFERENCES tasks(id), student_id TEXT NOT NULL, group_id TEXT NOT NULL, zone_id TEXT NOT NULL REFERENCES zones(id), text TEXT NOT NULL, media_id TEXT, original_version_id TEXT, version_no INTEGER NOT NULL, captured_at TEXT NOT NULL, dataset_type TEXT NOT NULL DEFAULT 'synthetic_demo_only', UNIQUE(project_id,student_id,version_no));
        CREATE TABLE IF NOT EXISTS interventions(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, student_id TEXT NOT NULL, student_pre_ai_version_id TEXT NOT NULL, prompt_template_version TEXT NOT NULL, model_provider TEXT NOT NULL, request_at TEXT NOT NULL, assistant_question TEXT NOT NULL, uncertainty TEXT NOT NULL, safety_flags TEXT NOT NULL, human_reviewed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS intervention_followups(id TEXT PRIMARY KEY, intervention_id TEXT NOT NULL REFERENCES interventions(id), student_revision_version_id TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS analyses(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, student_id TEXT NOT NULL, reading_ids TEXT NOT NULL, chart_config TEXT NOT NULL, explanation TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cers(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, student_id TEXT NOT NULL, claim TEXT NOT NULL, reasoning TEXT NOT NULL, version_no INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(task_id,student_id,version_no));
        CREATE TABLE IF NOT EXISTS cer_evidence(cer_id TEXT NOT NULL REFERENCES cers(id), evidence_type TEXT NOT NULL, evidence_id TEXT NOT NULL, PRIMARY KEY(cer_id,evidence_type,evidence_id));
        CREATE TABLE IF NOT EXISTS research_exports(id TEXT PRIMARY KEY, file_path TEXT NOT NULL, manifest TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS student_profiles(student_id TEXT PRIMARY KEY, class_id TEXT NOT NULL, group_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS zone_group_access(zone_id TEXT NOT NULL REFERENCES zones(id), group_id TEXT NOT NULL, PRIMARY KEY(zone_id,group_id));
        CREATE TRIGGER IF NOT EXISTS readings_immutable_update BEFORE UPDATE ON readings BEGIN SELECT RAISE(ABORT, 'sensor readings are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS readings_immutable_delete BEFORE DELETE ON readings BEGIN SELECT RAISE(ABORT, 'sensor readings are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS pre_ai_immutable_update BEFORE UPDATE ON responses WHEN OLD.phase='pre_ai' BEGIN SELECT RAISE(ABORT, 'pre_ai response is immutable'); END;
        CREATE TRIGGER IF NOT EXISTS pre_ai_immutable_delete BEFORE DELETE ON responses WHEN OLD.phase='pre_ai' BEGIN SELECT RAISE(ABORT, 'pre_ai response is immutable'); END;
        CREATE TRIGGER IF NOT EXISTS observations_immutable_update BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS observations_immutable_delete BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;
        CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
        """)
        migrations=ROOT/"db"/"migrations"
        for migration in sorted(migrations.glob("*.sql")) if migrations.exists() else []:
            if c.execute("SELECT 1 FROM schema_migrations WHERE version=?",(migration.name,)).fetchone():
                continue
            c.executescript(migration.read_text(encoding="utf-8"))
            c.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(?,?)",(migration.name,iso()))
        for i in range(1, 10):
            zone = f"Z{i:02d}"
            c.execute("INSERT OR IGNORE INTO zones VALUES(?,?,?,?,?)", (zone, (i-1)//3+1, (i-1)%3+1, "ENV-SHARED-01", f"LIGHT-L{(i-1)//3+1}"))
            c.execute("INSERT OR IGNORE INTO devices(id,zone_id,installed_at,removed_at,token_hash) VALUES(?,?,?,?,?)", (f"DEV-{zone}", zone, iso(), None, hashlib.sha256(b"device-demo-token").hexdigest()))
        for sid, scope, permission in (("S001", "research", 1), ("S001", "teaching", 1), ("S002", "research", 0), ("S002", "teaching", 1)):
            c.execute("INSERT OR IGNORE INTO consents VALUES(?,?,?,?)", (sid, scope, permission, "synthetic-v1"))
        c.execute("INSERT OR IGNORE INTO student_profiles VALUES('S001','C01','G01')")
        c.execute("INSERT OR IGNORE INTO student_profiles VALUES('S002','C01','G02')")
        for i in range(1,10): c.execute("INSERT OR IGNORE INTO zone_group_access VALUES(?,?)",(f"Z{i:02d}","G01" if i==1 else "G02" if i==2 else "SHARED"))
        c.execute("INSERT OR IGNORE INTO tasks VALUES(?,?,?,?,?,?,?)", ("TASK-DEMO", "C01", "M01", "毛氈苔黏液觀察", "記錄黏液變化，提出一個可以用資料檢驗的問題。", "v1.1-demo", iso()))


def audit(c: sqlite3.Connection, actor: dict, action: str, target: str, trace: str, details: dict | None = None) -> None:
    c.execute("INSERT INTO audit VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), actor["role"], actor.get("student_id", actor["role"]), action, target, trace, iso(), json.dumps(details or {}, ensure_ascii=False)))


def can_access_student(actor: dict, student_id: str, group_id: str | None = None) -> bool:
    if actor["role"] == "teacher": return actor.get("class_id") == "C01"
    if actor["role"] == "researcher": return True
    return actor.get("student_id") == student_id or (group_id is not None and actor.get("group_id") == group_id)


def can_access_zone(actor: dict, zone_id: str) -> bool:
    return actor["role"] != "student" or zone_id in actor.get("zone_ids", [])


def safe_export_text(value: str) -> str:
    # Free-form child text may contain identifying details; exports omit it pending a reviewed redaction workflow.
    return "[redacted_free_text]"


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class Handler(BaseHTTPRequestHandler):
    server_version = "AISIM/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def send_json(self, status: int, obj: dict) -> None:
        data = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def actor(self, *allowed: str) -> dict:
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        actor = ROLES.get(token)
        if not actor:
            raise APIError(401, "unauthorized", "請使用示範角色登入")
        if allowed and actor["role"] not in allowed:
            raise APIError(403, "forbidden", "此角色無權執行操作")
        return actor

    def body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 1_000_000:
                raise APIError(422, "payload_too_large", "請縮小請求內容")
            obj = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(obj, dict):
                raise ValueError()
            return obj
        except APIError:
            raise
        except (ValueError, json.JSONDecodeError):
            raise APIError(422, "invalid_json", "請提供有效 JSON 物件")

    def handle_api(self) -> None:
        trace = self.headers.get("X-Trace-Id") or str(uuid.uuid4())
        try:
            parsed = urlparse(self.path)
            path, method = parsed.path, self.command
            q = parse_qs(parsed.query)
            if path == "/api/v1/health" and method == "GET":
                return self.send_json(200, {"status": "ok", "mode": "synthetic-local", "external_ai": False})
            if path == "/api/v1/workspace" and method == "GET":
                actor=self.actor("student","teacher")
                if actor["role"]=="teacher" and actor["class_id"]!="C01": raise APIError(403,"forbidden","此教師未授權此班級")
                sid=q.get("student_id",[actor.get("student_id","S001")])[0]
                if actor["role"]=="student" and not can_access_student(actor,sid): raise APIError(403,"forbidden","不可存取其他學生工作台")
                with connect() as c:
                    observations=[dict(x) for x in c.execute("SELECT id,task_id,zone_id,original_version_id,version_no,captured_at,dataset_type FROM observations WHERE student_id=? ORDER BY captured_at",(sid,))]
                    responses=[dict(x) for x in c.execute("SELECT id,task_id,phase,version_no,content,submitted_at FROM responses WHERE student_id=? ORDER BY submitted_at",(sid,))]
                    interventions=[dict(x) for x in c.execute("SELECT id,task_id,prompt_template_version,model_provider,request_at,assistant_question,uncertainty,human_reviewed FROM interventions WHERE student_id=? ORDER BY request_at",(sid,))]
                    analyses=[dict(x) for x in c.execute("SELECT id,task_id,reading_ids,chart_config,created_at FROM analyses WHERE student_id=? ORDER BY created_at",(sid,))]
                    cers=[dict(x) for x in c.execute("SELECT id,task_id,version_no,created_at FROM cers WHERE student_id=? ORDER BY created_at",(sid,))]
                    assessments=[dict(x) for x in c.execute("SELECT task_id,rubric,created_at FROM scores WHERE student_id=? ORDER BY created_at",(sid,))]
                return self.send_json(200,{"student_pseudonym":sid,"dataset_type":"synthetic_demo_only","stages":{"observation":observations,"ai_intervention":interventions,"student_responses":responses,"analysis":analyses,"cer":cers,"assessment":assessments},"refresh_restores_work":True})
            if path == "/api/v1/openapi.json" and method == "GET":
                return self.send_json(200, {"openapi": "3.1.0", "info": {"title": "AI-SIM demo", "version": "1.1.0"}, "paths": {"/api/v1/zones": {"get": {}}, "/api/v1/readings": {"get": {}}, "/api/v1/ingest/readings": {"post": {}}, "/api/v1/tasks": {"post": {}}, "/api/v1/responses": {"post": {}}, "/api/v1/ai/hints": {"post": {}}, "/api/v1/cer/feedback": {"post": {}}, "/api/v1/rubric-scores": {"post": {}}, "/api/v1/research/exports": {"post": {}}}})
            if path == "/api/v1/zones" and method == "GET":
                actor = self.actor("teacher", "student", "researcher")
                if actor["role"]=="teacher" and actor["class_id"]!="C01": raise APIError(403,"forbidden","此教師未授權此班級")
                with connect() as c:
                    zones = [dict(r) for r in c.execute("SELECT * FROM zones ORDER BY id")]
                return self.send_json(200, {"zones": zones, "shared_environment_notice": "共享環境與燈源群組不可視為獨立實驗複本"})
            if path == "/api/v1/readings" and method == "GET":
                actor = self.actor("teacher", "student")
                if actor["role"]=="teacher" and actor["class_id"]!="C01": raise APIError(403,"forbidden","此教師未授權此班級")
                zone = q.get("zone_id", [None])[0]
                if actor["role"]=="student" and zone and not can_access_zone(actor,zone): raise APIError(403,"forbidden","不可讀取其他小組區域測值")
                with connect() as c:
                    if actor["role"] == "student":
                        allowed=actor["zone_ids"]
                        marks=",".join("?" for _ in allowed)
                        rows = c.execute(f"SELECT r.* FROM readings r WHERE r.zone_id IN ({marks}) AND (? IS NULL OR r.zone_id=?) ORDER BY r.observed_at DESC LIMIT 500", (*allowed,zone,zone)).fetchall()
                    else:
                        rows = c.execute("SELECT * FROM readings WHERE (? IS NULL OR zone_id=?) ORDER BY observed_at DESC LIMIT 500", (zone, zone)).fetchall()
                return self.send_json(200, {"readings": [dict(r) for r in rows], "timezone": "UTC (display in Asia/Taipei)", "missing_values_are_null": True})
            if path == "/api/v1/observations" and method == "POST":
                actor = self.actor("student")
                data = self.body()
                task_id = data.get("task_id", "TASK-DEMO")
                zone_id = data.get("zone_id", "Z01")
                text = data.get("text", "")
                if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                    raise APIError(422, "invalid_observation", "觀察文字必填且不得超過 4000 字")
                with DB_LOCK, connect() as c:
                    task = c.execute("SELECT id FROM tasks WHERE id=? AND class_id=?", (task_id, actor["class_id"])).fetchone()
                    zone = c.execute("SELECT id FROM zones WHERE id=?", (zone_id,)).fetchone()
                    if not task or not zone: raise APIError(404, "observation_scope_not_found", "找不到任務或區域")
                    previous = c.execute("SELECT * FROM observations WHERE project_id=? AND student_id=? ORDER BY version_no DESC LIMIT 1", (data.get("project_id", "P-DEMO-001"), actor["student_id"])).fetchone()
                    if data.get("original_version_id"):
                        if not previous or data["original_version_id"] != previous["id"]:
                            raise APIError(409, "version_conflict", "原稿版本不符；請以最新版本為基礎追加更正")
                    elif previous:
                        raise APIError(409, "immutable_original", "原始觀察已鎖定；更正需附 original_version_id")
                    oid = data.get("observation_id") or f"O-{uuid.uuid4().hex[:12].upper()}"
                    version = (previous["version_no"] if previous else 0) + 1
                    original = data.get("original_version_id") or oid
                    c.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (oid, data.get("project_id", "P-DEMO-001"), task_id, actor["student_id"], actor["group_id"], zone_id, text, data.get("media_id"), original, version, iso(), "synthetic_demo_only"))
                    audit(c, actor, "observation.append", oid, trace, {"version": version, "original_version_id": original})
                return self.send_json(201, {"observation_id": oid, "original_version_id": original, "version": version, "dataset_type": "synthetic_demo_only", "trace_id": trace})
            if path == "/api/v1/observations" and method == "GET":
                actor = self.actor("teacher", "student")
                student_id = q.get("student_id", [actor.get("student_id")])[0]
                if actor["role"] == "student" and not can_access_student(actor, student_id): raise APIError(403, "forbidden", "不可查詢其他學生觀察")
                if actor["role"]=="teacher" and actor["class_id"]!="C01": raise APIError(403,"forbidden","此教師未授權此班級")
                with connect() as c:
                    rows = c.execute("SELECT * FROM observations WHERE student_id=? ORDER BY captured_at", (student_id,)).fetchall()
                return self.send_json(200, {"observations": [dict(r) for r in rows]})
            if path == "/api/v1/devices/status" and method == "GET":
                self.actor("teacher", "student")
                with connect() as c:
                    rows = [dict(r) for r in c.execute("SELECT d.id AS device_id,d.zone_id,d.expected_interval_seconds,d.last_seen_at FROM devices d ORDER BY d.zone_id")]
                for row in rows:
                    last = datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None
                    row["status"] = "offline" if last is None or (now_utc()-last).total_seconds() > row["expected_interval_seconds"] else "online"
                    row["quality_notice"] = "缺測不得以 0 代替" if row["status"] == "offline" else None
                return self.send_json(200, {"devices": rows})
            if path == "/api/v1/analyses" and method == "POST":
                actor = self.actor("student")
                data = self.body()
                ids = data.get("reading_ids", [])
                if not isinstance(ids, list) or len(ids) < 2 or len(ids) > 100 or any(not isinstance(x,str) for x in ids) or len(set(ids)) != len(ids):
                    raise APIError(422, "invalid_analysis_sources", "分析至少引用兩筆不同的 reading_id")
                with DB_LOCK, connect() as c:
                    task=c.execute("SELECT id FROM tasks WHERE id=? AND class_id=?",(data.get("task_id","TASK-DEMO"),actor["class_id"])).fetchone()
                    if not task: raise APIError(404,"task_not_found","找不到授權任務")
                    marks = ",".join("?" for _ in ids)
                    rows = c.execute(f"SELECT * FROM readings WHERE id IN ({marks})", ids).fetchall()
                    if len(rows) != len(ids): raise APIError(422, "unknown_evidence", "分析引用包含不存在的 reading_id")
                    if any(not can_access_zone(actor,r["zone_id"]) for r in rows): raise APIError(403,"forbidden_evidence","分析不可引用其他小組區域讀值")
                    if len({(r["metric"],r["unit"]) for r in rows}) != 1 or any(r["value"] is None or r["quality_flag"]!="valid" for r in rows):
                        raise APIError(422,"incomparable_analysis_sources","圖表需引用同一指標/單位且品質 valid 的非缺測讀值")
                    aid = data.get("analysis_id") or f"A-{uuid.uuid4().hex[:12].upper()}"
                    c.execute("INSERT INTO analyses VALUES(?,?,?,?,?,?,?,?)", (aid, data.get("task_id", "TASK-DEMO"), actor["student_id"], json.dumps(ids), json.dumps(data.get("chart_config", {"type":"line","x":"observed_at","y":"value","group":"metric"})), str(data.get("explanation", ""))[:2000], actor["student_id"], iso()))
                    audit(c, actor, "analysis.create", aid, trace, {"reading_ids": ids})
                return self.send_json(201, {"analysis_id": aid, "reading_ids": ids, "chart_spec":{"type":"line","x":"observed_at","y":"value","metric":rows[0]["metric"],"unit":rows[0]["unit"]}, "points": [{"reading_id": r["id"], "observed_at": r["observed_at"], "metric": r["metric"], "unit":r["unit"], "value": r["value"], "quality_flag": r["quality_flag"]} for r in sorted(rows,key=lambda r:r["observed_at"])], "trace_id": trace})
            if path == "/api/v1/cers" and method == "POST":
                actor = self.actor("student")
                data = self.body()
                ev = data.get("evidence", [])
                if not isinstance(ev, list) or not ev: raise APIError(422, "evidence_required", "CER 至少需引用 observation_id 或 reading_id")
                with DB_LOCK, connect() as c:
                    task=c.execute("SELECT id FROM tasks WHERE id=? AND class_id=?",(data.get("task_id","TASK-DEMO"),actor["class_id"])).fetchone()
                    if not task: raise APIError(404,"task_not_found","找不到授權任務")
                    resolved=[]
                    for item in ev:
                        if not isinstance(item, dict) or item.get("type") not in {"observation", "reading", "analysis"}:
                            raise APIError(422, "invalid_evidence", "證據類型必須是 observation、reading 或 analysis")
                        table = {"observation":"observations", "reading":"readings", "analysis":"analyses"}[item["type"]]
                        row = c.execute(f"SELECT * FROM {table} WHERE id=?", (item.get("id"),)).fetchone()
                        if not row: raise APIError(422, "unknown_evidence", f"找不到證據來源 {item.get('id')}")
                        if item["type"] == "observation" and not can_access_student(actor, row["student_id"], row["group_id"]): raise APIError(403, "forbidden_evidence", "不可引用其他學生的觀察")
                        if item["type"] == "analysis" and row["student_id"] != actor["student_id"]: raise APIError(403, "forbidden_evidence", "不可引用其他學生的分析")
                        if item["type"] == "reading":
                            if row["zone_id"] not in {f"Z{i:02d}" for i in range(1,10)} or not can_access_zone(actor,row["zone_id"]): raise APIError(403, "forbidden_evidence", "不可引用未授權區域讀值")
                            resolved.append({"type":"reading","id":row["id"],"observed_at":row["observed_at"],"metric":row["metric"],"value":row["value"],"quality_flag":row["quality_flag"],"light_group_id":c.execute("SELECT light_group_id FROM zones WHERE id=?",(row["zone_id"],)).fetchone()[0]})
                        else: resolved.append({"type":item["type"],"id":row["id"]})
                    previous=c.execute("SELECT MAX(version_no) FROM cers WHERE task_id=? AND student_id=?",(data.get("task_id","TASK-DEMO"),actor["student_id"])).fetchone()[0] or 0
                    version=previous+1; cid=data.get("cer_id") or f"CER-{uuid.uuid4().hex[:12].upper()}"
                    c.execute("INSERT INTO cers VALUES(?,?,?,?,?,?,?)",(cid,data.get("task_id","TASK-DEMO"),actor["student_id"],str(data.get("claim",""))[:2000],str(data.get("reasoning",""))[:4000],version,iso()))
                    c.executemany("INSERT INTO cer_evidence VALUES(?,?,?)",[(cid,x["type"],x["id"]) for x in ev])
                    audit(c,actor,"cer.submit",cid,trace,{"evidence_ids":[x["id"] for x in ev],"version":version})
                return self.send_json(201,{"cer_id":cid,"version":version,"resolved_evidence":resolved,"trace_id":trace})
            if path.startswith("/api/v1/analyses/") and method == "GET":
                actor=self.actor("teacher","student")
                aid=path.rsplit("/",1)[-1]
                with connect() as c:
                    row=c.execute("SELECT * FROM analyses WHERE id=?",(aid,)).fetchone()
                    if not row: raise APIError(404,"analysis_not_found","找不到分析")
                    ids=json.loads(row["reading_ids"]); marks=",".join("?" for _ in ids)
                    points=[dict(r) for r in c.execute(f"SELECT id AS reading_id,observed_at,metric,unit,value,quality_flag FROM readings WHERE id IN ({marks}) ORDER BY observed_at",ids)]
                if actor["role"]=="student" and row["student_id"]!=actor["student_id"]: raise APIError(403,"forbidden","不可存取其他學生分析")
                return self.send_json(200,{"analysis_id":aid,"reading_ids":ids,"chart_config":json.loads(row["chart_config"]),"chart_spec":{"type":"line","x":"observed_at","y":"value","metric":points[0]["metric"] if points else "","unit":points[0]["unit"] if points else ""},"points":points,"explanation":row["explanation"]})
            if path == "/api/v1/ingest/readings" and method == "POST":
                actor = self.actor("device")
                data = self.body()
                items = data.get("readings", [data])
                if not isinstance(items, list) or len(items) > 1000:
                    raise APIError(422, "invalid_readings", "readings 必須是最多 1000 筆的陣列")
                inserted, duplicates = [], 0
                batch_id=data.get("ingest_batch_id") or f"B-{uuid.uuid4().hex[:12].upper()}"
                with DB_LOCK, connect() as c:
                    for item in items:
                        zone, metric, idem = item.get("zone_id"), item.get("metric"), item.get("idempotency_key")
                        metric={"illuminance":"light","relative_humidity":"humidity"}.get(metric,metric)
                        if zone not in {f"Z{i:02d}" for i in range(1,10)} or metric not in {"temperature", "humidity", "light", "ph"} or not idem:
                            raise APIError(422, "invalid_reading", "zone_id、支援的 metric 與 idempotency_key 為必填")
                        value = item.get("value")
                        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                            raise APIError(422, "invalid_value", "value 必須為數字或 null")
                        quality = item.get("quality_flag", "valid" if value is not None else "missing")
                        if quality not in QUALITY:
                            raise APIError(422, "invalid_quality", "不支援的品質旗標")
                        device = c.execute("SELECT id FROM devices WHERE zone_id=? AND removed_at IS NULL", (zone,)).fetchone()
                        observed = item.get("observed_at", iso())
                        try:
                            dt = datetime.fromisoformat(observed.replace("Z", "+00:00"))
                            if dt.tzinfo is None: raise ValueError()
                            observed = iso(dt)
                        except ValueError:
                            raise APIError(422, "invalid_timestamp", "observed_at 必須含時區偏移")
                        payload_hash = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
                        rid = str(uuid.uuid4())
                        existing=c.execute("SELECT payload_hash FROM readings WHERE device_id=? AND idempotency_key=?",(device["id"],idem)).fetchone()
                        if existing:
                            if existing["payload_hash"]!=payload_hash: raise APIError(409,"idempotency_key_conflict","相同冪等鍵不可搭配不同測值內容")
                            duplicates+=1
                            continue
                        try:
                            c.execute("INSERT INTO readings(id,device_id,zone_id,observed_at,received_at,metric,value,unit,quality_flag,calibration_ref,idempotency_key,payload_hash,source,ingest_batch_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (rid, device["id"], zone, observed, iso(), metric, value, item.get("unit", "C" if metric == "temperature" else "%" if metric == "humidity" else "lux" if metric == "light" else "pH"), quality, item.get("calibration_ref"), idem, payload_hash,item.get("source","device_simulator"),batch_id))
                            c.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (observed, device["id"]))
                            inserted.append(rid)
                        except sqlite3.IntegrityError:
                            raise APIError(409,"idempotency_key_conflict","冪等鍵已被其他上報使用")
                    audit(c, actor, "sensor.ingest", "readings", trace, {"inserted": len(inserted), "duplicates": duplicates})
                return self.send_json(200, {"inserted": inserted, "duplicate_count": duplicates, "ingest_batch_id":batch_id, "append_only": True, "trace_id": trace})
            if path == "/api/v1/tasks" and method == "POST":
                actor = self.actor("teacher")
                data = self.body()
                matrix = data.get("matrix_code")
                if matrix not in MATRIX or not data.get("title"):
                    raise APIError(422, "invalid_task", "matrix_code 必須為 M01–M25 且 title 必填")
                tid = str(uuid.uuid4())
                with DB_LOCK, connect() as c:
                    c.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?)", (tid, actor["class_id"], matrix, data["title"][:120], str(data.get("prompt", ""))[:2000], str(data.get("prompt_version", "v1.1"))[:50], iso()))
                    audit(c, actor, "task.create", tid, trace)
                return self.send_json(201, {"task_id": tid, "matrix_code": matrix, "trace_id": trace})
            if path == "/api/v1/responses" and method == "POST":
                actor = self.actor("student")
                data = self.body()
                task_id, phase, content = data.get("task_id"), data.get("phase"), data.get("content")
                if phase not in {"pre_ai", "revised", "cer", "reflection"} or not isinstance(content, dict):
                    raise APIError(422, "invalid_response", "phase/content 格式無效")
                with DB_LOCK, connect() as c:
                    task = c.execute("SELECT id FROM tasks WHERE id=? AND class_id=?", (task_id, actor["class_id"])).fetchone()
                    if not task: raise APIError(404, "task_not_found", "找不到此班級任務")
                    previous = c.execute("SELECT * FROM responses WHERE task_id=? AND student_id=? AND phase=? ORDER BY version_no DESC LIMIT 1", (task_id, actor["student_id"], phase)).fetchone()
                    if phase == "pre_ai" and previous:
                        raise APIError(409, "immutable_original", "初答已鎖定；請新增 revised 版本")
                    if data.get("expected_version") is not None and (previous["version_no"] if previous else 0) != data["expected_version"]:
                        raise APIError(409, "version_conflict", "版本已更新，請重新載入")
                    version = (previous["version_no"] if previous else 0) + 1
                    rid = str(uuid.uuid4())
                    c.execute("INSERT INTO responses VALUES(?,?,?,?,?,?,?,?)", (rid, task_id, actor["student_id"], actor["group_id"], phase, version, json.dumps(content, ensure_ascii=False), iso()))
                    if phase == "revised":
                        intervention = c.execute("SELECT id FROM interventions WHERE task_id=? AND student_id=? ORDER BY request_at DESC LIMIT 1", (task_id,actor["student_id"])).fetchone()
                        if intervention:
                            c.execute("INSERT INTO intervention_followups VALUES(?,?,?,?)",(str(uuid.uuid4()),intervention["id"],rid,iso()))
                    audit(c, actor, "response.append", rid, trace, {"phase": phase, "version": version})
                return self.send_json(201, {"response_id": rid, "version": version, "phase": phase, "trace_id": trace})
            if path == "/api/v1/ai/hints" and method == "POST":
                actor = self.actor("student", "teacher")
                data = self.body()
                student = data.get("student_id", actor.get("student_id"))
                if actor["role"] == "student" and student != actor["student_id"]:
                    raise APIError(403, "forbidden", "不可查詢其他學生資料")
                if actor["role"]=="teacher" and actor["class_id"]!="C01": raise APIError(403,"forbidden","此教師未授權此班級")
                with connect() as c:
                    pre = c.execute("SELECT r.* FROM responses r JOIN tasks t ON t.id=r.task_id WHERE r.task_id=? AND r.student_id=? AND r.phase='pre_ai' AND t.class_id=? ORDER BY r.version_no DESC LIMIT 1", (data.get("task_id"), student,actor["class_id"])).fetchone()
                if not pre: raise APIError(409, "pre_ai_required", "請先提交並鎖定初答")
                questions = ["你觀察到的變化有哪些？", "哪些環境條件也可能同時改變？", "哪一筆資料能幫你區分這些可能性？"]
                intervention_id=f"I-{uuid.uuid4().hex[:12].upper()}"
                with DB_LOCK, connect() as c:
                    c.execute("INSERT INTO interventions VALUES(?,?,?,?,?,?,?,?,?,?,?)",(intervention_id,data.get("task_id"),student,pre["id"],"socratic-v1","mock",iso(),json.dumps(questions,ensure_ascii=False),"mock questions do not assert biological facts","synthetic,no_fabricated_evidence",0))
                    audit(c,actor,"ai.intervention",intervention_id,trace,{"pre_ai_version_id":pre["id"],"provider":"mock"})
                return self.send_json(200, {"intervention_id":intervention_id,"provider": "mock", "questions": questions, "evidence_ids": [], "prompt_version": "socratic-v1", "student_pre_ai_version_id": pre["id"], "uncertainty":"Mock questions do not assert observations or biological findings.", "safety_flags": ["synthetic", "no_fabricated_evidence"], "teacher_review_required": True})
            if path.startswith("/api/v1/interventions/") and path.endswith("/review") and method == "POST":
                actor=self.actor("teacher"); iid=path.split("/")[-2]
                with DB_LOCK, connect() as c:
                    row=c.execute("SELECT * FROM interventions WHERE id=?",(iid,)).fetchone()
                    if not row: raise APIError(404,"intervention_not_found","找不到 AI 介入紀錄")
                    task=c.execute("SELECT class_id FROM tasks WHERE id=?",(row["task_id"],)).fetchone()
                    if not task or task["class_id"]!=actor["class_id"]: raise APIError(403,"forbidden","不在授權班級")
                    c.execute("UPDATE interventions SET human_reviewed=1 WHERE id=?",(iid,))
                    audit(c,actor,"ai.intervention_review",iid,trace,{"reviewed":True})
                return self.send_json(200,{"intervention_id":iid,"human_reviewed":True,"trace_id":trace})
            if path == "/api/v1/cer/feedback" and method == "POST":
                actor = self.actor("teacher", "student")
                data = self.body()
                if actor["role"] == "student" and data.get("student_id", actor["student_id"]) != actor["student_id"]:
                    raise APIError(403, "forbidden", "不可查詢其他學生資料")
                return self.send_json(200, {"advisory": True, "checks": {"claim": bool(data.get("claim")), "evidence": bool(data.get("evidence_ids")), "reasoning": bool(data.get("reasoning"))}, "message": "請確認主張、證據與推理彼此對應；此提示不是成績。"})
            if path == "/api/v1/rubric-scores" and method == "POST":
                actor = self.actor("teacher")
                data = self.body()
                rubric = data.get("rubric", {})
                if not isinstance(rubric, dict) or any(k not in {"claim", "evidence", "reasoning"} or v not in {1,2,3,4} for k,v in rubric.items()):
                    raise APIError(422, "invalid_rubric", "CER 各向度等級為 1 至 4")
                with DB_LOCK, connect() as c:
                    task = c.execute("SELECT id FROM tasks WHERE id=? AND class_id=?", (data.get("task_id"), actor["class_id"])).fetchone()
                    response = c.execute("SELECT id FROM cers WHERE task_id=? AND student_id=?", (data.get("task_id"), data.get("student_id"))).fetchone()
                    if not task or not response: raise APIError(404, "work_not_found", "找不到可評閱 CER")
                    sid = str(uuid.uuid4())
                    c.execute("INSERT INTO scores VALUES(?,?,?,?,?,?)", (sid, data["task_id"], data["student_id"], "TEACHER-DEMO", json.dumps(rubric), iso()))
                    audit(c, actor, "teacher.rubric_score", sid, trace, rubric)
                return self.send_json(201, {"score_id": sid, "rubric": rubric, "human_review": True, "trace_id": trace})
            if path.startswith("/api/v1/cers/") and method == "GET":
                actor=self.actor("teacher","student"); cid=path.rsplit("/",1)[-1]
                with connect() as c:
                    row=c.execute("SELECT * FROM cers WHERE id=?",(cid,)).fetchone()
                    if not row: raise APIError(404,"cer_not_found","找不到 CER")
                    if not can_access_student(actor,row["student_id"]): raise APIError(403,"forbidden","不可存取其他學生 CER")
                    refs=[dict(x) for x in c.execute("SELECT evidence_type,evidence_id FROM cer_evidence WHERE cer_id=?",(cid,))]
                    score=c.execute("SELECT rubric,created_at FROM scores WHERE task_id=? AND student_id=? ORDER BY created_at DESC LIMIT 1",(row["task_id"],row["student_id"])).fetchone() if actor["role"]=="teacher" else None
                return self.send_json(200,{"cer_id":cid,"claim":row["claim"],"reasoning":row["reasoning"],"version":row["version_no"],"evidence":refs,"teacher_assessment":dict(score) if score else None})
            if path == "/api/v1/research/exports" and method == "POST":
                actor = self.actor("researcher")
                data = self.body()
                scope = data.get("scope", "research")
                if scope!="research": raise APIError(403,"consent_scope_forbidden","研究匯出只能使用 research 同意範圍")
                date_range=data.get("date_range") or {}
                if not isinstance(date_range,dict): raise APIError(422,"invalid_date_range","date_range 必須為 from/to 物件")
                try:
                    bounds={k:datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc) for k,v in date_range.items() if k in {"from","to"} and v}
                    if any(datetime.fromisoformat(v.replace("Z","+00:00")).tzinfo is None for k,v in date_range.items() if k in {"from","to"} and v): raise ValueError()
                except (ValueError,AttributeError): raise APIError(422,"invalid_date_range","匯出日期須為含時區的 ISO-8601")
                if "from" in bounds and "to" in bounds and bounds["from"]>bounds["to"]: raise APIError(422,"invalid_date_range","起始日期不可晚於結束日期")
                def in_range(timestamp):
                    point=datetime.fromisoformat(timestamp.replace("Z","+00:00")).astimezone(timezone.utc)
                    return ("from" not in bounds or point>=bounds["from"]) and ("to" not in bounds or point<=bounds["to"])
                with DB_LOCK, connect() as c:
                    students = [r[0] for r in c.execute("SELECT student_id FROM consents WHERE scope=? AND permission=1", (scope,))]
                    group_marks=",".join("?" for _ in students) or "NULL"
                    consented_groups=[r[0] for r in c.execute(f"SELECT DISTINCT group_id FROM student_profiles WHERE student_id IN ({group_marks})",students)]
                    zone_marks=",".join("?" for _ in consented_groups) or "NULL"
                    exported_readings = [dict(r) for r in c.execute(f"SELECT r.id,r.zone_id,r.observed_at,r.metric,r.value,r.unit,r.quality_flag,r.device_id,r.idempotency_key,r.source,r.ingest_batch_id,z.light_group_id FROM readings r JOIN zones z ON z.id=r.zone_id JOIN zone_group_access za ON za.zone_id=z.id WHERE za.group_id IN ({zone_marks})",consented_groups) if in_range(r["observed_at"])]
                    observations = [dict(r) for r in c.execute("SELECT id,student_id,group_id,zone_id,original_version_id,version_no,captured_at,dataset_type FROM observations WHERE student_id IN (SELECT student_id FROM consents WHERE scope=? AND permission=1)",(scope,)) if in_range(r["captured_at"])]
                    cers = []
                    cer_rows=c.execute("SELECT * FROM cers WHERE student_id IN (SELECT student_id FROM consents WHERE scope=? AND permission=1)",(scope,)).fetchall()
                    for row in cer_rows:
                        if not in_range(row["created_at"]): continue
                        refs=[dict(e) for e in c.execute("SELECT evidence_type,evidence_id FROM cer_evidence WHERE cer_id=?",(row["id"],))]
                        cers.append({"cer_id":row["id"],"student_pseudonym":row["student_id"],"version":row["version_no"],"created_at":row["created_at"],"claim":safe_export_text(row["claim"]),"reasoning":safe_export_text(row["reasoning"]),"evidence_refs":refs})
                    zones = [dict(r) for r in c.execute("SELECT id,environment_cluster_id,light_group_id FROM zones")]
                    scores=[dict(r) for r in c.execute("SELECT task_id,student_id,rubric,created_at FROM scores WHERE student_id IN (SELECT student_id FROM consents WHERE scope=? AND permission=1)",(scope,)) if in_range(r["created_at"])]
                    result = {"export_id": str(uuid.uuid4()), "scope": scope, "student_count": len(students), "consented_groups":consented_groups, "responses": [], "observations": observations, "sensor_readings": exported_readings, "cers": cers, "rubric_scores": scores, "zone_environment_groups": zones, "identifiers_removed": ["real_name", "face", "voice", "free_form_observation_text", "raw_cer_text"], "synthetic_only": True, "date_range": data.get("date_range")}
                    audit(c, actor, "research.export", result["export_id"], trace, {"scope": scope, "student_count": len(students)})
                    manifest={"export_id":result["export_id"],"version":"MVP-001","dataset_type":"synthetic_demo_only","scope":scope,"consented_pseudonyms":students,"consented_groups":consented_groups,"date_range":data.get("date_range"),"deidentification_rules":result["identifiers_removed"],"generated_at":iso(),"filters":"Only consented pseudonyms and their assigned zone groups; free-form child text omitted; sensor records retain shared light_group_id; synthetic data only."}
                    dictionary=(ROOT/"docs"/"DATA_DICTIONARY.md").read_text(encoding="utf-8")
                    export_dir=DB_PATH.parent/"exports"; export_dir.mkdir(parents=True,exist_ok=True)
                    zip_path=export_dir/f"{result['export_id']}.zip"
                    files={"data.json":json.dumps(result,ensure_ascii=False,indent=2).encode(),"observations.csv":self.rows_csv(observations),"sensor_readings.csv":self.rows_csv(exported_readings),"cer.json":json.dumps(cers,ensure_ascii=False,indent=2).encode(),"data_dictionary.md":dictionary.encode(),"manifest.json":b""}
                    hashes={name:hashlib.sha256(content).hexdigest() for name,content in files.items() if name!="manifest.json"}
                    manifest["sha256"]=hashes
                    files["manifest.json"]=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
                    with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as archive:
                        for name,content in files.items(): archive.writestr(name,content)
                    result["manifest"]=manifest; result["download_path"]=f"/api/v1/research/exports/{result['export_id']}.zip"
                    c.execute("INSERT INTO research_exports VALUES(?,?,?,?)",(result["export_id"],str(zip_path),json.dumps(manifest,ensure_ascii=False),iso()))
                return self.send_json(200, result)
            if path.startswith("/api/v1/research/exports/") and method == "GET" and path.endswith(".zip"):
                self.actor("researcher")
                export_id=path.rsplit("/",1)[-1][:-4]
                with connect() as c: export=c.execute("SELECT file_path FROM research_exports WHERE id=?",(export_id,)).fetchone()
                if not export: raise APIError(404,"export_not_found","找不到匯出檔")
                p=Path(export["file_path"])
                if not p.is_file() or p.parent.resolve()!=(DB_PATH.parent/"exports").resolve(): raise APIError(404,"export_missing","匯出檔不存在")
                blob=p.read_bytes(); self.send_response(200); self.send_header("Content-Type","application/zip"); self.send_header("Content-Disposition",f'attachment; filename="{export_id}.zip"'); self.send_header("Content-Length",str(len(blob))); self.end_headers(); self.wfile.write(blob); return
            if path == "/api/v1/audit" and method == "GET":
                actor = self.actor("teacher", "researcher")
                if actor["role"]=="teacher" and actor["class_id"]!="C01": raise APIError(403,"forbidden","此教師未授權此班級")
                with connect() as c: rows = [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY created_at DESC LIMIT 200")]
                return self.send_json(200, {"events": rows})
            raise APIError(404, "not_found", "找不到此 API")
        except APIError as exc:
            self.send_json(exc.status, {"error": {"code": exc.code, "message": exc.message, "request_id": trace}})
        except Exception:
            self.send_json(500, {"error": {"code": "internal_error", "message": "伺服器處理失敗", "request_id": trace}})

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            return self.handle_api()
        path = urlparse(self.path).path
        target = (ROOT / "web" / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
        if ROOT.joinpath("web").resolve() not in target.parents and target != ROOT / "web" / "index.html":
            return self.send_error(404)
        try:
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if target.suffix == ".html" else "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self.send_error(404)

    def do_POST(self) -> None:
        self.handle_api()

    @staticmethod
    def rows_csv(rows) -> bytes:
        output=io.StringIO()
        keys=list(rows[0].keys()) if rows else []
        writer=csv.DictWriter(output,fieldnames=keys); writer.writeheader(); writer.writerows(rows)
        return output.getvalue().encode("utf-8-sig")


if __name__ == "__main__":
    initialize()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"AI-SIM synthetic demo ready at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
