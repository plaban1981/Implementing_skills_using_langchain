---
name: youtube-transcript
description: Extract transcripts, captions, and metadata from YouTube videos using the youtube-transcript-api Python library. Use when users share YouTube links requesting summaries, guides, explanations, transcripts, or content about videos. Automatically extracts transcripts, analyzes content, and provides comprehensive video summaries. Works directly without requiring MCP server installation.
---

# YouTube Transcript Extraction

## Overview

Extract transcripts and analyze YouTube videos using the `youtube-transcript-api` Python library.

## Automatic Processing

**CRITICAL**: When a user shares a YouTube URL or video ID, immediately begin transcript extraction without asking for confirmation. The workflow is fully automated.

## Core Capabilities

### 1. Automatic Transcript Extraction
- Extract transcripts from any YouTube video with captions
- Support for multiple languages (100+ languages)
- Automatic fallback to available languages
- Formatted text with natural paragraph breaks
- Raw segments with timing information

### 2. Timestamped Transcripts
- Preserve timing information for each segment
- HH:MM:SS formatted timestamps

### 3. Content Analysis
- Automatic summarization of video content
- Key point extraction
- Topic identification

## Workflow

### Step 1: Automatic Video ID Extraction

When user provides any of these formats:
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`
- Just the `VIDEO_ID` (11 characters)

### Step 2: Ensure Dependencies

```bash
pip install youtube-transcript-api
```

### Step 3: Extract Transcript

Use the provided script to extract the transcript:

```python
from skills.youtube-transcript.scripts.extract_transcript import get_transcript, extract_video_id
video_id = extract_video_id("VIDEO_URL")
result = get_transcript(video_id)
```

### Step 4: Process and Present

Based on the user's request:
- **Transcript only**: Present the formatted transcript
- **Summary requested**: Analyze and summarize the content
- **Timestamped content**: Include timing references

## Error Handling

- **"Transcripts are disabled"**: Inform user, suggest alternatives
- **"Video unavailable"**: Verify video URL
- **"No transcripts available"**: Try again later
