import requests

# பல பயனர்களின் விவரங்களைக் கொண்ட nested JSON பட்டியலைப் பெறும் endpoint
url = "https://jsonplaceholder.typicode.com/users"

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    users = response.json()  # இது ஒரு list of dictionaries

    # முதல் பயனரின் nested தரவைப் பாதுகாப்பாக எடுத்தல்
    if isinstance(users, list) and len(users) > 0:
        first_user = users[0]
        name = first_user.get("name", "Unknown")

        # Nested dict: company -> name
        company_name = first_user.get("company", {}).get("name", "No Company")

        # Deeply nested dict: address -> geo -> lat
        lat = first_user.get("address", {}).get("geo", {}).get("lat", "N/A")

        print("First User:", name)
        print("Company:", company_name)
        print("Latitude:", lat)

        # List-க்குள் loop செய்து அனைத்து பயனர்களின் நகரங்களையும் எடுத்தல்
        cities = [
            user.get("address", {}).get("city")
            for user in users
            if user.get("address", {}).get("city")
        ]
        print("Total cities found:", len(cities))
        print("First 3 cities:", cities[:3])

except requests.exceptions.RequestException as e:
    print("Request failed:", e)