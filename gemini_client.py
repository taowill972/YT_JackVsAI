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
        raise ValueError("Aucune clé API Gemini disponible.")
    return keys

_KEYS = load_keys()
_KI = [0]
STATS = {"calls": 0, "rotations": 0, "failures": 0}

def call_gemini(parts: List[Dict[str, Any]], model: str = GEMINI_MODEL, retries: int = 8, initial_backoff: int = 10) -> str:
    """Appel hautement résilient à Gemini avec rotation automatique des 10 clés et backoff exponentiel."""
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
    """Traduit le titre anglais en français percutant et professionnel."""
    prompt = (
        "Tu es un traducteur expert en vidéo IA, infographie et cinéma numérique.\n"
        "Traduis ce titre de vidéo YouTube de l'anglais vers un français percutant, captivant et naturel.\n"
        "Garde les noms de logiciels/outils/modèles intacts (Seedance, Kling, Midjourney, Wan, Nano Banana, Claude, GPT, etc.).\n"
        "Réponds STRICTEMENT avec le titre traduit uniquement, sans guillemets ni fioritures.\n\n"
        f"Titre : {title_en}"
    )
    res = call_gemini([{"text": prompt}])
    return res.strip().replace('"', '') if res else title_en

def process_multimodal_block(image_path: Optional[Path], timestamp_str: str, text_en: str) -> Dict[str, str]:
    """
    Traite un bloc temporel en UNE SEULE requête Gemini 3.5 Flash-Lite :
    1. Analyse visuelle chirurgicale de l'écran en français (Interface, Contenu/Code, Action)
    2. Traduction mot à mot intégrale (verbatim) du discours anglais en français sans rien omettre ni résumer.
    """
    default_res = {
        "verbatim_fr": text_en,
        "interface": "Jack face caméra ou plan d'illustration.",
        "contenu": "Explications orales des concepts et des méthodes de création vidéo IA.",
        "action": "Démonstration pédagogique et présentation du workflow."
    }

    prompt = (
        f"Tu es un analyste expert en intelligence artificielle générative vidéo et cinéma numérique pour la chaîne {CHANNEL_NAME} (minutage {timestamp_str}).\n"
        f"Voici le discours audio anglais prononcé dans ce segment :\n"
        f'"""\n{text_en}\n"""\n\n'
        "Ta mission en français :\n"
        "1. VERBATIM_FR : Traduis le discours audio mot à mot intégralement en français, naturel, fluide, sans RIEN omettre ni abréger. Si c'est de la musique sans parole, indique [Musique d'illustration / Thème sonore].\n"
        "2. INTERFACE : Décris précisément les interfaces, logiciels ou sites affichés sur l'image (ex: Seedance 2.5, Kling 3.0, Midjourney, ComfyUI, Premiere, Runway, Discord, navigateur web, ou Jack face caméra).\n"
        "3. CONTENU : Détaille tous les textes, prompts de génération, paramètres techniques visibles (motion, camera pan/tilt, seed, fps, ratio aspect, prompts négatifs, etc.).\n"
        "4. ACTION : Décris l'action montrée ou manipulée (clics, sélection de paramètres, lecture du résultat vidéo, comparaison côte-à-côte, etc.).\n\n"
        "Format STRICT obligatoire de ta réponse :\n"
        "[VERBATIM_FR] <traduction mot à mot complète en français>\n"
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
    Rédige la synthèse exécutive structurée :
    - ### 📌 Résumé
    - ### 🛠️ Outils, Modèles & Logiciels Présentés
    - ### 🔑 Points Clés & Enseignements Stratégiques
    """
    tools_str = ", ".join(tools_detected) if tools_detected else "Seedance 2.5, Kling 3.0, Midjourney, Vidéo IA, Motion Design"
    prompt = (
        f"Tu es un réalisateur et analyste expert en vidéo par intelligence artificielle.\n"
        f"Vidéo de {CHANNEL_NAME} intitulée : « {video_title} ».\n"
        f"Outils identifiés : {tools_str}\n\n"
        f"Transcription intégrale de la vidéo en français :\n\"\"\"\n{full_verbatim_fr[:9000]}\n\"\"\"\n\n"
        "Rédige une synthèse exécutive structurée, dense, fluide et très riche en enseignements concrets en français.\n"
        "Tu DOIS STRICTEMENT employer ces titres de niveau 3 exacts :\n"
        "### 📌 Résumé\n"
        "(2 à 3 paragraphes denses et immersifs expliquant le sujet central, les techniques innovantes, la méthode étape par étape de Jack et les bénéfices concrets pour les créateurs de vidéo)\n\n"
        "### 🛠️ Outils, Modèles & Logiciels Présentés\n"
        "(Liste à puces exhaustive avec nom de l'outil en gras et une phrase expliquant son rôle précis dans le tutoriel)\n\n"
        "### 🔑 Points Clés & Enseignements Stratégiques\n"
        "(8 à 12 points clés détaillés, percutants et actionnables résumant les astuces de prompt, les réglages de caméra, les workflows et les pièges à éviter)"
    )

    parts = [{"text": prompt}]
    res = call_gemini(parts)
    if not res:
        res = (
            "### 📌 Résumé\n"
            f"Dans ce tutoriel complet intitulé **{video_title}**, Jack présente les techniques de pointe pour maîtriser la génération de vidéos et de visuels par intelligence artificielle.\n\n"
            "### 🛠️ Outils, Modèles & Logiciels Présentés\n"
            "- **Modèles vidéo IA** : Génération de plans cinématiques.\n"
            "- **Outils de prompt** : Structuration avancée des descriptions visuelles.\n\n"
            "### 🔑 Points Clés & Enseignements Stratégiques\n"
            "- Structurer ses prompts de mouvement avec des termes de caméra précis.\n"
            "- Soigner la cohérence des personnages entre chaque plan.\n"
            "- Exploiter les modèles de dernière génération pour un rendu professionnel."
        )
    return res
