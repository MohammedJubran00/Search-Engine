import os


from dotenv import load_dotenv

from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_tavily import TavilySearch
from langgraph.graph import  StateGraph, END


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
tavily = TavilySearch(max_results=5)


llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    temperature=0
)

@tool(description="Search the web using Tavily")
def web_search(query:str):
    result=tavily.invoke(query)
    results=[]

    for item in result['results']:
          results.append(
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Content: {item['content']}"
        )
    return "\n\n".join(results)


agent = create_react_agent(
    model=llm,
    tools=[web_search],
    prompt="""
You are an AI research assistant.

Always use web_search when the question requires factual or recent information.

Provide clear answers and include sources whenever possible.

Do not make up information.
""")

chat_history = []
def agent_node(state): #Adapter 
    chat_history.append(
        ("human", state["query"])
    )
    response = agent.invoke(
        {
            "messages": chat_history
        }
    )

    state["answer"] = response["messages"][-1].content
    chat_history.append(
    ("assistant", state["answer"])
)

    return state
#         { للتذكير لفائدة return state
#     "query": "Who founded OpenAI?",
#     "answer": "..."
# }________________________________________________________



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
            result = app.invoke(
                {
                    "query": query
                }
            )

            print("\nAnswer:")
            print(result["answer"])

        except Exception as e:
            print(f"\nSomething went wrong: {e}")