#!/usr/bin/env python3
"""
YouTube Transcript Extractor
Extracts transcripts from YouTube videos using youtube-transcript-api

Compatibility: v0.x (dict segments) AND v1.x (FetchedTranscriptSnippet objects)
"""

import sys
import json
import re
from typing import Dict, List, Optional


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract video ID from various YouTube URL formats."""
    if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id):
        return url_or_id

    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/shorts\/)([A-Za-z0-9_-]{11})',
        r'youtube\.com\/watch\?.*v=([A-Za-z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    return None


def _segment_to_dict(segment) -> Dict:
    """
    Normalise a transcript segment to a plain dict regardless of API version.

    youtube-transcript-api v0.x  → segment is already a dict
                                   {"text": ..., "start": ..., "duration": ...}
    youtube-transcript-api v1.x  → segment is a FetchedTranscriptSnippet object
                                   with .text, .start, .duration attributes
    """
    if isinstance(segment, dict):
        return {
            "text":     segment.get("text", ""),
            "start":    segment.get("start", 0.0),
            "duration": segment.get("duration", 0.0),
        }
    # Object-style (v1.x)
    return {
        "text":     getattr(segment, "text",     ""),
        "start":    getattr(segment, "start",    0.0),
        "duration": getattr(segment, "duration", 0.0),
    }


def get_transcript(video_id: str, languages: List[str] = None,
                   preserve_formatting: bool = True) -> Dict:
    """Get transcript for a YouTube video."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {
            "error": "youtube-transcript-api not installed",
            "solution": "pip install youtube-transcript-api"
        }

    if languages is None:
        languages = ['en']

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        transcript    = None
        found_language = None

        for lang in languages:
            try:
                transcript = transcript_list.find_transcript([lang])
                found_language = lang
                break
            except Exception:
                continue

        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
                found_language = 'en (auto-generated)'
            except Exception:
                available = list(transcript_list)
                if available:
                    transcript = available[0]
                    found_language = transcript.language_code
                else:
                    return {"error": "No transcripts available", "video_id": video_id}

        raw_segments = transcript.fetch()

        # Normalise every segment to a plain dict (handles both v0.x and v1.x)
        segments = [_segment_to_dict(s) for s in raw_segments]

        # Build full text
        if preserve_formatting:
            full_text = ""
            for seg in segments:
                text = seg["text"].strip()
                if full_text and not full_text.endswith('\n'):
                    if text and text[0].isupper() and full_text[-1] in '.!?':
                        full_text += '\n\n'
                    else:
                        full_text += ' '
                full_text += text
        else:
            full_text = " ".join(seg["text"].strip() for seg in segments)

        # Build available-languages list
        available_languages = []
        try:
            for t in transcript_list:
                available_languages.append({
                    "language":       t.language,
                    "language_code":  t.language_code,
                    "is_generated":   t.is_generated,
                    "is_translatable": t.is_translatable,
                })
        except Exception:
            pass  # non-critical

        return {
            "success":            True,
            "video_id":           video_id,
            "language":           found_language,
            "transcript":         full_text,
            "segments":           segments,
            "segment_count":      len(segments),
            "character_count":    len(full_text),
            "word_count":         len(full_text.split()),
            "available_languages": available_languages,
        }

    except Exception as e:
        error_msg = str(e).lower()
        if "disabled" in error_msg:
            return {"error": "Transcripts are disabled for this video", "video_id": video_id}
        if "unavailable" in error_msg or "not found" in error_msg:
            return {"error": "Video unavailable or no transcript found", "video_id": video_id}
        return {"error": str(e), "video_id": video_id, "error_type": type(e).__name__}


def get_transcript_with_timestamps(video_id: str, languages: List[str] = None) -> Dict:
    """Get transcript with [MM:SS] timestamp markers on every segment."""
    result = get_transcript(video_id, languages, preserve_formatting=False)

    if not result.get('success'):
        return result

    timestamped_segments = []
    for seg in result['segments']:
        start_time = seg['start']
        hours   = int(start_time // 3600)
        minutes = int((start_time % 3600) // 60)
        seconds = int(start_time % 60)

        timestamp = (
            f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            if hours > 0 else
            f"{minutes:02d}:{seconds:02d}"
        )

        timestamped_segments.append({
            "timestamp":     timestamp,
            "start_seconds": start_time,
            "duration":      seg['duration'],
            "text":          seg['text'],
        })

    formatted_text = "\n".join(
        f"[{s['timestamp']}] {s['text']}" for s in timestamped_segments
    )

    result['timestamped_segments']    = timestamped_segments
    result['formatted_with_timestamps'] = formatted_text

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_transcript.py <youtube_url_or_id>")
        sys.exit(1)

    url_or_id = sys.argv[1]
    video_id  = extract_video_id(url_or_id)

    if not video_id:
        print(f"Error: Could not extract video ID from: {url_or_id}")
        sys.exit(1)

    languages = sys.argv[2].split(',') if len(sys.argv) > 2 else ['en']
    result    = get_transcript(video_id, languages)
    print(json.dumps(result, indent=2))
