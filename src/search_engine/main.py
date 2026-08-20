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
    model="gemini-3.6-flash",
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


print(web_search.invoke("Latest AI news"))