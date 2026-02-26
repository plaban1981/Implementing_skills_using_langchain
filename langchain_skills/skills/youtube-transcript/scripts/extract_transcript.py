#!/usr/bin/env python3
"""
YouTube Transcript Extractor
Extracts transcripts from YouTube videos using youtube-transcript-api
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


def get_transcript(video_id: str, languages: List[str] = None, preserve_formatting: bool = True) -> Dict:
    """Get transcript for a YouTube video."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {
            "error": "youtube-transcript-api not installed",
            "solution": "Install with: pip install youtube-transcript-api"
        }
    
    if languages is None:
        languages = ['en']
    
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        transcript = None
        found_language = None
        
        for lang in languages:
            try:
                transcript = transcript_list.find_transcript([lang])
                found_language = lang
                break
            except:
                continue
        
        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
                found_language = 'en (auto-generated)'
            except:
                available = list(transcript_list)
                if available:
                    transcript = available[0]
                    found_language = transcript.language_code
                else:
                    return {"error": "No transcripts available", "video_id": video_id}
        
        transcript_data = transcript.fetch()
        
        if preserve_formatting:
            full_text = ""
            for item in transcript_data:
                text = item['text'].strip()
                if full_text and not full_text.endswith('\n'):
                    if text and text[0].isupper() and full_text[-1] in '.!?':
                        full_text += '\n\n'
                    else:
                        full_text += ' '
                full_text += text
        else:
            full_text = " ".join([item['text'].strip() for item in transcript_data])
        
        available_languages = []
        for t in transcript_list:
            available_languages.append({
                "language": t.language,
                "language_code": t.language_code,
                "is_generated": t.is_generated,
                "is_translatable": t.is_translatable
            })
        
        return {
            "success": True,
            "video_id": video_id,
            "language": found_language,
            "transcript": full_text,
            "segments": [{"text": s["text"], "start": s["start"], "duration": s["duration"]} for s in transcript_data],
            "segment_count": len(transcript_data),
            "character_count": len(full_text),
            "word_count": len(full_text.split()),
            "available_languages": available_languages
        }
        
    except Exception as e:
        error_msg = str(e)
        if "disabled" in error_msg.lower():
            return {"error": "Transcripts are disabled for this video", "video_id": video_id}
        elif "unavailable" in error_msg.lower() or "not found" in error_msg.lower():
            return {"error": "Video unavailable or no transcript found", "video_id": video_id}
        else:
            return {"error": str(e), "video_id": video_id, "error_type": type(e).__name__}


def get_transcript_with_timestamps(video_id: str, languages: List[str] = None) -> Dict:
    """Get transcript with timestamp information preserved."""
    result = get_transcript(video_id, languages, preserve_formatting=False)
    
    if not result.get('success'):
        return result
    
    timestamped_segments = []
    for segment in result['segments']:
        start_time = segment['start']
        hours = int(start_time // 3600)
        minutes = int((start_time % 3600) // 60)
        seconds = int(start_time % 60)
        
        if hours > 0:
            timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            timestamp = f"{minutes:02d}:{seconds:02d}"
        
        timestamped_segments.append({
            "timestamp": timestamp,
            "start_seconds": start_time,
            "duration": segment['duration'],
            "text": segment['text']
        })
    
    formatted_text = "\n".join([f"[{seg['timestamp']}] {seg['text']}" for seg in timestamped_segments])
    
    result['timestamped_segments'] = timestamped_segments
    result['formatted_with_timestamps'] = formatted_text
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_transcript.py <youtube_url_or_id>")
        sys.exit(1)
    
    url_or_id = sys.argv[1]
    video_id = extract_video_id(url_or_id)
    
    if not video_id:
        print(f"Error: Could not extract video ID from: {url_or_id}")
        sys.exit(1)
    
    languages = ['en']
    if len(sys.argv) > 2:
        languages = sys.argv[2].split(',')
    
    result = get_transcript(video_id, languages)
    print(json.dumps(result, indent=2))
