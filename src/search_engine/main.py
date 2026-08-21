import logging
import os


from dotenv import load_dotenv

from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_tavily import TavilySearch
from langgraph.graph import  StateGraph, END
from langchain_core.messages import AIMessageChunk


load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
tavily = TavilySearch(max_results=5)


llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    temperature=0
)

@tool(description="Search the web using Tavily")
def web_search(query:str):
    # Tavily / network failures must not crash LangGraph. Return a string
    # the agent can read so it can still produce a response.
    try:
        result=tavily.invoke(query)
        results=[]

        for item in result['results']:
              results.append(
                f"Title: {item['title']}\n"
                f"URL: {item['url']}\n"
                f"Content: {item['content']}"
            )
        if not results:
            return "No search results were found for this query."
        return "\n\n".join(results)
    except Exception as e:
        logger.exception("Tavily web_search failed for query=%r", query)
        return (
            "Web search is currently unavailable. "
            f"Tell the user you could not search the web. Details: {e}"
        )


agent = create_react_agent(
    model=llm,
    tools=[web_search],
    prompt="""
You are an AI research assistant.

Always use web_search when the question requires factual or recent information.

Provide clear answers and include sources whenever possible.

Do not make up information.
""")

# chat_history = []
sessions = {}

# def agent_node(state): #Adapter  #for chat history and no session id
#     chat_history.append(
#         ("human", state["query"])
#     )
#     response = agent.invoke(
#         {
#             "messages": chat_history
#         }
#     )

#     state["answer"] = response["messages"][-1].content
#     chat_history.append(
#     ("assistant", state["answer"])
# )

#     return state
# #         { للتذكير لفائدة return state
# #     "query": "Who founded OpenAI?",
# #     "answer": "..."
# # }________________________________________________________

def agent_node(state): #for chat history and session id
    # Copy history first so a failed Gemini/LangGraph call cannot leave a
    # half-written turn in sessions[session_id].
    session_id = state.get("session_id")
    query = state.get("query")
    chat_history = list(sessions.get(session_id, [])) #get the chat history for the session id للتذكير 
    # [] اذا ما بقت السيشن موجودة 

    try:
        chat_history.append(
            ("human", query)
        )
        # Protect the model call: Gemini errors, tool crashes, or an empty
        # agent payload should be logged and re-raised for the API layer.
        response = agent.invoke(
            {
                "messages": chat_history
            }
        )
        if not response or not response.get("messages"):
            raise RuntimeError("The agent returned no messages.")

        answer=response["messages"][-1].content #[-1] اخر مسج انبعت من اليوزر 
        chat_history.append(("assistant", answer))
        sessions[session_id] = chat_history
        state["answer"] = answer
        return state
    except Exception:
        logger.exception(
            "LangGraph agent_node failed for session_id=%r",
            session_id,
        )
        raise
    #         { للتذكير لفائدة return state
    #     "query": "Who founded OpenAI?",
    #     "answer": "..."
    # }________________________________________________________


def _delta_text(content) -> str:
    # Streaming chunks should concatenate with "" so tokens do not gain
    # extra blank lines between pieces of the same sentence.
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_delta_text(item) for item in content)
    if isinstance(content, dict):
        if content.get("type") in {"thinking", "reasoning"}:
            return ""
        if isinstance(content.get("text"), str):
            return content["text"]
        return ""
    return ""


def stream_agent(session_id: str, query: str):
    # Same session memory as agent_node, but yields Gemini tokens as they
    # arrive instead of waiting for the full invoke() result.
    chat_history = list(sessions.get(session_id, []))
    chat_history.append(("human", query))
    full_answer = []

    try:
        for item in agent.stream(
            {"messages": chat_history},
            stream_mode="messages",
        ):
            message = item[0] if isinstance(item, tuple) else item
            if not isinstance(message, AIMessageChunk):
                continue

            delta = _delta_text(getattr(message, "content", ""))
            if not delta:
                continue

            full_answer.append(delta)
            yield delta

        answer = "".join(full_answer)
        if not answer.strip():
            raise RuntimeError("The agent returned an empty answer.")

        chat_history.append(("assistant", answer))
        sessions[session_id] = chat_history
    except Exception:
        logger.exception(
            "LangGraph stream_agent failed for session_id=%r",
            session_id,
        )
        raise


graph=StateGraph(dict)

graph.add_node("agent", agent_node)
graph.set_entry_point("agent")
graph.add_edge("agent", END)
app=graph.compile()

 # the queston or the prompt ( the request)
if __name__ == "__main__": 
    
    while True:
        query = input("Query> ").strip()

        if query.lower() in ["exit", "quit"]:
            break

        if not query:
            print("Please enter a question.")
            continue

        try:
            # Same protection as the FastAPI path so a CLI crash does not
            # kill the process on a Gemini/Tavily error.
            result = app.invoke(
                {
                    "session_id": "user1",
                    "query": query
                }
            )

            print("\nAnswer:")
            print(result["answer"])

        except Exception as e:
            logger.exception("CLI LangGraph invoke failed")
            print(f"\nSomething went wrong: {e}")