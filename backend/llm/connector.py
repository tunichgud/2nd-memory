"""
connector.py – LLM-Abstraktion für memosaur.

Unterstützt:
  - Ollama (lokal, Standard)
  - OpenAI
  - Anthropic

Konfiguration über config.yaml (llm.provider, llm.model, llm.vision_model).
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Noise-Loggers drosseln (HuggingFace/HTTPX-Gequassel vermeiden)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Konfiguration laden
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parents[2] / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


_cfg: dict | None = None


def get_cfg() -> dict:
    global _cfg
    if _cfg is None:
        _cfg = _load_config()

        # ENV-Variablen haben Priorität über config.yaml (Security Best Practice)
        # ⚠️  PRIVACY: Nutze externe APIs nur wenn du bewusst Daten teilen willst!
        if "OPENAI_API_KEY" in os.environ:
            _cfg["llm"]["api_key"] = os.environ["OPENAI_API_KEY"]
            logger.warning("⚠️  OPENAI_API_KEY aus ENV geladen - Daten werden an OpenAI gesendet!")
        elif "ANTHROPIC_API_KEY" in os.environ:
            _cfg["llm"]["api_key"] = os.environ["ANTHROPIC_API_KEY"]
            logger.warning("⚠️  ANTHROPIC_API_KEY aus ENV geladen - Daten werden an Anthropic gesendet!")
        elif "GEMINI_API_KEY" in os.environ:
            _cfg["llm"]["api_key"] = os.environ["GEMINI_API_KEY"]
            logger.warning("⚠️  GEMINI_API_KEY aus ENV geladen - Daten werden an Google gesendet!")

        # Ollama Host aus ENV (falls auf anderem Host)
        if "OLLAMA_HOST" in os.environ:
            _cfg["llm"]["base_url"] = os.environ["OLLAMA_HOST"]

    return _cfg


# ---------------------------------------------------------------------------
# Ollama-Client (gecacht)
# ---------------------------------------------------------------------------

_ollama_client: Any = None


def _get_ollama_client():
    global _ollama_client
    if _ollama_client is None:
        import ollama
        cfg = get_cfg()["llm"]
        _ollama_client = ollama.Client(host=cfg["base_url"])
    return _ollama_client


# ---------------------------------------------------------------------------
# Text-Chat
# ---------------------------------------------------------------------------

def _strip_thinking(text: str) -> str:
    """Entfernt <think>...</think> Blöcke aus qwen3/deepseek-r1 Antworten."""
    import re
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def chat(messages: list[dict], model: str | None = None, tools: list | None = None) -> str:
    """Sendet eine Chat-Anfrage an das konfigurierte LLM und gibt den Antworttext zurück."""
    cfg = get_cfg()["llm"]
    provider = cfg["provider"]
    model = model or cfg["model"]

    if provider == "ollama":
        client = _get_ollama_client()
        response = client.chat(model=model, messages=messages)
        return _strip_thinking(response["message"]["content"].strip())

    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=cfg.get("api_key", ""))
        response = client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content.strip()

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=cfg.get("api_key", ""))
        # Anthropic erwartet system-Nachrichten separat
        system = ""
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                filtered.append(m)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=filtered,
        )
        return response.content[0].text.strip()

    elif provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=cfg.get("api_key", ""))
        
        # Gemini erwartet system_instruction separat, User/Assistant-Messages als History
        system_msg = ""
        history = []
        last_user = None
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            elif m["role"] == "user":
                last_user = m["content"]
            elif m["role"] == "assistant" and last_user:
                history.append({"role": "user",  "parts": [last_user]})
                history.append({"role": "model", "parts": [m["content"]]})
                last_user = None
                
        kwargs = {}
        if system_msg:
            kwargs["system_instruction"] = system_msg
        if tools:
            kwargs["tools"] = tools
            
        gmodel = genai.GenerativeModel(model, **kwargs)
        
        chat_session = gmodel.start_chat(
            history=history,
            enable_automatic_function_calling=bool(tools)
        )
        response = chat_session.send_message(last_user or "")
        return _strip_thinking(response.text.strip())

    else:
        raise ValueError(f"Unbekannter LLM-Provider: {provider}")


async def chat_stream(messages: list[dict], model: str | None = None, tools: list | None = None):
    """Asynchroner Generator für Chat-Streams.
    Wertet Tool-Calls manuell aus, um dem Frontend "Plan"-Ereignisse zu senden.

    Yields:
        {'type': 'thought', 'content': '...'} für ReAct Thought
        {'type': 'tool_call', 'content': {...}} für Tool-Aufruf
        {'type': 'tool_result', 'content': {...}} für Tool-Ergebnis
        {'type': 'text', 'content': '...'} für finale Text-Chunks
    """
    import asyncio
    cfg = get_cfg()["llm"]
    provider = cfg["provider"]
    model = model or cfg["model"]

    if provider != "gemini":
        # Fallback: Kein Stream/Tools für andere Modelle (reicht für MVP)
        res = chat(messages, model, tools)
        yield {"type": "text", "content": res}
        return

    import google.generativeai as genai
    genai.configure(api_key=cfg.get("api_key", ""))

    system_msg = ""
    history = []
    last_user = None
    for m in messages:
        if m["role"] == "system":
            system_msg = m["content"]
        elif m["role"] == "user":
            last_user = m["content"]
        elif m["role"] == "assistant" and last_user:
            history.append({"role": "user",  "parts": [last_user]})
            history.append({"role": "model", "parts": [m["content"]]})
            last_user = None

    kwargs = {}
    if system_msg:
        kwargs["system_instruction"] = system_msg
    if tools:
        kwargs["tools"] = tools

    gmodel = genai.GenerativeModel(model, **kwargs)
    
    # NICHT automatic function calling aktivieren! Wir reifen die Tools manuell ab.
    chat_session = gmodel.start_chat(history=history)

    current_prompt = last_user or ""
    tool_map = {t.__name__: t for t in tools} if tools else {}

    # Event-Loop-Abbruch-Check (CancelledError) wird von uvicorn geworfen,
    # wenn der Client die SSE-Verbindung trennt.
    MAX_STEPS = 5
    logger.info("=== chat_stream SYSTEM_PROMPT (first 500 chars): %s...", system_msg[:500])
    logger.info("=== chat_stream USER_PROMPT (first 800 chars): %s...", (last_user or "")[:800])
    for step in range(MAX_STEPS):
        # Wir streamen die Antwort NICHT solange er Tools ruft, sondern erst am Ende.
        response = chat_session.send_message(current_prompt, stream=False)

        # Prüfen ob Gemini ein Tool aufrufen möchte
        function_calls = response.parts if hasattr(response, 'parts') else []
        fc = None
        plan_text = None
        for part in function_calls:
            if hasattr(part, 'text') and part.text.strip():
                # Text-Part vor dem Tool-Aufruf gefunden (ReAct-Gedanke)
                plan_text = part.text.strip()
            elif hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                break
                
        if fc and fc.name in tool_map:
            # Schritt 1: Thought (ReAct Reasoning)
            if plan_text:
                yield {"type": "thought", "content": plan_text}

            # Schritt 2: Tool Call (Action)
            friendly_args = {k: v for k, v in fc.args.items()}
            yield {
                "type": "tool_call",
                "content": {
                    "tool": fc.name,
                    "args": friendly_args,
                    "status": "running"
                }
            }

            # Tool ausführen
            tool_func = tool_map[fc.name]
            args = {k: v for k, v in fc.args.items()}
            logger.info(f"Manual Tool Call: {fc.name}({args})")

            # Da Tools blocking sein könnten, mit asyncio abfangen
            try:
                tool_res = tool_func(**args)
                tool_error = None
            except Exception as e:
                logger.error(f"Tool error: {e}")
                tool_res = f"Fehler bei Tool-Ausführung: {e}"
                tool_error = str(e)

            # Schritt 3: Tool Result (Observation)
            # Parse JSON wenn Tool structured output liefert
            import json as json_lib
            try:
                parsed = json_lib.loads(tool_res) if isinstance(tool_res, str) else tool_res
                new_sources_count = len(parsed.get("new_sources", [])) if isinstance(parsed, dict) else 0
                summary = f"{new_sources_count} neue Quellen" if new_sources_count > 0 else "Keine neuen Quellen"
            except:
                summary = f"{len(tool_res[:100])}+ Zeichen" if isinstance(tool_res, str) else "Ergebnis erhalten"

            yield {
                "type": "tool_result",
                "content": {
                    "tool": fc.name,
                    "summary": summary,
                    "status": "error" if tool_error else "success",
                    "error": tool_error
                }
            }

            # Das Resultat als Antwort von uns (dem "System") ins Model füttern
            current_prompt = genai.protos.Content(
                role="user", # Bei manual calls oft als "function" role
                parts=[
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fc.name,
                            response={"result": tool_res}
                        )
                    )
                ]
            )
        else:
            # Keine Tools mehr -> Text Finale
            yield {"type": "thought", "content": "Formuliere finale Antwort..."}
            # Trick: Wir senden den current_prompt (sollte leer sein, oder die letzte func response)
            # noch einmal als Stream, um den Text chunk-weise zu Frontend zu feuern.
            # Da wir oben schon send_message ohne stream gemacht haben...
            # Eigentlich haben wir hier schon den Text.
            # Für echtes Streaming müssten wir send_message(stream=True) nutzen,
            # was aber mit function calls bei Gemini kompliziert ist.
            # -> Wir streamen den fertigen Text künstlich oder geben ihn am Stück.
            text = _strip_thinking(response.text.strip())

            # Wir stückeln ihn für eine "Tipp-Animation" (oder reichen ihn am Stück durch,
            # Frontend macht sowieso markdown rendering)
            yield {"type": "text", "content": text}
            break

# ---------------------------------------------------------------------------
# Vision (Bildbeschreibung)
# ---------------------------------------------------------------------------

# Maximale Bildgröße vor dem Senden an das Vision-Modell (Pixel, längste Seite).
# Kleinere Bilder = weniger VRAM-Druck, weniger GPU-Timeouts.
VISION_MAX_PX = 768


def _resize_image(image_bytes: bytes, max_px: int = VISION_MAX_PX) -> bytes:
    """Skaliert ein Bild auf max. max_px (längste Seite), gibt JPEG-Bytes zurück."""
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(image_bytes))
    # EXIF-Rotation anwenden falls vorhanden
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    w, h = img.size
    if max(w, h) > max_px:
        ratio = max_px / max(w, h)
        resample = getattr(Image.Resampling, "LANCZOS", 1)  # 1 = LANCZOS in alten Versionen
        img = img.resize((int(w * ratio), int(h * ratio)), resample)

    # Als RGB-JPEG speichern (entfernt Alpha-Kanal falls vorhanden)
    if img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def describe_image(image_bytes: bytes, prompt: str | None = None) -> str:
    """Analysiert ein Bild und gibt eine deutschsprachige Beschreibung zurück.

    Bilder werden vor dem Senden auf VISION_MAX_PX skaliert um GPU-Timeouts
    durch zu hohen VRAM-Verbrauch zu vermeiden.
    """
    import time

    cfg = get_cfg()["llm"]
    provider = cfg.get("vision_provider") or cfg["provider"]
    vision_model = cfg["vision_model"]

    if prompt is None:
        prompt = (
            "Beschreibe dieses Bild in 2-4 Sätzen auf Deutsch. "
            "Fokussiere dich auf: Personen (Anzahl, Geschlecht, Aktivität), "
            "Ort/Umgebung (drinnen/draußen, Art des Ortes), "
            "sichtbare Objekte (Essen, Gegenstände, Fahrzeuge), "
            "Stimmung und Tageszeit. "
            "Sei präzise und faktisch."
        )

    # Bild skalieren
    try:
        image_bytes = _resize_image(image_bytes)
    except Exception as exc:
        logger.warning("Bild-Resize fehlgeschlagen, sende Original: %s", exc)

    if provider == "ollama":
        client = _get_ollama_client()
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        last_exc: Exception | None = None
        for attempt in range(1, 4):  # bis zu 3 Versuche
            try:
                response = client.chat(
                    model=vision_model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        }
                    ],
                    options={
                        # Nach jedem Aufruf VRAM für 5 Minuten behalten, gut für fortlaufende Ingestion
                        "keep_alive": "5m",
                    },
                )
                return _strip_thinking(response["message"]["content"].strip())
            except Exception as exc:
                last_exc = exc
                logger.warning("Vision Versuch %d/3 fehlgeschlagen: %s", attempt, exc)
                time.sleep(5 * attempt)  # 5s, 10s, 15s warten

        raise last_exc  # type: ignore[misc]

    elif provider == "gemini":
        import google.generativeai as genai
        import io
        from PIL import Image as PilImage
        genai.configure(api_key=cfg.get("api_key", ""))
        gmodel = genai.GenerativeModel(vision_model)
        # Bild als PIL-Image übergeben (Gemini SDK nimmt PIL direkt)
        img = PilImage.open(io.BytesIO(image_bytes))
        response = gmodel.generate_content([prompt, img])
        return _strip_thinking(response.text.strip())

    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=cfg.get("api_key", ""))
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        response = client.chat.completions.create(
            model=vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
        )
        return response.choices[0].message.content.strip()

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=cfg.get("api_key", ""))
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        response = client.messages.create(
            model=vision_model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return response.content[0].text.strip()

    else:
        raise ValueError(f"Unbekannter LLM-Provider: {provider}")


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

_st_model = None


def _get_st_model():
    """Gibt ein gecachtes SentenceTransformer-Modell zurück."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        model_name = "paraphrase-multilingual-MiniLM-L12-v2"
        logger.info("Lade Embedding-Modell %s …", model_name)
        
        try:
            # Versuche erst lokal (schaltet Hub-Check aus)
            _st_model = SentenceTransformer(model_name, local_files_only=True)
            logger.info("Embedding-Modell lokal geladen (Offline-Modus).")
        except Exception:
            # Fallback: Normal laden (darf ins Netz)
            _st_model = SentenceTransformer(model_name)
            logger.info("Embedding-Modell geladen (Online-Modus).")
            
    return _st_model


def embed(texts: list[str]) -> list[list[float]]:
    """Erzeugt Embedding-Vektoren für eine Liste von Texten.

    Verwendet immer sentence-transformers lokal (kein Ollama-Embedding-Modell
    nötig) – schneller, zuverlässiger und offline-fähig.
    """
    model = _get_st_model()
    return model.encode(texts, show_progress_bar=False).tolist()
