import sys
import asyncio
import json
import re
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

load_dotenv()

st.set_page_config(page_title="AI YouTube Interview Coach", page_icon="🎯", layout="wide")


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


# Initialize Session States
if "mcp_client" not in st.session_state:
    st.session_state.mcp_client = None
if "mcp_tools" not in st.session_state:
    st.session_state.mcp_tools = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_question" not in st.session_state:
    st.session_state.last_question = ""
if "last_transcript" not in st.session_state:
    st.session_state.last_transcript = ""


# Async Helper for MCP Connection
async def init_mcp_client():
    client = MultiServerMCPClient({
        "interview_mcp_server": {
            "command": sys.executable,
            "args": ["mcp_server.py"],
            "transport": "stdio",
        }
    })
    tools = await client.get_tools()
    return client, {tool.name: tool for tool in tools}


# Load MCP Tools into Streamlit Cache
if not st.session_state.mcp_tools:
    with st.spinner("Connecting to MCP Server backend..."):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            client, tools_dict = loop.run_until_complete(init_mcp_client())
            st.session_state.mcp_client = client
            st.session_state.mcp_tools = tools_dict
        except Exception as e:
            st.error(f"Failed to connect to MCP Server: {e}")


# Helper to run async MCP tool calls
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# --- Sidebar ---
st.sidebar.title("🎯 Interview Coach Setup")
st.sidebar.info("Managed Desktop Folder: `~/Desktop/Interview_Prep/`")

# Sidebar File Viewers
def read_desktop_file(filename: str) -> str:
    home = Path.home()
    desktop = home / "OneDrive" / "Desktop" if (home / "OneDrive" / "Desktop").exists() else home / "Desktop"
    target_path = desktop / "Interview_Prep" / filename
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    return f"File `{filename}` not created yet."

with st.sidebar.expander("📄 View `interview_topics.md`"):
    st.code(read_desktop_file("interview_topics.md"), language="markdown")

with st.sidebar.expander("📝 View `interview_qa_log.md`"):
    st.code(read_desktop_file("interview_qa_log.md"), language="markdown")

with st.sidebar.expander("📌 View `video_summaries.md`"):
    st.code(read_desktop_file("video_summaries.md"), language="markdown")


# --- Main UI ---
st.title("📹 AI YouTube Interview Coach (MCP Enabled)")
st.caption("Ask general questions, request video summaries, or practice topic questions!")

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Chat Input
if prompt := st.chat_input("Ask a question, paste a YouTube link, or type 'ask me a question from the folder'..."):
    # Append User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    user_low = prompt.lower()
    url_match = re.search(r"https?://[^\s]+", prompt)
    tools_dict = st.session_state.mcp_tools

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        try:
            # 1. Feature: Video Summary Request
            if "summary" in user_low or "summarize" in user_low:
                if url_match:
                    url = url_match.group(0)
                    with st.spinner("Ingesting YouTube video transcript..."):
                        transcript_res = run_async(tools_dict["ingest_youtube_video"].ainvoke({"youtube_url": url}))
                        st.session_state.last_transcript = str(transcript_res)

                if not st.session_state.last_transcript or st.session_state.last_transcript.startswith("Error"):
                    ai_out = "Error retrieving video transcript. Please provide a valid YouTube link."
                else:
                    sum_prompt = (
                        f"Analyze the transcript below and generate a short summary. "
                        f"Provide a descriptive title header (# Title) followed by EXACTLY 2 to 3 concise bullet points.\n\n"
                        f"Transcript:\n{st.session_state.last_transcript[:6000]}"
                    )
                    llm = get_groq_llm()
                    raw_summary = llm.invoke([HumanMessage(content=sum_prompt)]).content.strip()
                    title = raw_summary.split("\n")[0].replace("#", "").strip() if "#" in raw_summary else "Video Summary"

                    run_async(tools_dict["save_video_summary"].ainvoke({"title": title, "summary": raw_summary}))
                    ai_out = f"**Summarized and saved to `video_summaries.md`!**\n\n{raw_summary}"

            # 2. Feature: Question from Desktop Topics Folder
            elif "folder" in user_low or "topic" in user_low:
                with st.spinner("Reading topics from interview_topics.md..."):
                    topics = run_async(tools_dict["read_interview_topics"].ainvoke({}))
                    q_prompt = (
                        f"Formulate ONE concise technical interview question based on these topics:\n{topics}\n\n"
                        f"STRICT RULE: The question MUST be exactly 1 to 2 lines long."
                    )
                    try:
                        q_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
                        question = q_llm.invoke([HumanMessage(content=q_prompt)]).content.strip()
                    except Exception:
                        q_llm = get_groq_llm()
                        question = q_llm.invoke([HumanMessage(content=q_prompt)]).content.strip()

                    st.session_state.last_question = question
                    ai_out = question

            # 3. Feature: Question from Video
            elif ("question" in user_low or "ask" in user_low or "practice" in user_low) and not st.session_state.last_question:
                if url_match:
                    url = url_match.group(0)
                    with st.spinner("Ingesting YouTube video transcript..."):
                        transcript_res = run_async(tools_dict["ingest_youtube_video"].ainvoke({"youtube_url": url}))
                        st.session_state.last_transcript = str(transcript_res)

                if not st.session_state.last_transcript or st.session_state.last_transcript.startswith("Error"):
                    ai_out = "Error retrieving video transcript. Please provide a valid YouTube link."
                else:
                    q_prompt = (
                        f"Formulate ONE concise technical interview question based on the transcript.\n\n"
                        f"Transcript:\n{st.session_state.last_transcript[:6000]}\n\n"
                        f"STRICT RULE: Return ONLY the question text in 1 to 2 sentences."
                    )
                    try:
                        q_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
                        question = q_llm.invoke([HumanMessage(content=q_prompt)]).content.strip()
                    except Exception:
                        q_llm = get_groq_llm()
                        question = q_llm.invoke([HumanMessage(content=q_prompt)]).content.strip()

                    st.session_state.last_question = question
                    ai_out = question

            # 4. Feature: Answer Evaluation & Logging
            elif st.session_state.last_question and len(prompt.split()) > 2 and not any(w in user_low for w in ["hi", "hello", "hey"]):
                eval_prompt = f"""
                Evaluate the candidate's response.
                Question Asked: {st.session_state.last_question}
                Candidate Answer: {prompt}

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

                run_async(tools_dict["save_interview_qa"].ainvoke({
                    "question": st.session_state.last_question,
                    "user_answer": prompt,
                    "score": score,
                    "ai_answer": ai_answer
                }))

                ai_out = f"**Score:** {score}\n\n**AI Answer:** {ai_answer}\n\n*[Saved via MCP to `interview_qa_log.md`]*"
                st.session_state.last_question = ""

            # 5. Feature: Conversational Chatbot Fallback
            else:
                llm = get_groq_llm()
                history_messages = [
                    SystemMessage(content="You are an AI YouTube Interview Coach. Keep answers strictly within 2 to 3 lines.")
                ] + [
                    HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
                    for m in st.session_state.messages
                ]
                ai_out = llm.invoke(history_messages).content.strip()

            response_placeholder.markdown(ai_out)
            st.session_state.messages.append({"role": "assistant", "content": ai_out})

        except Exception as e:
            st.error(f"Error during execution: {e}")