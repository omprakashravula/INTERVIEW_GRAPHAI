import re
from pathlib import Path
from typing import Optional
from fastmcp import FastMCP
from youtube_transcript_api import YouTubeTranscriptApi

mcp = FastMCP("YouTubeInterviewMCPServer")


def get_prep_folder() -> Path:
    """Returns ~/Desktop/Interview_Prep/ (supports OneDrive)."""
    home = Path.home()
    desktop = home / "OneDrive" / "Desktop" if (home / "OneDrive" / "Desktop").exists() else home / "Desktop"
    prep_dir = desktop / "Interview_Prep"
    prep_dir.mkdir(parents=True, exist_ok=True)
    return prep_dir


def extract_video_id(url: str) -> Optional[str]:
    """Extracts 11-character YouTube video ID."""
    if not url or not isinstance(url, str):
        return None
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    pattern = r"(?:v=|\/|be\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else url.strip()


@mcp.tool()
def ingest_youtube_video(youtube_url: str) -> str:
    """Fetches full transcript text for a YouTube video."""
    video_id = extract_video_id(youtube_url)
    if not video_id:
        return "Error: Invalid YouTube URL."

    try:
        api = YouTubeTranscriptApi()
        transcript_obj = api.fetch(video_id)
        transcript_list = (
            transcript_obj.to_raw_data()
            if hasattr(transcript_obj, "to_raw_data")
            else transcript_obj
        )
        full_text = " ".join([
            entry["text"] if isinstance(entry, dict) else getattr(entry, "text", str(entry))
            for entry in transcript_list
        ])
        return full_text
    except Exception as e:
        return f"Error retrieving transcript: {str(e)}"


@mcp.tool()
def save_video_summary(title: str, summary: str) -> str:
    """Appends video summary to Desktop/Interview_Prep/video_summaries.md"""
    folder = get_prep_folder()
    file_path = folder / "video_summaries.md"

    formatted_entry = f"# {title}\n\n{summary}\n\n---\n\n"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(formatted_entry)

    return f"Summary saved to {file_path.name}"


@mcp.tool()
def save_interview_qa(question: str, user_answer: str, score: str, ai_answer: str) -> str:
    """Appends Q&A evaluation to Desktop/Interview_Prep/interview_qa_log.md"""
    folder = get_prep_folder()
    file_path = folder / "interview_qa_log.md"

    formatted_entry = (
        f"### Question\n{question}\n\n"
        f"### Your Answer\n{user_answer}\n\n"
        f"### Score\n{score}\n\n"
        f"### AI Answer\n{ai_answer}\n\n"
        f"---\n\n"
    )
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(formatted_entry)

    return f"Q&A logged to {file_path.name}"


@mcp.tool()
def read_interview_topics() -> str:
    """Reads stored topics from Desktop/Interview_Prep/interview_topics.md"""
    folder = get_prep_folder()
    file_path = folder / "interview_topics.md"

    if not file_path.exists():
        default_topics = (
            "# Practice Topics\n\n"
            "- Transformer Attention Mechanisms & KV Caching\n"
            "- Distributed Rate Limiters & Caching Strategies\n"
            "- Vector Database Indexing (HNSW vs IVF)\n"
            "- Gradient Descent Variations (Batch vs Stochastic)"
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(default_topics)
        return default_topics

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()


if __name__ == "__main__":
    mcp.run()