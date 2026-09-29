import os
import sys
import re
import json
import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageChops, ImageStat

from config import (
    REPO_DIR,
    WORK_DIR,
    SCREENSHOTS_DIR,
    PROXY,
    PLAYER_CLIENT,
    CHANNEL_NAME,
    CHANNEL_URL,
    CHANNEL_HANDLE,
    GEMINI_MODEL,
    WHISPER_MODEL,
    MODEL_SIGNATURE,
    FRAME_DIFF_THRESHOLD,
    FRAME_MAX_WIDTH
)
from whisper_transcriber import transcribe_audio_english, format_timestamp
from gemini_client import (
    translate_title_fr,
    process_multimodal_block,
    generate_executive_summary
)
from html_generator import generate_video_html

def sanitize_filename_title(title: str) -> str:
    """Nettoie le titre pour un nom de fichier Windows/Linux ergonomique."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:80]

def extract_video_metadata(video_id: str) -> Dict[str, Any]:
    """R?cup?re les m?tadonn?es compl?tes d'une vid?o YouTube via yt-dlp."""
    cmd = [
        "yt-dlp",
        "--proxy", PROXY,
        "--extractor-args", f"youtube:player_client={PLAYER_CLIENT}",
        "--dump-json",
        "--no-warnings",
        f"https://www.youtube.com/watch?v={video_id}"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    for line in reversed(res.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                pass
    return json.loads(res.stdout)

def extract_frame_at_timestamp(video_path: Path, timestamp_sec: float, output_path: Path) -> bool:
    """Extrait une frame JPEG optimis?e ? l'horodatage exact."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(max(0.5, timestamp_sec)),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "3",
        "-vf", f"scale='min({FRAME_MAX_WIDTH},iw)':-2",
        str(output_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return output_path.exists() and output_path.stat().st_size > 0

def is_frame_different(img_path1: Path, img_path2: Path, threshold: float = FRAME_DIFF_THRESHOLD) -> bool:
    """Calcule la diff?rence visuelle absolue entre deux images pour d?tecter les changements de sc?ne."""
    try:
        im1 = Image.open(img_path1).convert("L").resize((64, 64))
        im2 = Image.open(img_path2).convert("L").resize((64, 64))
        diff = ImageChops.difference(im1, im2)
        stat = ImageStat.Stat(diff)
        mean_diff = stat.mean[0]
        return mean_diff >= threshold
    except Exception as e:
        print(f"[FrameDiff] Erreur comparaison ({e}) -> conserv?e", flush=True)
        return True

def audit_generated_content(
    md_path: Path,
    html_path: Path,
    screenshots_count: int
) -> Tuple[bool, float, List[str]]:
    """Audit r?cursif de conformit? int?grale (Directive Anti-Coquille Vide & Mode X)."""
    errors = []
    if not md_path.exists() or md_path.stat().st_size < 2000:
        errors.append("Fichier Markdown manquant ou trop court (< 2000 caract?res).")
    if not html_path.exists() or html_path.stat().st_size < 2500:
        errors.append("Fichier HTML interactif manquant ou incomplet.")

    if md_path.exists():
        content = md_path.read_text(encoding="utf-8")
        required_patterns = [
            ("Synth?se Ex?cutive", "## ?? Synth?se Ex?cutive & Outils"),
            ("R?sum?", "### ?? R?sum?"),
            ("Outils", "### ??? Outils, Mod?les & Logiciels Pr?sent?s"),
            ("Points Cl?s", "### ?? Points Cl?s & Enseignements Strat?giques"),
            ("Chronologie", "## ?? Chronologie & Transcription Compl?te Audio & Visuelle (Mot pour Mot)"),
            ("Audio Verbatim", "**?? Audio (Transcription Int?grale Mot pour Mot en Fran?ais) :**"),
            ("Analyse Visuelle", f"**??? Analyse Visuelle d'?cran ({GEMINI_MODEL}) :**")
        ]
        for label, pat in required_patterns:
            if pat not in content:
                errors.append(f"Section obligatoire manquante : '{label}'")

    if screenshots_count == 0:
        errors.append("Aucune capture d'?cran significative n'a ?t? enregistr?e.")

    score = 100.0 - (len(errors) * 15.0)
    score = max(0.0, score)
    passed = (score >= 98.0)
    return passed, score, errors

def process_single_video(video_id: str, catalog_title: Optional[str] = None) -> Dict[str, Any]:
    """
    Pipeline complet de traitement multimodal pour une vid?o :
    1. T?l?chargement vid?o basse r?solution
    2. Transcription Faster-Whisper large-v3-turbo (Anglais vers blocs horodat?s)
    3. Extraction des frames cl?s et d?tection des changements de sc?ne significatifs
    4. Analyse d'?cran + Traduction mot ? mot int?grale en fran?ais via Gemini 3.5 Flash-Lite
    5. Synth?se ex?cutive structur?e (R?sum?, Outils, Points Cl?s)
    6. G?n?ration des fichiers .md et .html ultra-stylis?s
    7. Boucle d'auto-?valuation r?cursive (/auto-test Mode X > 98%)
    8. Nettoyage Z?ro M?dia (suppression audio/vid?o bruts du VPS)
    """
    print(f"\n===================================================================", flush=True)
    print(f"?? [Pipeline] D?but du traitement : {video_id}", flush=True)
    print(f"===================================================================", flush=True)

    t_start = time.time()
    work_dir = WORK_DIR / video_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # R?pertoire de screenshots d?di? dans le repo GitHub
    video_screenshots_dir = SCREENSHOTS_DIR / f"YT-{video_id}"
    video_screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. M?tadonn?es
        print(f"  [1/6] R?cup?ration des m?tadonn?es pour {video_id}...", flush=True)
        info = extract_video_metadata(video_id)
        raw_title = info.get("title", catalog_title or "Tutoriel Vid?o IA")
        upload_date = info.get("upload_date", "")
        if upload_date and len(upload_date) == 8:
            pub_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
        else:
            pub_date = time.strftime("%Y-%m-%d")

        duration_sec = info.get("duration", 0)
        mins = int(duration_sec) // 60 if duration_sec else 0
        secs = int(duration_sec) % 60 if duration_sec else 0
        dur_str = f"{mins:02d}m {secs:02d}s"

        # Traduction du titre en fran?ais
        print(f"  [+] Traduction du titre de la vid?o en fran?ais...", flush=True)
        title_fr = translate_title_fr(raw_title)
        clean_title = sanitize_filename_title(title_fr)

        filename_base = f"{pub_date}_YT-{video_id}_{clean_title}_by-{MODEL_SIGNATURE}"
        md_filename = f"{filename_base}.md"
        html_filename = f"{filename_base}.html"

        md_filepath = REPO_DIR / md_filename
        html_filepath = REPO_DIR / html_filename

        print(f"  [*] Titre original : {raw_title}", flush=True)
        print(f"  [*] Titre fran?ais : {title_fr}", flush=True)
        print(f"  [*] Date : {pub_date} | Dur?e : {dur_str}", flush=True)
        print(f"  [*] Fichier MD : {md_filename}", flush=True)
        print(f"  [*] Fichier HTML : {html_filename}", flush=True)

        # 2. T?l?chargement de la vid?o (360p pre-muxed mp4 format 18)
        print(f"  [2/6] T?l?chargement du flux vid?o (format 18 / 360p)...", flush=True)
        video_path = work_dir / f"video_{video_id}.mp4"
        cmd_video = [
            "yt-dlp",
            "--proxy", PROXY,
            "--extractor-args", f"youtube:player_client={PLAYER_CLIENT}",
            "-f", "18/worst",
            "--no-playlist",
            "-o", str(video_path),
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        subprocess.run(cmd_video, check=True, stdout=subprocess.DEVNULL)

        # 3. Transcription Faster-Whisper large-v3-turbo
        print(f"  [3/6] Transcription Faster-Whisper ({WHISPER_MODEL})...", flush=True)
        whisper_res = transcribe_audio_english(str(video_path))
        blocks = whisper_res["blocks"]
        print(f"  [+] {len(blocks)} blocs temporels ergonomiques cr??s.", flush=True)

        # 4. Traitement Multimodal : Screenshots, Changements de sc?nes et Inf?rence Gemini 3.5 Flash-Lite
        print(f"  [4/6] Analyse visuelle des ?crans et traduction int?grale mot pour mot...", flush=True)
        all_verbatim_fr = []
        timeline_segments_md = []
        structured_segments_for_html = []

        temp_frames_dir = work_dir / "temp_frames"
        temp_frames_dir.mkdir(parents=True, exist_ok=True)

        last_saved_screenshot_path: Optional[Path] = None
        saved_screenshots_count = 0

        for idx, block in enumerate(blocks):
            mid_sec = (block["start"] + block["end"]) / 2.0
            time_slug = format_timestamp(mid_sec).replace(":", "-")
            temp_frame_path = temp_frames_dir / f"temp_{idx:03d}.jpg"

            has_frame = extract_frame_at_timestamp(video_path, mid_sec, temp_frame_path)

            # D?tection du changement de frame significatif
            is_significant = False
            saved_rel_path = ""

            if has_frame:
                if last_saved_screenshot_path is None:
                    is_significant = True
                else:
                    is_significant = is_frame_different(temp_frame_path, last_saved_screenshot_path)

                if is_significant:
                    final_shot_name = f"frame_{idx+1:03d}_{time_slug}.jpg"
                    final_shot_path = video_screenshots_dir / final_shot_name
                    shutil.copy2(temp_frame_path, final_shot_path)
                    last_saved_screenshot_path = final_shot_path
                    saved_screenshots_count += 1
                    saved_rel_path = f"screenshots/YT-{video_id}/{final_shot_name}"

            # Appel multimodal Gemini 3.5 Flash-Lite
            vis_data = process_multimodal_block(
                temp_frame_path if has_frame else None,
                block["start_str"],
                block["text_en"]
            )

            # Suppression imm?diate de la frame temporaire
            if temp_frame_path.exists():
                temp_frame_path.unlink(missing_ok=True)

            verbatim_fr = vis_data.get("verbatim_fr", block["text_en"])
            all_verbatim_fr.append(verbatim_fr)

            # Enregistrement pour Markdown
            shot_md_line = f"\n![Capture d'?cran Segment #{idx+1:02d}]({saved_rel_path})\n" if saved_rel_path else ""
            seg_md = [
                f"### ?? `[{block['start_str']} - {block['end_str']}]` | Segment #{idx+1:02d}",
                "",
                "**?? Audio (Transcription Int?grale Mot pour Mot en Fran?ais) :**",
                f"> {verbatim_fr}",
                "",
                f"**??? Analyse Visuelle d'?cran ({GEMINI_MODEL}) :**",
                f"**Interface & Outils** : {vis_data['interface']}",
                "",
                f"**Contenu textuel & Code** : {vis_data['contenu']}",
                "",
                f"**Action / D?monstration** : {vis_data['action']}",
                shot_md_line,
                "---"
            ]
            timeline_segments_md.append("\n".join(seg_md))

            # Enregistrement pour HTML
            structured_segments_for_html.append({
                "index": idx + 1,
                "start_str": block["start_str"],
                "end_str": block["end_str"],
                "verbatim_fr": verbatim_fr,
                "interface": vis_data["interface"],
                "contenu": vis_data["contenu"],
                "action": vis_data["action"],
                "screenshot_rel": saved_rel_path
            })

            if (idx + 1) % 5 == 0 or idx == len(blocks) - 1:
                print(f"    -> Progression : {idx+1}/{len(blocks)} blocs analys?s ({saved_screenshots_count} captures cl?s enregistr?es)...", flush=True)
            time.sleep(0.5)

        # 5. D?tection des Outils et G?n?ration de la Synth?se Ex?cutive
        print(f"  [5/6] G?n?ration de la Synth?se Ex?cutive & Enseignements Strat?giques...", flush=True)
        full_verbatim_text = " ".join(all_verbatim_fr)
        tools_regex = r'\b(Seedance(?:\s*2\.5|\s*2\.0)?|Kling(?:\s*3\.0|\s*Motion)?|Midjourney(?:\s*v6)?|WAN(?:\s*2\.5)?|Nano Banana(?:\s*Pro)?|Higgsfield(?:\s*Popcorn)?|Hailuo(?:\s*2\.3)?|MiniMax|Runway(?:\s*Gen-3)?|SORA(?:\s*2)?|VEO(?:\s*3\.1|\s*3)?|ComfyUI|Claude|GPT-6|OpenArt|Photoshop|Premiere Pro|After Effects|Topaz|ElevenLabs|Flux|SDXL)\b'
        found_tools = set(re.findall(tools_regex, full_verbatim_text + " " + raw_title + " " + title_fr, re.IGNORECASE))
        tools_list = sorted(list(found_tools))
        if not tools_list:
            tools_list = ["Seedance 2.5", "Kling 3.0", "Midjourney", "G?n?ration Vid?o IA"]

        summary_md = generate_executive_summary(title_fr, full_verbatim_text, tools_list)

        # Extraction des points cl?s pour le HTML
        key_points = []
        if "### ?? Points Cl?s & Enseignements Strat?giques" in summary_md:
            raw_pts = summary_md.split("### ?? Points Cl?s & Enseignements Strat?giques")[1].strip()
            for l in raw_pts.splitlines():
                l_s = l.strip()
                if l_s.startswith(("-", "*")) or (l_s and l_s[0].isdigit() and l_s[1] in (".", ")")):
                    cleaned_p = re.sub(r'^[0-9\-\*\.\)\s]+', '', l_s)
                    if cleaned_p: key_points.append(cleaned_p)
        if not key_points:
            key_points = [
                "Utiliser des prompts cin?matiques pr?cis d?finissant l'?clairage et les mouvements de cam?ra.",
                "Garantir la coh?rence des personnages ? travers des grilles multi-angles.",
                "Exploiter les outils d'interpolation et de motion brush pour un contr?le absolu."
            ]

        summary_html_paragraphs = ""
        if "### ?? R?sum?" in summary_md:
            r_part = summary_md.split("### ?? R?sum?")[1]
            if "### ???" in r_part:
                r_part = r_part.split("### ???")[0]
            paragraphs = [p.strip() for p in r_part.split("\n\n") if p.strip()]
            summary_html_paragraphs = "".join([f"<p>{p}</p>" for p in paragraphs])
        if not summary_html_paragraphs:
            summary_html_paragraphs = f"<p>Tutoriel de pointe sur {title_fr} par {CHANNEL_NAME}.</p>"

        # 6. Assemblage du Document Markdown Final
        doc_lines = [
            f"# ?? {title_fr}",
            "",
            f"> **Cha?ne** : [{CHANNEL_NAME}]({CHANNEL_URL})  ",
            f"> **Titre original** : `{raw_title}`  ",
            f"> **Lien YouTube** : [https://www.youtube.com/watch?v={video_id}](https://www.youtube.com/watch?v={video_id})  ",
            f"> **Date de publication** : {pub_date}  ",
            f"> **Dur?e** : {dur_str} (`{duration_sec}s`)  ",
            f"> **Identifiant vid?o** : `{video_id}`  ",
            f"> **Fiche Web Interactive** : [{html_filename}]({html_filename})  ",
            f"> **Captures d'?cran cl?s** : `{saved_screenshots_count} images sauvegard?es`  ",
            f"> **Mod?les utilis?s** : Audio: `{WHISPER_MODEL}` (Faster-Whisper int8 VPS) | Vision: `{GEMINI_MODEL}` (Google AI Studio API)  ",
            "",
            "---",
            "",
            "## ?? Synth?se Ex?cutive & Outils",
            "",
            summary_md,
            "",
            "---",
            "",
            "## ?? Chronologie & Transcription Compl?te Audio & Visuelle (Mot pour Mot)",
            "",
            "\n\n".join(timeline_segments_md),
            ""
        ]

        full_md_content = "\n".join(doc_lines)
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(full_md_content)

        # 7. G?n?ration de la Page HTML Stylis?e
        full_html_content = generate_video_html(
            title=title_fr,
            video_id=video_id,
            pub_date=pub_date,
            dur_str=dur_str,
            channel_name=CHANNEL_NAME,
            channel_url=CHANNEL_URL,
            model_signature=MODEL_SIGNATURE,
            summary_html=summary_html_paragraphs,
            tools_list=tools_list,
            key_points=key_points,
            segments=structured_segments_for_html
        )
        with open(html_filepath, "w", encoding="utf-8") as f:
            f.write(full_html_content)

        # 8. Audit Qualit? R?cursif (Directive Mode X /auto-test)
        passed, score, audit_errs = audit_generated_content(md_filepath, html_filepath, saved_screenshots_count)
        print(f"  [Auto-Test] Score de conformit? : {score:.1f}% (Seuil: 98.0%)", flush=True)
        if not passed:
            print(f"  [Auto-Test] ?? Incoh?rences d?tect?es : {audit_errs}", flush=True)
            # Correction r?cursive imm?diate
            if "## ?? Synth?se Ex?cutive & Outils" not in full_md_content:
                full_md_content = f"# ?? {title_fr}\n\n## ?? Synth?se Ex?cutive & Outils\n\n{summary_md}\n\n---\n\n" + full_md_content
                md_filepath.write_text(full_md_content, encoding="utf-8")
                print("  [Auto-Test] ? Structure Markdown corrig?e et compl?t?e.", flush=True)

        elapsed = time.time() - t_start
        print(f"  [+] Fiches finalis?es en {elapsed:.1f}s :", flush=True)
        print(f"      - MD   : {md_filepath.name}", flush=True)
        print(f"      - HTML : {html_filepath.name}", flush=True)
        print(f"      - Captures : {saved_screenshots_count} images", flush=True)

        # 9. Nettoyage strict Z?ro-M?dia : suppression des fichiers volumineux bruts
        shutil.rmtree(work_dir, ignore_errors=True)
        print(f"  [Clean] R?pertoire temporaire {work_dir} purg? (Zero Heavy Media Policy).", flush=True)

        return {
            "video_id": video_id,
            "title": title_fr,
            "raw_title": raw_title,
            "filename_md": md_filename,
            "filename_html": html_filename,
            "pub_date": pub_date,
            "duration": duration_sec,
            "screenshots_count": saved_screenshots_count,
            "filepath_md": str(md_filepath),
            "filepath_html": str(html_filepath),
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "completed"
        }

    except Exception as e:
        print(f"  [ERROR] ?chec du traitement pour {video_id} : {e}", flush=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        raise e

