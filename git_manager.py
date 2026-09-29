import subprocess
from pathlib import Path
from typing import List, Dict, Any

from config import (
    REPO_DIR,
    CHANNEL_NAME,
    CHANNEL_URL,
    CHANNEL_HANDLE,
    MODEL_SIGNATURE
)

def update_readme_index(processed_videos: List[Dict[str, Any]], total_catalog_count: int = 56) -> None:
    """Met ? jour le sommaire central README.md dans le d?p?t GitHub avec liens MD et HTML."""
    readme_path = REPO_DIR / "README.md"
    pct = (len(processed_videos) / total_catalog_count * 100) if total_catalog_count > 0 else 0

    lines = [
        f"# ?? YT_JackVsAI ? Transcriptions & Analyses Multimodales",
        "",
        f"> Base de connaissances et transcriptions int?grales mot pour mot en fran?ais (audio via `whisper-v3-large-turbo`) et descriptions visuelles d'?cran (via `gemini-3.5-flash-lite`) avec captures d'?cran cl?s et fiches HTML interactives de la cha?ne **[{CHANNEL_NAME}]({CHANNEL_URL})** ({CHANNEL_HANDLE}).",
        "",
        "## ?? Statistiques de l'Automatisation",
        f"- **Vid?os trait?es** : `{len(processed_videos)} / {total_catalog_count}` (`{pct:.1f}%`)",
        f"- **Mod?le Audio ASR** : `OpenAI / Faster-Whisper large-v3-turbo` (CPU int8 VPS Contabo, 100% Verbatim Fran?ais)",
        f"- **Mod?le Vision d'?cran** : `Google Gemini 3.5 Flash-Lite` (Analyse d'?crans, prompts, outils et workflows vid?o IA)",
        f"- **Signature des fichiers** : `by-{MODEL_SIGNATURE}`",
        f"- **Cadence de la routine** : Traitement par lot de 5 vid?os toutes les 6 heures (d?croissant : des plus r?centes aux plus anciennes)",
        f"- **?coute passive** : D?tection instantan?e 0 token (flux Atom XML YouTube) des nouveaux uploads",
        "",
        "---",
        "",
        "## ?? Index Chronologique des Transcriptions Disponibles",
        "",
        "| Date | Titre & Fiche Markdown | Fiche Web Interactive | Dur?e | Captures | Lien YouTube | ID Vid?o |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: |"
    ]

    for item in processed_videos:
        title = item.get("title", "Sans titre").replace("|", "-")
        md_file = item.get("filename_md", "")
        html_file = item.get("filename_html", "")
        duration_s = item.get("duration", 0)
        mins = int(duration_s) // 60 if duration_s else 0
        secs = int(duration_s) % 60 if duration_s else 0
        dur_str = f"{mins}m {secs:02d}s" if duration_s else "N/A"
        pub = item.get("pub_date", "N/A")
        vid_id = item.get("video_id", "")
        yt_url = f"https://www.youtube.com/watch?v={vid_id}"
        shots_count = item.get("screenshots_count", 0)

        lines.append(
            f"| {pub} | [{title}]({md_file}) | [?? Consulter en ligne]({html_file}) | {dur_str} | `{shots_count} images` | [Voir sur YouTube]({yt_url}) | `{vid_id}` |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*G?n?r? automatiquement par l'agent de veille multimodale Antigravity sur VPS Contabo.*")

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[GitManager] README.md mis ? jour ({len(processed_videos)} vid?os index?es).", flush=True)

def commit_and_push_repo(commit_msg: str) -> bool:
    """Stage tous les fichiers du repo, commit et push vers GitHub origin/main."""
    try:
        subprocess.run(["git", "add", "."], cwd=REPO_DIR, check=True, capture_output=True)

        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_DIR, capture_output=True, text=True, check=True
        )
        if not status_res.stdout.strip():
            print("[GitManager] Aucun nouveau changement ? commiter.", flush=True)
            return True

        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=REPO_DIR, check=True, capture_output=True
        )
        print(f"[GitManager] Commit cr?? : '{commit_msg}'", flush=True)

        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=REPO_DIR, check=True, capture_output=True
        )
        print(f"[GitManager] ? D?ploiement GitHub r?ussi vers origin/main.", flush=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[GitManager] Erreur Git (code {e.returncode}) : {e.stderr}", flush=True)
        return False
    except Exception as e:
        print(f"[GitManager] Erreur commit/push : {e}", flush=True)
        return False

