import os
import sys
import json
import base64
import time
import socket
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import (
    GEMINI_KEYS_FILE,
    GEMINI_MODEL,
    CHANNEL_NAME
)

socket.setdefaulttimeout(60)

def load_keys() -> List[str]:
    keys = []
    if GEMINI_KEYS_FILE.exists():
        with open(GEMINI_KEYS_FILE, "r", encoding="utf-8") as f:
            keys = [k.strip() for k in f if k.strip() and not k.startswith("#")]
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key and env_key not in keys:
        keys.append(env_key.strip())
    if not keys:
        raise ValueError("Aucune cl? API Gemini disponible.")
    return keys

_KEYS = load_keys()
_KI = [0]
STATS = {"calls": 0, "rotations": 0, "failures": 0}

def call_gemini(parts: List[Dict[str, Any]], model: str = GEMINI_MODEL, retries: int = 8, initial_backoff: int = 10) -> str:
    """Appel hautement r?silient ? Gemini avec rotation automatique des 10 cl?s et backoff exponentiel."""
    data = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096
        }
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    for rnd in range(retries):
        for _ in range(max(1, len(_KEYS))):
            key = _KEYS[_KI[0] % len(_KEYS)]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                STATS["calls"] += 1
                candidates = result.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    return "".join(p.get("text", "") for p in candidates[0]["content"].get("parts", [])).strip()
                return ""
            except urllib.error.HTTPError as e:
                _KI[0] += 1
                if e.code in (429, 503, 500):
                    STATS["rotations"] += 1
                    time.sleep(1.5)
                    continue
                err_text = e.read().decode("utf-8", "ignore")[:200]
                print(f"[Gemini] HTTPError {e.code}: {err_text}", flush=True)
            except Exception as e:
                _KI[0] += 1
                time.sleep(2)

        wait_s = initial_backoff * (rnd + 1)
        print(f"[Gemini] Quotas temporairement atteints. Pause {wait_s}s (essai {rnd+1}/{retries})...", flush=True)
        time.sleep(wait_s)

    STATS["failures"] += 1
    return ""

def translate_title_fr(title_en: str) -> str:
    """Traduit le titre anglais en fran?ais percutant et professionnel."""
    prompt = (
        "Tu es un traducteur expert en vid?o IA, infographie et cin?ma num?rique.\n"
        "Traduis ce titre de vid?o YouTube de l'anglais vers un fran?ais percutant, captivant et naturel.\n"
        "Garde les noms de logiciels/outils/mod?les intacts (Seedance, Kling, Midjourney, Wan, Nano Banana, Claude, GPT, etc.).\n"
        "R?ponds STRICTEMENT avec le titre traduit uniquement, sans guillemets ni fioritures.\n\n"
        f"Titre : {title_en}"
    )
    res = call_gemini([{"text": prompt}])
    return res.strip().replace('"', '') if res else title_en

def process_multimodal_block(image_path: Optional[Path], timestamp_str: str, text_en: str) -> Dict[str, str]:
    """
    Traite un bloc temporel en UNE SEULE requ?te Gemini 3.5 Flash-Lite :
    1. Analyse visuelle chirurgicale de l'?cran en fran?ais (Interface, Contenu/Code, Action)
    2. Traduction mot ? mot int?grale (verbatim) du discours anglais en fran?ais sans rien omettre ni r?sumer.
    """
    default_res = {
        "verbatim_fr": text_en,
        "interface": "Jack face cam?ra ou transition d'?cran.",
        "contenu": "Explications orales des concepts et des m?thodes de cr?ation vid?o IA.",
        "action": "D?monstration p?dagogique et pr?sentation du workflow."
    }

    prompt = (
        f"Tu es un analyste expert en intelligence artificielle g?n?rative vid?o et cin?ma num?rique pour la cha?ne {CHANNEL_NAME} (minutage {timestamp_str}).\n"
        f"Voici le discours audio anglais prononc? dans ce segment :\n"
        f'"""\n{text_en}\n"""\n\n'
        "Ta mission en fran?ais :\n"
        "1. VERBATIM_FR : Traduis le discours audio mot ? mot int?gralement en fran?ais, naturel, fluide, sans RIEN omettre ni abr?ger.\n"
        "2. INTERFACE : D?cris pr?cis?ment les interfaces, logiciels ou sites affich?s sur l'image (ex: Seedance 2.5, Kling 3.0, Midjourney, ComfyUI, Premiere, Runway, Discord, navigateur web, ou Jack face cam?ra).\n"
        "3. CONTENU : D?taille tous les textes, prompts de g?n?ration, param?tres techniques visibles (motion, camera pan/tilt, seed, fps, ratio aspect, prompts n?gatifs, etc.).\n"
        "4. ACTION : D?cris l'action montr?e ou manipul?e (clics, s?lection de param?tres, lecture du r?sultat vid?o, comparaison c?te-?-c?te, etc.).\n\n"
        "Format STRICT obligatoire de ta r?ponse :\n"
        "[VERBATIM_FR] <traduction mot ? mot compl?te en fran?ais>\n"
        "[INTERFACE] <texte>\n"
        "[CONTENU] <texte>\n"
        "[ACTION] <texte>"
    )

    parts = [{"text": prompt}]

    if image_path and image_path.exists() and image_path.stat().st_size > 0:
        try:
            with open(image_path, "rb") as f:
                b64_img = base64.b64encode(f.read()).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64_img
                }
            })
        except Exception as e:
            print(f"[Gemini Vision] Erreur lecture image {image_path}: {e}", flush=True)

    raw = call_gemini(parts)
    if not raw:
        return default_res

    res = dict(default_res)
    try:
        if "[VERBATIM_FR]" in raw and "[INTERFACE]" in raw:
            p_v = raw.split("[INTERFACE]")[0].replace("[VERBATIM_FR]", "").strip()
            rest = raw.split("[INTERFACE]")[1]
            p_i = rest.split("[CONTENU]")[0].strip() if "[CONTENU]" in rest else ""
            rest2 = rest.split("[CONTENU]")[1] if "[CONTENU]" in rest else ""
            p_c = rest2.split("[ACTION]")[0].strip() if "[ACTION]" in rest2 else ""
            p_a = rest2.split("[ACTION]")[1].strip() if "[ACTION]" in rest2 else ""

            if p_v: res["verbatim_fr"] = p_v
            if p_i: res["interface"] = p_i
            if p_c: res["contenu"] = p_c
            if p_a: res["action"] = p_a
        elif "[VERBATIM]" in raw and "[DESCRIPTION]" in raw:
            res["verbatim_fr"] = raw.split("[VERBATIM]")[1].strip()
            res["action"] = raw.split("[VERBATIM]")[0].replace("[DESCRIPTION]", "").strip()
        else:
            res["verbatim_fr"] = raw.strip()
    except Exception as e:
        print(f"[Gemini] Erreur parsing bloc multimodal : {e}", flush=True)

    return res

def generate_executive_summary(video_title: str, full_verbatim_fr: str, tools_detected: List[str]) -> str:
    """
    R?dige la synth?se ex?cutive haut de gamme calqu?e sur l'exemple de r?f?rence :
    - ### ?? R?sum? (2-3 paragraphes complets et percutants)
    - ### ??? Outils, Mod?les & Logiciels Pr?sent?s (liste ? puces exhaustive)
    - ### ?? Points Cl?s & Enseignements Strat?giques (8-12 points concrets)
    """
    tools_str = ", ".join(tools_detected) if tools_detected else "Seedance, Kling AI, Midjourney, Vid?o IA, Motion Design"
    prompt = (
        f"Tu es un r?alisateur et analyste expert en vid?o par intelligence artificielle.\n"
        f"Vid?o de {CHANNEL_NAME} intitul?e : ? {video_title} ?.\n"
        f"Outils identifi?s : {tools_str}\n\n"
        f"Transcription int?grale mot pour mot de la vid?o en fran?ais :\n\"\"\"\n{full_verbatim_fr[:9000]}\n\"\"\"\n\n"
        "R?dige une synth?se ex?cutive structur?e, dense, fluide et tr?s riche en enseignements concrets en fran?ais :\n"
        "Respecte STRICTEMENT ce plan en Markdown :\n"
        "### ?? R?sum?\n"
        "(2 ? 3 paragraphes denses et immersifs expliquant le sujet central, les techniques innovantes, la m?thode ?tape par ?tape de Jack et les b?n?fices concrets pour les cr?ateurs de vid?o)\n\n"
        "### ??? Outils, Mod?les & Logiciels Pr?sent?s\n"
        "(Liste ? puces exhaustive avec nom de l'outil en gras et une phrase expliquant son r?le pr?cis dans le tutoriel)\n\n"
        "### ?? Points Cl?s & Enseignements Strat?giques\n"
        "(8 ? 12 points cl?s d?taill?s, percutants et actionnables r?sumant les astuces de prompt, les r?glages de cam?ra, les workflows et les pi?ges ? ?viter)"
    )

    parts = [{"text": prompt}]
    res = call_gemini(parts)
    if not res:
        res = (
            "### ?? R?sum?\n"
            f"Dans ce tutoriel complet intitul? **{video_title}**, Jack pr?sente les techniques de pointe pour ma?triser la g?n?ration de vid?os et de visuels par intelligence artificielle.\n\n"
            "### ??? Outils, Mod?les & Logiciels Pr?sent?s\n"
            "- **Mod?les vid?o IA** : G?n?ration de plans cin?matiques.\n"
            "- **Outils de prompt** : Structuration avanc?e des descriptions visuelles.\n\n"
            "### ?? Points Cl?s & Enseignements Strat?giques\n"
            "- Structurer ses prompts de mouvement avec des termes de cam?ra pr?cis.\n"
            "- Soigner la coh?rence des personnages entre chaque plan.\n"
            "- Exploiter les mod?les de derni?re g?n?ration pour un rendu professionnel."
        )
    return res

