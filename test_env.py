import os
from dotenv import load_dotenv

load_dotenv()  # .env ஃபைலில் உள்ள மதிப்புகளை load செய்யும்

api_key = os.getenv("MY_TEST_KEY")

if api_key:
    print("API Key loaded successfully! Length:", len(api_key))
else:
    print("API Key not found. Check your .env file.")