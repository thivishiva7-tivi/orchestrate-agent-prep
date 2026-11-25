import requests

url = "https://jsonplaceholder.typicode.com/todos/1"

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()  # 404 அல்லது 500 போன்ற HTTP எரர்கள் வந்தால் பிடிக்கும்

    data = response.json()  # JSON பதிலை Python dictionary-ஆக மாற்றும்

    print("Status Code:", response.status_code)
    print("Title:", data.get("title"))
    print("Completed:", data.get("completed"))

except requests.exceptions.RequestException as e:
    print("API call failed:", e)