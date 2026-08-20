from dotenv import load_dotenv
from langchain_tavily import TavilySearch

load_dotenv()

tool = TavilySearch(max_results=3)

result = tool.invoke("Latest AI news")

for i, item in enumerate(result["results"], start=1):
    print(f"\nResult {i}")
    print("Title:", item["title"])
    print("URL:", item["url"])
    print()