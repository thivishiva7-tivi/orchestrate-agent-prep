import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("DEMO_API_TOKEN")

url = "https://httpbin.org/post"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

# API-க்கு அனுப்ப வேண்டிய JSON தரவு (Payload)
payload = {
    "agent_name": "StudyPlannerAgent",
    "task": "Summarize Python API concepts",
    "priority": 1,
    "tags": ["python", "api", "hackathon"]
}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()

    data = response.json()
    received_json = data.get("json", {})

    print("Status Code:", response.status_code)
    print("Server received Agent:", received_json.get("agent_name"))
    print("Server received Task:", received_json.get("task"))
    print("Tags:", received_json.get("tags"))

except requests.exceptions.RequestException as e:
    print("POST request failed:", e)