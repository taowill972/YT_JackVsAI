import json
import time
from pipeline import process_single_video
from git_manager import update_readme_index, commit_and_push_repo
from config import STATE_FILE, CATALOG_FILE

vid_id = "CBDaJb04FgU"
print(f"[FinishSingle] Traitement final de la 5eme video : {vid_id}", flush=True)

rec = process_single_video(vid_id)

with open(STATE_FILE, "r", encoding="utf-8") as f:
    state = json.load(f)

if vid_id not in state["processed_ids"]:
    state["processed_ids"].append(vid_id)
state["processed_videos"].insert(0, rec)
state["completed_count"] = len(state["processed_ids"])

total_catalog = 59
if CATALOG_FILE.exists():
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        cat = json.load(f)
        total_catalog = len(cat.get("videos", []))

state["total_catalog_count"] = total_catalog
state["status"] = "waiting_next_cron"
state["last_run_timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

update_readme_index(state["processed_videos"], total_catalog_count=total_catalog)
commit_and_push_repo(f"feat(transcription): YT-{vid_id} - {rec.get('title', vid_id)[:60]}")
print(f"🎉 [FinishSingle] 5/5 VIDÉOS DU PREMIER LOT TERMINÉES AVEC SUCCÈS !", flush=True)
