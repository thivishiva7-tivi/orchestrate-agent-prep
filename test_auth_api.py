import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("DEMO_API_TOKEN")

if not api_key:
    raise ValueError("DEMO_API_TOKEN is missing in .env")

url = "https://httpbin.org/headers"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    data = response.json()
    sent_headers = data.get("headers", {})

    print("Status Code:", response.status_code)
    print("Authorization Header received by server:", sent_headers.get("Authorization"))

except requests.exceptions.RequestException as e:
    print("Request failed:", e)