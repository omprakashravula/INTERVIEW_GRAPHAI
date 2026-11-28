 Architected an Agentic RAG Workstream: Built an autonomous interview prep pipeline using LangGraph state management and an In-Memory Checkpointer to deliver concise, source-grounded technical Q&As and candidate answer evaluations. 
 • Integrated Model Context Protocol (MCP): Designed an asynchronous local MCP server communicating over stdio transport using FastMCP to safely ingest YouTube transcripts, index Markdown practice topics, and maintain persistent Q&A evaluation logs. 
 •  Multi-LLM Orchestration: Implemented a resilient fallback engine across Groq (Llama-3.3-70B, GPT-OSS) and OpenAI (GPT-4o-mini) models to ensure low latency and continuous availability during tool execution. 
 •  Full-Stack Interface & File Persistence: Created an interactive Streamlit UI with dynamic sidebars for realtime file viewing (interview_topics.md, interview_qa_log.md) and direct local desktop file I/O.
 Tech Stack: Python, LangGraph, Model Context Protocol (MCP), FastMCP, Streamlit, Groq API, OpenAI API, YouTube Transcript API, Pydantic. 
 START → router_node
          ├─ topic_mock ───────► prepare_topic_node ──────────────┐
          ├─ youtube_mock ─┐                                      │
          ├─ youtube_summary┤► fetch_youtube_node ─┐              │
          ├─ file_mock ────► fetch_file_node ──────┤              │
          └─ clarify ──────► clarify_node → END    │              │
                                        error? ──► END            │
                                                   ▼              │
                                            split_text_node       │
                                         (plain code, no LLM)     │
                              ┌─ summary ─────────┴─ mock ────────┤
                              ▼                                   ▼
                       summarize_node ──► log_summary_node   generate_question_node ◄────┐
                                                │ → END              ▼                  │
                                                            await_answer_node  ⏸ PAUSE    │
                                                       ┌──── end ──┼──── skip ────────────┤
                                                       ▼           ▼ answer               │
                                              final_report_node  evaluate_node            │
                                                  │ → END            ▼                    │
                                                              log_turn_node ──────────────┘
