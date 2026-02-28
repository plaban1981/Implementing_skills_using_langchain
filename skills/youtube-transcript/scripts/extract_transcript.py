#!/usr/bin/env python3
"""
YouTube Transcript Extractor
Extracts transcripts from YouTube videos.

Strategy (tried in order):
  1. youtube-transcript-api  — fast, no external process
  2. yt-dlp subtitle download — fallback when YouTube blocks the API
     (handles IpBlocked, cloud IP restrictions, etc.)

Compatibility: youtube-transcript-api v0.x (dict) AND v1.x (FetchedTranscriptSnippet objects)
"""

import sys
import json
import re
import os
import tempfile
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# URL / ID helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract 11-char video ID from any YouTube URL format or bare ID."""
    url_or_id = url_or_id.strip()
    if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id):
        return url_or_id
    patterns = [
        r'(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([A-Za-z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url_or_id)
        if m:
            return m.group(1)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Segment normalisation (v0.x dict vs v1.x object)
# ─────────────────────────────────────────────────────────────────────────────

def _seg(segment) -> Dict:
    """Return a plain dict from either a v0.x dict or v1.x FetchedTranscriptSnippet."""
    if isinstance(segment, dict):
        return {"text": segment.get("text", ""), "start": segment.get("start", 0.0), "duration": segment.get("duration", 0.0)}
    return {"text": getattr(segment, "text", ""), "start": getattr(segment, "start", 0.0), "duration": getattr(segment, "duration", 0.0)}


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1 — youtube-transcript-api
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_via_api(video_id: str, languages: List[str]) -> Dict:
    """Attempt transcript extraction using youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"error": "youtube-transcript-api not installed", "_strategy": "api"}

    try:
        # Use cookies file if available (bypasses IpBlocked on cloud IPs)
        cookies_file = os.environ.get("YT_COOKIES_FILE", "")
        if cookies_file and os.path.exists(cookies_file):
            try:
                from youtube_transcript_api import CookieJar
                api = YouTubeTranscriptApi(cookie_path=cookies_file)
            except (ImportError, TypeError):
                # Older versions don't support cookie_path — fall through
                api = YouTubeTranscriptApi()
        else:
            api = YouTubeTranscriptApi()
        tlist = api.list(video_id)

        transcript = None
        found_lang = None

        for lang in languages:
            try:
                transcript = tlist.find_transcript([lang])
                found_lang = lang
                break
            except Exception:
                continue

        if transcript is None:
            try:
                transcript = tlist.find_generated_transcript(["en"])
                found_lang = "en (auto-generated)"
            except Exception:
                available = list(tlist)
                if available:
                    transcript = available[0]
                    found_lang = transcript.language_code
                else:
                    return {"error": "No transcripts available", "video_id": video_id, "_strategy": "api"}

        raw = transcript.fetch()
        segments = [_seg(s) for s in raw]

        available_languages = []
        try:
            for t in tlist:
                available_languages.append({"language": t.language, "language_code": t.language_code,
                                            "is_generated": t.is_generated})
        except Exception:
            pass

        return {
            "success": True, "_strategy": "api",
            "video_id": video_id, "language": found_lang,
            "segments": segments, "available_languages": available_languages,
        }

    except Exception as e:
        return {"error": str(e), "error_type": type(e).__name__, "_strategy": "api", "video_id": video_id}


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 2 — yt-dlp subtitle download
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_via_ytdlp(video_id: str, languages: List[str]) -> Dict:
    """
    Fallback: use yt-dlp to download auto-subtitles as VTT, then parse them.
    Handles IpBlocked and other API restrictions.
    Install: pip install yt-dlp
    """
    try:
        import yt_dlp
    except ImportError:
        return {"error": "yt-dlp not installed. Run: pip install yt-dlp", "_strategy": "ytdlp"}

    url = f"https://www.youtube.com/watch?v={video_id}"
    lang_codes = languages + ["en"]  # always try en as last resort

    with tempfile.TemporaryDirectory() as tmpdir:
        for lang in lang_codes:
            out_template = os.path.join(tmpdir, "sub")
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": [lang],
                "subtitlesformat": "vtt",
                "outtmpl": out_template,
                "quiet": True,
                "no_warnings": True,
            }
            # Use cookies if available
            _cf = os.environ.get("YT_COOKIES_FILE", "")
            if _cf and os.path.exists(_cf):
                ydl_opts["cookiefile"] = _cf
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # Find the downloaded .vtt file
                vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
                if not vtt_files:
                    continue

                vtt_path = os.path.join(tmpdir, vtt_files[0])
                segments = _parse_vtt(vtt_path)
                if segments:
                    return {
                        "success": True, "_strategy": "ytdlp",
                        "video_id": video_id, "language": lang,
                        "segments": segments, "available_languages": [],
                    }
            except Exception as e:
                last_err = str(e)
                continue

    return {"error": f"yt-dlp could not retrieve subtitles. Last error: {locals().get('last_err', 'unknown')}",
            "_strategy": "ytdlp", "video_id": video_id}


def _parse_vtt(vtt_path: str) -> List[Dict]:
    """Parse a WebVTT subtitle file into segment dicts."""
    segments = []
    seen_texts = set()  # deduplicate overlapping VTT cues

    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into cue blocks
    blocks = re.split(r"\n\n+", content.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        # Find the timestamp line: 00:00:01.000 --> 00:00:03.000
        ts_line = None
        text_lines = []
        for i, line in enumerate(lines):
            if "-->" in line:
                ts_line = line
                text_lines = lines[i + 1:]
                break
        if not ts_line or not text_lines:
            continue

        # Parse start time
        m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)", ts_line)
        if not m:
            m = re.match(r"(\d+):(\d+)[.,](\d+)", ts_line)
            if m:
                h, mi, s, ms = 0, int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                continue
        else:
            h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        start_seconds = h * 3600 + mi * 60 + s + ms / 1000

        # Clean text — strip VTT tags like <00:00:01.000><c>text</c>
        raw_text = " ".join(text_lines)
        clean = re.sub(r"<[^>]+>", "", raw_text).strip()
        clean = re.sub(r"\s+", " ", clean)

        if not clean or clean in seen_texts:
            continue
        seen_texts.add(clean)

        segments.append({"text": clean, "start": start_seconds, "duration": 0.0})

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# Public API — tries both strategies automatically
# ─────────────────────────────────────────────────────────────────────────────

def _build_full_result(video_id: str, raw: Dict, preserve_formatting: bool) -> Dict:
    """Build the final result dict from raw segment data."""
    segments = raw.get("segments", [])

    if preserve_formatting:
        full_text = ""
        for seg in segments:
            text = seg["text"].strip()
            if full_text and not full_text.endswith("\n"):
                if text and text[0].isupper() and full_text[-1] in ".!?":
                    full_text += "\n\n"
                else:
                    full_text += " "
            full_text += text
    else:
        full_text = " ".join(s["text"].strip() for s in segments)

    return {
        "success":             True,
        "video_id":            video_id,
        "language":            raw.get("language", "unknown"),
        "transcript":          full_text,
        "segments":            segments,
        "segment_count":       len(segments),
        "character_count":     len(full_text),
        "word_count":          len(full_text.split()),
        "available_languages": raw.get("available_languages", []),
        "extraction_method":   raw.get("_strategy", "unknown"),
    }


def get_transcript(video_id: str, languages: List[str] = None,
                   preserve_formatting: bool = True) -> Dict:
    """
    Get transcript for a YouTube video.
    Tries youtube-transcript-api first; falls back to yt-dlp on IpBlocked/error.
    """
    if languages is None:
        languages = ["en"]

    # Strategy 1: youtube-transcript-api
    result = _fetch_via_api(video_id, languages)
    if result.get("success"):
        return _build_full_result(video_id, result, preserve_formatting)

    api_error = result.get("error", "")
    print(f"[Transcript] API failed ({api_error[:80]}), trying yt-dlp fallback...")

    # Strategy 2: yt-dlp (handles IpBlocked, rate limits, cloud IP bans)
    result2 = _fetch_via_ytdlp(video_id, languages)
    if result2.get("success"):
        return _build_full_result(video_id, result2, preserve_formatting)

    # Both failed — return informative error
    ytdlp_error = result2.get("error", "yt-dlp unavailable")
    error_msg = api_error

    # Give a helpful user-facing message for common errors
    if "ipblocked" in api_error.lower() or "ip" in api_error.lower():
        error_msg = (
            "YouTube is blocking transcript access from this server's IP address (IpBlocked). "
            f"yt-dlp fallback also failed: {ytdlp_error}. "
            "Solutions: (1) Run the app locally instead of on a cloud server, "
            "(2) Install yt-dlp: pip install yt-dlp"
        )
    elif "disabled" in api_error.lower():
        error_msg = "Transcripts are disabled for this video by the creator."
    elif "unavailable" in api_error.lower() or "not found" in api_error.lower():
        error_msg = "Video is unavailable or private."

    return {
        "success": False,
        "error": error_msg,
        "api_error": api_error,
        "ytdlp_error": ytdlp_error,
        "video_id": video_id,
    }


def get_transcript_with_timestamps(video_id: str, languages: List[str] = None) -> Dict:
    """Get transcript with [MM:SS] or [HH:MM:SS] timestamp markers."""
    result = get_transcript(video_id, languages, preserve_formatting=False)
    if not result.get("success"):
        return result

    timestamped_segments = []
    for seg in result["segments"]:
        t = seg["start"]
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ts = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        timestamped_segments.append({
            "timestamp": ts, "start_seconds": t,
            "duration": seg["duration"], "text": seg["text"],
        })

    formatted_text = "\n".join(f"[{s['timestamp']}] {s['text']}" for s in timestamped_segments)
    result["timestamped_segments"]     = timestamped_segments
    result["formatted_with_timestamps"] = formatted_text
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_transcript.py <youtube_url_or_id> [lang_codes]")
        sys.exit(1)

    vid = extract_video_id(sys.argv[1])
    if not vid:
        print(f"Error: Cannot extract video ID from: {sys.argv[1]}")
        sys.exit(1)

    langs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["en"]
    res   = get_transcript(vid, langs)
    print(json.dumps(res, indent=2, ensure_ascii=False))
