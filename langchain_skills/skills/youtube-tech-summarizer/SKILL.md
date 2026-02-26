---
name: youtube-tech-summarizer
description: Automatically generate comprehensive step-by-step guides and blog posts from technical YouTube videos. Use when users share YouTube links requesting summaries, guides, explanations, or content about programming tutorials, AI/ML, software development, frameworks, or technology demonstrations. Automatically extracts transcripts, analyzes content, shows original code followed by enhanced versions, and creates adaptive 2000-6000 word guides.
---

# YouTube Technical Video Summarizer

Automatically transform technical YouTube videos into comprehensive, publication-ready guides.

## Core Behavior

**AUTOMATIC PROCESSING**: When a user shares a YouTube URL, immediately begin transcript extraction and content generation.

**OUTPUT TARGET**: Generate comprehensive step-by-step guides of 2000-6000 words.

**CODE TREATMENT**: For every code snippet, show BOTH:
1. Original code exactly as shown in the video
2. Enhanced version with error handling, comments, and best practices

## Workflow

### 1. Extract Transcript
Use the youtube-transcript skill to extract the full transcript.

### 2. Intelligent Content Analysis
Analyze the transcript to identify:
- Video type: Tutorial, concept explanation, tool demo, architecture discussion
- Complexity level: Beginner, intermediate, or advanced
- Main topic and learning objectives
- Key concepts and technical principles
- All technologies, frameworks, libraries mentioned
- Code examples with full context
- Step-by-step processes

### 3. Generate Comprehensive Guide

Structure:
- Title, metadata, table of contents
- What you'll learn + prerequisites
- Core concept explanation
- Project overview / architecture
- Step-by-step implementation (original + enhanced code for each step)
- Complete code walkthrough
- Configuration and setup
- Testing
- Real-world use cases
- Best practices and pitfalls
- Key takeaways, resources, next steps, FAQ, conclusion

## Length Targets
- Short videos (< 10 min): 2000-3000 words
- Medium videos (10-30 min): 3000-4500 words
- Long videos (> 30 min): 4500-6000 words
