# -*- coding: utf-8 -*-
"""Live smoke test against the real ~/.jobcli/jobcli.db database."""
import os
import sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from jobcli.storage.models import Database
from jobcli.storage.repositories import FieldAnswerRepository, SyncMetadataRepository
from jobcli.profile.schemas import ATSType
import uuid

DB_PATH = os.getenv("DATABASE_PATH") or str(Path.home() / ".jobcli" / "jobcli.db")
DB_PATH = os.path.expandvars(os.path.expanduser(DB_PATH))
db = Database(f"sqlite:///{Path(DB_PATH).as_posix()}")
db.create_tables()
session = db.get_session()

repo = FieldAnswerRepository(session)
sync = SyncMetadataRepository(session)

# Unique suffix keeps each run isolated against the persistent DB
RUN_ID = uuid.uuid4().hex[:8]
SMOKE_LABEL  = f"smoke_{RUN_ID}"
MERGE_LABEL  = f"merge_{RUN_ID}"
DEGRADE_LABEL = f"degrade_{RUN_ID}"

PASS = "✓ PASS"
FAIL = "✗ FAIL"

print("=" * 60)
print("PHASE 1 LOCAL LEARNING — LIVE SMOKE TEST")
print(f"DB: {DB_PATH}")
print("=" * 60)

# ── Test 1: confidence starts at 1.0 on first success ────────────
repo.save_answer("Smoke Test", SMOKE_LABEL, "Yes", ATSType.GREENHOUSE, success=True, source="auto")
row = repo.get_raw_by_label(SMOKE_LABEL, ATSType.GREENHOUSE)
t1 = row.confidence == 1.0
print(f"\n[1] First success  -> confidence={row.confidence:.2f}  (expect 1.00)  {PASS if t1 else FAIL}")

# ── Test 2: gated retrieval returns None below MIN_SUCCESS_COUNT ──
result = repo.get_by_normalized_label(SMOKE_LABEL, ATSType.GREENHOUSE)
t2 = result is None
print(f"[2] Gated get (1 success, need 3) -> {result}  (expect None)  {PASS if t2 else FAIL}")

# ── Test 3: crosses threshold after 3 successes ───────────────────
repo.save_answer("Smoke Test", SMOKE_LABEL, "Yes", ATSType.GREENHOUSE, success=True, source="auto")
repo.save_answer("Smoke Test", SMOKE_LABEL, "Yes", ATSType.GREENHOUSE, success=True, source="auto")
row = repo.get_raw_by_label(SMOKE_LABEL, ATSType.GREENHOUSE)
result = repo.get_by_normalized_label(SMOKE_LABEL, ATSType.GREENHOUSE)
t3 = result is not None and result.value == "Yes"
print(f"[3] After 3 successes conf={row.confidence:.2f}, gated={result.value if result else None}  {PASS if t3 else FAIL}")

# ── Test 4: merge protection — human not overwritten by auto ──────
repo.save_answer("Merge Guard", MERGE_LABEL, "Human Answer", ATSType.LEVER, source="human")
repo.save_answer("Merge Guard", MERGE_LABEL, "Auto Override", ATSType.LEVER, source="auto")
row = repo.get_raw_by_label(MERGE_LABEL, ATSType.LEVER)
t4 = row.value == "Human Answer" and row.source == "human"
print(f"[4] Merge protection -> value='{row.value}' src='{row.source}'  {PASS if t4 else FAIL}")

# ── Test 5: failure degrades confidence ───────────────────────────
repo.save_answer("Degrade Test", DEGRADE_LABEL, "v", ATSType.WORKDAY, success=True)
repo.save_answer("Degrade Test", DEGRADE_LABEL, "v", ATSType.WORKDAY, success=True)
repo.save_answer("Degrade Test", DEGRADE_LABEL, "v", ATSType.WORKDAY, success=False)
row = repo.get_raw_by_label(DEGRADE_LABEL, ATSType.WORKDAY)
expected_conf = round(2 / 3, 4)
t5 = abs(row.confidence - expected_conf) < 1e-3
print(f"[5] 2 success + 1 failure → conf={row.confidence:.4f}  (expect {expected_conf:.4f})  {PASS if t5 else FAIL}")

# ── Test 6: record_outcome updates counts without changing value ──
before = repo.get_raw_by_label(SMOKE_LABEL, ATSType.GREENHOUSE)
count_before = before.success_count
repo.record_outcome(SMOKE_LABEL, ATSType.GREENHOUSE, success=True)
row = repo.get_raw_by_label(SMOKE_LABEL, ATSType.GREENHOUSE)
t6 = row.success_count == count_before + 1 and row.value == "Yes"
print(f"[6] record_outcome: count {count_before} -> {row.success_count} value='{row.value}'  {PASS if t6 else FAIL}")

# ── Test 7: sync metadata counter ─────────────────────────────────
sync.increment_apps_since_sync()
sync.increment_apps_since_sync()
count = sync.get_apps_since_sync()
t7 = count == 2
print(f"[7] Sync counter after 2 increments → {count}  (expect 2)  {PASS if t7 else FAIL}")

sync.record_sync(version="1.0.0")
meta = sync.get_or_create()
t8 = meta.apps_since_sync == 0 and meta.last_version == "1.0.0" and meta.last_sync_at is not None
print(f"[8] record_sync  → apps={meta.apps_since_sync} version={meta.last_version} synced_at={meta.last_sync_at}  {PASS if t8 else FAIL}")

# ── Test 8: extractor strips PII, keeps safe fields ───────────────
from jobcli.sync.extractor import extract_field_answers

# pump a fresh safe label to threshold to confirm it appears
for _ in range(3):
    repo.save_answer("Email", "email", "test@example.com", ATSType.GREENHOUSE, success=True)

answers = extract_field_answers(session)
labels = {a["normalized_label"] for a in answers}
t9a = "email" not in labels          # PII stripped
t9b = SMOKE_LABEL in labels          # our fresh safe field present
print(f"[9] Extractor: email excluded={t9a}  (expect True)   {PASS if t9a else FAIL}")
print(f"[10] Extractor: test field included={t9b}  (expect True)   {PASS if t9b else FAIL}")

# ── Summary ────────────────────────────────────────────────────────
all_pass = all([t1, t2, t3, t4, t5, t6, t7, t8, t9a, t9b])
print()
print("=" * 60)
results = [t1, t2, t3, t4, t5, t6, t7, t8, t9a, t9b]
passed = sum(results)
print(f"RESULT: {passed}/{len(results)} passed  {'ALL PASS ✓' if all_pass else 'SOME FAILURES ✗'}")

# ── Show current DB state ───────────────────────────────────────────
print()
print("CURRENT field_answers TABLE (all rows):")
from jobcli.storage.models import FieldAnswerModel
rows = session.query(FieldAnswerModel).order_by(FieldAnswerModel.normalized_label).all()
print(f"  {'LABEL':<32} {'CONF':>6}  {'S':>4}  {'F':>4}  {'SRC'}")
print("  " + "-" * 60)
for r in rows:
    flag = "TRUSTED" if (r.confidence >= 0.6 and r.success_count >= 3) else "low-conf"
    print(f"  [{flag}] {(r.normalized_label or ''):<28} {r.confidence:>6.2f}  {r.success_count:>4d}  {r.failure_count:>4d}  {r.source}")

print()
print("SYNC METADATA:")
from jobcli.storage.models import SyncMetadataModel
m = session.query(SyncMetadataModel).first()
if m:
    print(f"  apps_since_sync={m.apps_since_sync}  last_version={m.last_version}  last_sync_at={m.last_sync_at}")

session.close()
print("=" * 60)
