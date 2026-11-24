import sys
import asyncio
import json
import re
from dotenv import load_dotenv

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

load_dotenv()

LAST_QUESTION_ASKED = ""
LAST_TRANSCRIPT = ""


def get_groq_llm():
    groq_models = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ]
    for model_name in groq_models:
        try:
            return ChatGroq(model=model_name, temperature=0.3)
        except Exception:
            continue
    return ChatGroq(model="openai/gpt-oss-120b", temperature=0.3)


async def run_mcp_agent():
    global LAST_QUESTION_ASKED, LAST_TRANSCRIPT

    mcp_client = MultiServerMCPClient({
        "interview_mcp_server": {
            "command": sys.executable,
            "args": ["mcp_server.py"],
            "transport": "stdio",
        }
    })

    mcp_tools = await mcp_client.get_tools()
    tools_dict = {tool.name: tool for tool in mcp_tools}

    print("=" * 60)
    print("MCP YouTube Interview Coach Active!")
    print("Desktop Storage Path: ~/Desktop/Interview_Prep/")
    print("Files Managed:")
    print("  1. video_summaries.md   (Video Summaries)")
    print("  2. interview_qa_log.md  (Practice Questions & Scores)")
    print("  3. interview_topics.md  (Folder Topic Questions)")
    print("=" * 60 + "\n")

    conversation_history = [
        SystemMessage(content=(
            "You are an AI YouTube Interview Coach. "
            "IMPORTANT: Always keep your responses extremely concise—no more than 2 to 3 lines long. "
            "For general conversation or greetings, respond directly in 1-2 sentences without tools. "
            "Only execute tool calls when explicitly requested."
        ))
    ]

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                print("Session ended.")
                break

            user_low = user_input.lower()
            url_match = re.search(r"https?://[^\s]+", user_input)

            # Feature 1: Video Summary Request
            if "summary" in user_low or "summarize" in user_low or "explain" in user_low:
                if url_match:
                    url = url_match.group(0)
                    print("\n[MCP Tool] Ingesting YouTube video transcript...")
                    transcript_res = await tools_dict["ingest_youtube_video"].ainvoke({"youtube_url": url})
                    LAST_TRANSCRIPT = str(transcript_res)

                if not LAST_TRANSCRIPT or LAST_TRANSCRIPT.startswith("Error"):
                    print("\nAI: Error retrieving video transcript. Please provide a valid YouTube link.\n")
                    continue

                sum_prompt = (
                    f"Analyze the transcript below and generate a short summary. "
                    f"Provide a descriptive title header (# Title) followed by EXACTLY 2 to 3 concise bullet points summarizing key technical takeaways.\n\n"
                    f"Transcript:\n{LAST_TRANSCRIPT[:6000]}"
                )
                llm = get_groq_llm()
                raw_summary = llm.invoke([HumanMessage(content=sum_prompt)]).content.strip()

                title = raw_summary.split("\n")[0].replace("#", "").strip() if "#" in raw_summary else "Video Summary"

                await tools_dict["save_video_summary"].ainvoke({"title": title, "summary": raw_summary})

                output_msg = f"Summarized and saved to `video_summaries.md`!\n\n{raw_summary}"
                print(f"\nAI: {output_msg}\n")
                conversation_history.append(HumanMessage(content=user_input))
                conversation_history.append(AIMessage(content=output_msg))
                continue

            # Feature 3: Question from Desktop Topics Folder
            if "folder" in user_low or "topic" in user_low:
                print("\n[MCP Tool] Reading topics from interview_topics.md...")
                topics = await tools_dict["read_interview_topics"].ainvoke({})

                q_prompt = (
                    f"Formulate ONE concise technical interview question based on these topics:\n{topics}\n\n"
                    f"STRICT RULE: The question MUST be exactly 1 to 2 lines long. Do NOT write long preambles."
                )
                try:
                    q_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
                    question = q_llm.invoke([HumanMessage(content=q_prompt)]).content.strip()
                except Exception:
                    q_llm = get_groq_llm()
                    question = q_llm.invoke([HumanMessage(content=q_prompt)]).content.strip()

                LAST_QUESTION_ASKED = question
                print(f"\nAI: {question}\n")
                conversation_history.append(HumanMessage(content=user_input))
                conversation_history.append(AIMessage(content=question))
                continue

            # Feature 2A: Question from Video
            if ("question" in user_low or "ask" in user_low or "practice" in user_low) and not LAST_QUESTION_ASKED:
                if url_match:
                    url = url_match.group(0)
                    print("\n[MCP Tool] Ingesting YouTube video transcript...")
                    transcript_res = await tools_dict["ingest_youtube_video"].ainvoke({"youtube_url": url})
                    LAST_TRANSCRIPT = str(transcript_res)

                if not LAST_TRANSCRIPT or LAST_TRANSCRIPT.startswith("Error"):
                    print("\nAI: Error retrieving video transcript. Please provide a valid YouTube link.\n")
                    continue

                q_prompt = (
                    f"You are a principal engineer. Formulate ONE concise technical interview question based on the transcript.\n\n"
                    f"Transcript:\n{LAST_TRANSCRIPT[:6000]}\n\n"
                    f"STRICT RULE: Return ONLY the question text in 1 to 2 sentences (2-3 lines max)."
                )
                try:
                    q_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
                    question = q_llm.invoke([HumanMessage(content=q_prompt)]).content.strip()
                except Exception:
                    q_llm = get_groq_llm()
                    question = q_llm.invoke([HumanMessage(content=q_prompt)]).content.strip()

                LAST_QUESTION_ASKED = question
                print(f"\nAI: {question}\n")
                conversation_history.append(HumanMessage(content=user_input))
                conversation_history.append(AIMessage(content=question))
                continue

            # Feature 2B: Evaluate Answer & Log
            if LAST_QUESTION_ASKED and len(user_input.split()) > 2 and not any(w in user_low for w in ["hi", "hello", "hey"]):
                eval_prompt = f"""
                Evaluate the candidate's response.
                Question Asked: {LAST_QUESTION_ASKED}
                Candidate Answer: {user_input}

                STRICT RULE: The ideal_answer MUST be exactly 1 to 2 sentences (15-25 words max).

                Return strictly valid JSON:
                {{
                  "score": "<score out of 10>",
                  "ideal_answer": "<concise 1 to 2 sentence answer>"
                }}
                """
                eval_llm = get_groq_llm()
                raw_eval = eval_llm.invoke([HumanMessage(content=eval_prompt)]).content.strip()

                clean_json = re.search(r"\{.*\}", raw_eval, re.DOTALL)
                if clean_json:
                    data = json.loads(clean_json.group(0))
                    score = data.get("score", "7/10")
                    ai_answer = data.get("ideal_answer", "N/A")
                else:
                    score = "7/10"
                    ai_answer = raw_eval[:150]

                await tools_dict["save_interview_qa"].ainvoke({
                    "question": LAST_QUESTION_ASKED,
                    "user_answer": user_input,
                    "score": score,
                    "ai_answer": ai_answer
                })

                output_msg = f"**Score:** {score}\n**AI Answer:** {ai_answer}\n\n*[Saved via MCP to interview_qa_log.md]*"
                print(f"\nAI: {output_msg}\n")

                LAST_QUESTION_ASKED = ""
                conversation_history.append(HumanMessage(content=user_input))
                conversation_history.append(AIMessage(content=output_msg))
                continue

            # Standard Chatbot Fallback (Short 2-3 Line Answer Prompt)
            llm = get_groq_llm()
            conversation_history.append(HumanMessage(
                content=f"{user_input}\n\n(Note: Keep your answer strictly within 2 to 3 lines for an interview scenario.)"
            ))
            chat_response = llm.invoke(conversation_history).content.strip()

            print(f"\nAI: {chat_response}\n")
            conversation_history.append(AIMessage(content=chat_response))

        except Exception as e:
            print(f"\n[Error]: {str(e)}\n")


if __name__ == "__main__":
    asyncio.run(run_mcp_agent())