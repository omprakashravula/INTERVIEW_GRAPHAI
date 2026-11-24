import sys
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

load_dotenv()

TEST_VIDEO_URL = "https://youtu.be/A_5XNd7_3to?si=oGD1lb4hPeYilrXs"


def extract_video_id(url: str) -> str:
    """Extracts the 11-character YouTube video ID from various URL formats."""
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url.strip()


def summarize_scraped_transcript(video_url_or_id: str):
    video_id = extract_video_id(video_url_or_id)
    print(f"--> Target Video ID: {video_id}")
    print("--> Fetching full transcript from YouTube...\n")

    # Step 1: Extract transcript from YouTube
    try:
        api = YouTubeTranscriptApi()
        transcript_obj = api.fetch(video_id)
        
        transcript_list = (
            transcript_obj.to_raw_data()
            if hasattr(transcript_obj, "to_raw_data")
            else transcript_obj
        )
        
        full_transcript_text = " ".join([
            entry["text"] if isinstance(entry, dict) else getattr(entry, "text", str(entry))
            for entry in transcript_list
        ])

        word_count = len(full_transcript_text.split())
        print(f"SUCCESS: Extracted {len(transcript_list)} caption segments ({word_count} total words).\n")

    except TranscriptsDisabled:
        print("ERROR: Captions are disabled for this video.")
        return
    except NoTranscriptFound:
        print("ERROR: No transcript found for this video.")
        return
    except Exception as e:
        print(f"FAILED TO FETCH TRANSCRIPT: {str(e)}")
        return

    # Step 2: Pass full transcript to Groq (openai/gpt-oss-120b) for summarization
    print("--> Sending transcript to Groq (openai/gpt-oss-120b) for summarization...\n")

    try:
        groq_llm = ChatGroq(
            model="openai/gpt-oss-120b",
            temperature=0.2
        )

        prompt = f"""
        You are an expert technical AI assistant. Below is a full transcript scraped from a YouTube video.
        
        Analyze the text and generate a structured summary:
        1. **Executive Summary** (2-3 sentence overview)
        2. **Key Concepts & Technical Takeaways** (3-5 bullet points)
        3. **Final Conclusion / Practical Application**

        Full Transcript:
        {full_transcript_text}
        """

        response = groq_llm.invoke([HumanMessage(content=prompt)])
        summary = response.content.strip()

        print("=" * 60)
        print(f"AI SUMMARY FOR VIDEO ({video_id}) [Groq: gpt-oss-120b]")
        print("=" * 60)
        print(summary)
        print("=" * 60)

    except Exception as e:
        print(f"FAILED TO GENERATE SUMMARY: {str(e)}")


if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else TEST_VIDEO_URL
    summarize_scraped_transcript(target_url)