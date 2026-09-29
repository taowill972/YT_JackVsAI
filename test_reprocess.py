import sys
import json
import time
from pathlib import Path
from pipeline import process_single_video
from git_manager import update_readme_index, commit_and_push_repo
from config import STATE_FILE, CATALOG_FILE

def main():
    video_id = "CBDaJb04FgU"
    title = "How to Build a Solo Motion Graphics Studio with AI"
    print(f"=== [TEST REPROCESS] Starting multi-screenshot & anti-facecam test on {video_id} ===", flush=True)

    t0 = time.time()
    record = process_single_video(video_id, catalog_title=title)
    elapsed = time.time() - t0
    print(f"=== [TEST REPROCESS] Finished in {elapsed:.1f}s ===", flush=True)
    print(f"  Screenshots saved: {record.get('screenshots_count')}", flush=True)
    print(f"  MD file: {record.get('filepath_md')}", flush=True)
    print(f"  HTML file: {record.get('filepath_html')}", flush=True)

    # Update state.json
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        new_pv = []
        replaced = False
        for pv in state.get("processed_videos", []):
            if pv.get("video_id") == video_id:
                new_pv.append(record)
                replaced = True
            else:
                new_pv.append(pv)
        if not replaced:
            new_pv.append(record)
        state["processed_videos"] = new_pv

        if video_id not in state.get("processed_ids", []):
            state["processed_ids"].append(video_id)

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            cat = json.load(f)
            total = len(cat.get("videos", []))

        update_readme_index(state["processed_videos"], total_catalog_count=total)
        commit_and_push_repo(f"feat(multi-screen): reprocessed YT-{video_id} with multi-screenshot grid & anti-facecam filter")
        print("=== [TEST REPROCESS] Git updated & pushed successfully ===", flush=True)

if __name__ == "__main__":
    main()
