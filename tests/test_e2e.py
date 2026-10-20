import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile
import io
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class E2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        env = os.environ.copy()
        env["AI_SIM_DB"] = str(Path(cls.temp.name) / "test.sqlite3")
        env["AI_SIM_HOST"] = "127.0.0.1"
        env["AI_SIM_PORT"] = "18765"
        env["AI_SIM_PUBLIC_SHOWCASE"] = "0"
        cls.proc = subprocess.Popen([sys.executable, "-m", "app.server"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = "http://127.0.0.1:18765"
        for _ in range(80):
            try:
                cls.request("GET", "/api/v1/health")
                break
            except Exception:
                time.sleep(.1)
        else:
            raise RuntimeError("API did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        cls.temp.cleanup()

    @classmethod
    def request(cls, method, path, token=None, data=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(cls.base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_full_synthetic_loop_and_guards(self):
        self.assertEqual(self.request("GET", "/api/v1/zones", "student-g01-demo-token")[0], 200)  # T01/T12, E01
        self.assertEqual(len(self.request("GET", "/api/v1/zones", "student-g01-demo-token")[1]["zones"]), 9)
        self.assertEqual(self.request("GET", "/api/v1/zones")[0], 401)
        self.assertEqual(self.request("GET", "/api/v1/zones", "teacher-other-class-demo-token")[0], 403)  # E08
        self.assertEqual(self.request("GET", "/api/v1/audit", "teacher-other-class-demo-token")[0],403)
        self.assertEqual(self.request("GET", "/api/v1/readings", "research-demo-token")[0],403)
        self.assertEqual(self.request("GET", "/api/v1/observations?student_id=S002", "student-g01-demo-token")[0], 403)  # T01/E08
        self.assertEqual(self.request("GET", "/api/v1/readings?zone_id=Z01", "student-g02-demo-token")[0],403)
        self.assertEqual(self.request("POST", "/api/v1/ai/hints", "student-g01-demo-token", {"task_id":"TASK-DEMO"})[0], 409)  # T02/E03

        status, obs = self.request("POST", "/api/v1/observations", "student-g01-demo-token", {"observation_id":"O001","task_id":"TASK-DEMO","zone_id":"Z01","text":"合成觀察：葉面黏液亮點似乎較少，原因待驗證。"})
        self.assertEqual(status, 201)  # E01/E02
        self.assertEqual(self.request("POST", "/api/v1/observations", "student-g01-demo-token", {"observation_id":"O001-EDIT","task_id":"TASK-DEMO","text":"改寫原始觀察"})[0], 409)  # T03
        self.assertEqual(self.request("POST", "/api/v1/observations", "student-g01-demo-token", {"observation_id":"O002","task_id":"TASK-DEMO","text":"更正觀察版本","original_version_id":"O001"})[0], 201)  # append correction

        status, pre = self.request("POST", "/api/v1/responses", "student-g01-demo-token", {"task_id":"TASK-DEMO","phase":"pre_ai","content":{"text":"黏液減少可能與光照有關，仍需驗證"}})
        self.assertEqual(status, 201)
        self.assertEqual(self.request("POST", "/api/v1/responses", "student-g01-demo-token", {"task_id":"TASK-DEMO","phase":"pre_ai","content":{"text":"改寫初答"}})[0], 409)  # T03/E02
        status, hint = self.request("POST", "/api/v1/ai/hints", "student-g01-demo-token", {"task_id":"TASK-DEMO"})
        self.assertEqual(status, 200); self.assertEqual(hint["provider"],"mock"); self.assertLessEqual(len(hint["questions"]),3)  # E03/T09
        self.assertTrue(hint["intervention_id"] and hint["prompt_version"] and hint["student_pre_ai_version_id"])
        self.assertEqual(self.request("POST", "/api/v1/responses", "student-g01-demo-token", {"task_id":"TASK-DEMO","phase":"revised","content":{"text":"我會比較光照並檢查濕度"},"expected_version":0})[0], 201)
        self.assertEqual(self.request("POST", "/api/v1/responses", "student-g01-demo-token", {"task_id":"TASK-DEMO","phase":"revised","content":{"text":"過期版本寫入"},"expected_version":0})[0], 409)
        db=sqlite3.connect(Path(self.temp.name)/"test.sqlite3")
        try: self.assertEqual(db.execute("SELECT COUNT(*) FROM intervention_followups WHERE intervention_id=?",(hint["intervention_id"],)).fetchone()[0],1)
        finally: db.close()
        self.assertEqual(self.request("POST", "/api/v1/ai/hints", "student-g02-demo-token", {"task_id":"TASK-DEMO","student_id":"S001"})[0], 403)
        self.assertEqual(self.request("POST", f"/api/v1/interventions/{hint['intervention_id']}/review", "teacher-demo-token", {})[0], 200)

        _, offline = self.request("GET", "/api/v1/devices/status", "teacher-demo-token")
        self.assertTrue(any(d["status"]=="offline" for d in offline["devices"]))  # T06/E04
        self.assertEqual(self.request("POST", "/api/v1/tasks", "student-g01-demo-token", {"matrix_code":"M09","title":"變因"})[0], 403)
        self.assertEqual(self.request("GET", "/api/v1/readings", "device-demo-token")[0], 403)
        items=[]
        for n,(metric,value,quality,zone,when) in enumerate([("illuminance",6200,"valid","Z01","2026-10-19T10:00:00+08:00"),("temperature",23,"valid","Z01","2026-10-19T10:01:00+08:00"),("humidity",None,"missing","Z01","2026-10-19T10:02:00+08:00"),("temperature",24,"valid","Z01","2026-10-19T10:03:00+08:00"),("temperature",22,"valid","Z02","2020-01-01T00:00:00Z")]):
            if metric=="illuminance": metric="light"
            items.append({"zone_id":zone,"metric":metric,"value":value,"unit":"lux" if metric=="light" else "C" if metric=="temperature" else "%","quality_flag":quality,"observed_at":when,"idempotency_key":f"E04-{n}"})
        _, ingest = self.request("POST", "/api/v1/ingest/readings", "device-demo-token", {"readings":items,"ingest_batch_id":"batch-E04"})
        self.assertEqual(len(ingest["inserted"]),5); self.assertEqual(ingest["duplicate_count"],0)
        self.assertEqual(ingest["ingest_batch_id"],"batch-E04")
        _, dup = self.request("POST", "/api/v1/ingest/readings", "device-demo-token", {"readings":items})
        self.assertEqual(dup["duplicate_count"],5)  # T04/E04
        conflicting={**items[0],"value":999}
        self.assertEqual(self.request("POST","/api/v1/ingest/readings","device-demo-token",conflicting)[0],409)
        self.assertEqual(self.request("POST","/api/v1/ingest/readings","device-demo-token",{"zone_id":"Z01","metric":"temperature","value":float('nan'),"idempotency_key":"nan"})[0],422)
        _, stale_status=self.request("GET","/api/v1/devices/status","teacher-demo-token")
        self.assertEqual(next(d["status"] for d in stale_status["devices"] if d["zone_id"]=="Z02"),"offline")
        _, readings = self.request("GET", "/api/v1/readings?zone_id=Z01", "teacher-demo-token")
        self.assertTrue(any(r["quality_flag"]=="missing" and r["value"] is None for r in readings["readings"]))  # T05
        utcrow=next(r for r in readings["readings"] if r["id"]==ingest["inserted"][0])
        self.assertTrue(utcrow["observed_at"].endswith("+00:00"))  # T07
        self.assertEqual(utcrow["source"],"device_simulator"); self.assertEqual(utcrow["ingest_batch_id"],"batch-E04")
        db=sqlite3.connect(Path(self.temp.name)/"test.sqlite3")
        try:
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE readings SET value=99 WHERE id=?",(ingest["inserted"][0],))
            with self.assertRaises(sqlite3.IntegrityError): db.execute("DELETE FROM readings WHERE id=?",(ingest["inserted"][0],))
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE observations SET text='changed' WHERE id='O001'")
        finally: db.close()

        status, analysis=self.request("POST","/api/v1/analyses","student-g01-demo-token",{"task_id":"TASK-DEMO","reading_ids":[ingest["inserted"][1],ingest["inserted"][3]],"explanation":"合成資料示例，只描述時間序列。"})
        self.assertEqual(status,201); self.assertEqual(len(analysis["points"]),2); self.assertTrue(all(p["reading_id"] in ingest["inserted"] for p in analysis["points"]))  # E05
        self.assertEqual(analysis["chart_spec"]["metric"],"temperature")
        self.assertEqual(self.request("POST","/api/v1/analyses","student-g01-demo-token",{"reading_ids":[ingest["inserted"][1],ingest["inserted"][2]]})[0],422)
        status, cer=self.request("POST","/api/v1/cers","student-g01-demo-token",{"task_id":"TASK-DEMO","claim":"合成示例主張：目前資料不足以判定原因。","reasoning":"兩筆感測值只能描述該時間點，無法證明因果。","evidence":[{"type":"observation","id":"O001"},{"type":"reading","id":ingest["inserted"][0]},{"type":"reading","id":ingest["inserted"][1]},{"type":"analysis","id":analysis["analysis_id"]}]})
        self.assertEqual(status,201); self.assertEqual(len(cer["resolved_evidence"]),4)  # E06/T09
        self.assertEqual(self.request("POST","/api/v1/cers","student-g02-demo-token",{"claim":"cross-group","reasoning":"cross-group","evidence":[{"type":"reading","id":ingest["inserted"][1]}]})[0],403)
        self.assertEqual(self.request("POST","/api/v1/cers","student-g01-demo-token",{"claim":"bad","reasoning":"bad","evidence":[{"type":"reading","id":"NO-SUCH-READING"}]})[0],422)
        self.assertEqual(self.request("POST", "/api/v1/rubric-scores", "teacher-demo-token", {"task_id":"TASK-DEMO","student_id":"S001","rubric":{"claim":3,"evidence":2,"reasoning":3}})[0], 201)  # E06/T11
        self.assertEqual(self.request("POST", "/api/v1/rubric-scores", "teacher-demo-token", {"task_id":"TASK-DEMO","student_id":"S002","rubric":{"claim":5}})[0], 422)

        _, export = self.request("POST", "/api/v1/research/exports", "research-demo-token", {"scope":"research"})
        self.assertEqual(self.request("POST","/api/v1/research/exports","research-demo-token",{"scope":"research","date_range":{"from":"2030-01-01T00:00:00","to":"2020-01-01T00:00:00Z"}})[0],422)
        self.assertEqual(export["student_count"], 1); self.assertTrue(all(x["student_id"]!="S002" for x in export["observations"]))  # T10/E07
        self.assertEqual(export["consented_groups"],["G01"]); self.assertTrue(all(x["zone_id"]=="Z01" for x in export["sensor_readings"]))
        self.assertIn("light_group_id",export["sensor_readings"][0]); self.assertIn("sha256",export["manifest"])
        self.assertNotIn("合成觀察",json.dumps(export,ensure_ascii=False))
        zip_url=export["download_path"]
        req=urllib.request.Request(self.base+zip_url,headers={"Authorization":"Bearer research-demo-token"})
        with urllib.request.urlopen(req) as resp: archive=zipfile.ZipFile(io.BytesIO(resp.read()))
        self.assertTrue({"data.json","observations.csv","sensor_readings.csv","cer.json","data_dictionary.md","manifest.json"}.issubset(archive.namelist()))
        zmanifest=json.loads(archive.read("manifest.json")); self.assertTrue(zmanifest["sha256"])
        for name,digest in zmanifest["sha256"].items(): self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)
        self.assertNotIn("合成觀察",archive.read("data.json").decode("utf-8"))
        self.assertEqual(self.request("GET", "/api/v1/observations?student_id=S001", "student-g02-demo-token")[0], 403)  # E08
        self.assertEqual(self.request("GET", "/api/v1/observations", "student-g01-demo-token")[0],200)  # persisted after new API/login
        _, workspace=self.request("GET","/api/v1/workspace","student-g01-demo-token")
        self.assertTrue(workspace["refresh_restores_work"] and all(workspace["stages"].values()))
        _, restored_chart=self.request("GET",f"/api/v1/analyses/{analysis['analysis_id']}","student-g01-demo-token")
        self.assertEqual({p["reading_id"] for p in restored_chart["points"]},set(analysis["reading_ids"]))
        self.assertEqual(self.request("GET",f"/api/v1/analyses/{analysis['analysis_id']}","student-g02-demo-token")[0],403)
        _, audit = self.request("GET", "/api/v1/audit", "research-demo-token")
        self.assertEqual(self.request("POST","/api/v1/research/exports","research-demo-token",{"scope":"teaching"})[0],403)
        actions={e["action"] for e in audit["events"]}
        self.assertTrue({"research.export","teacher.rubric_score","observation.append","ai.intervention","cer.submit"}.issubset(actions))


class PublicShowcaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        env = os.environ.copy()
        env["AI_SIM_DB"] = str(Path(cls.temp.name) / "public-showcase.sqlite3")
        env["AI_SIM_HOST"] = "127.0.0.1"
        env["AI_SIM_PORT"] = "18766"
        env["AI_SIM_PUBLIC_SHOWCASE"] = "1"
        cls.proc = subprocess.Popen([sys.executable, "-m", "app.server"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = "http://127.0.0.1:18766"
        for _ in range(80):
            try:
                with urllib.request.urlopen(cls.base + "/api/v1/health", timeout=1):
                    break
            except Exception:
                time.sleep(.1)
        else:
            raise RuntimeError("Public showcase API did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        cls.temp.cleanup()

    def test_public_site_is_synthetic_and_api_is_read_only(self):
        with urllib.request.urlopen(self.base + "/api/v1/health", timeout=2) as response:
            health = json.loads(response.read())
        self.assertEqual(health["mode"], "synthetic-public-showcase")
        self.assertFalse(health["writes_enabled"])
        with urllib.request.urlopen(self.base + "/", timeout=2) as response:
            page = response.read().decode("utf-8")
        self.assertIn("公開展示模式・僅使用合成資料", page)
        self.assertIn("重新整理即清除", page)
        request = urllib.request.Request(
            self.base + "/api/v1/observations",
            data=json.dumps({"task_id": "TASK-DEMO", "zone_id": "Z01", "text": "synthetic"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer student-g01-demo-token"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(err.exception.code, 403)
        body = json.loads(err.exception.read())
        self.assertEqual(body["error"]["code"], "showcase_read_only")


if __name__ == "__main__":
    unittest.main()
