import time
import requests


def fetch_with_retry(url: str, max_retries: int = 3, timeout: float = 5.0):
    """
    தற்காலிக நெட்வொர்க்/சர்வர் பிழைகளுக்கு (Timeout, 429, 5xx)
    exponential backoff முறையில் மீண்டும் முயற்சிக்கும் function.
    """
    retry_statuses = {429, 500, 502, 503, 504}

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Attempt {attempt}/{max_retries} -> {url}")
            response = requests.get(url, timeout=timeout)

            # தற்காலிகப் பிழை status codes வந்தால் மீண்டும் முயற்சிக்கலாம்
            if response.status_code in retry_statuses:
                raise requests.exceptions.HTTPError(
                    f"Retryable status code: {response.status_code}",
                    response=response,
                )

            # 401, 403, 404 போன்ற மற்ற HTTP பிழைகளுக்கு உடனே நிறுத்திவிடும்
            response.raise_for_status()
            return response.json()

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            # 401 / 403 / 404 போன்றவற்றை retry செய்ய வேண்டாம்
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                if e.response.status_code not in retry_statuses:
                    print(f"Non-retryable HTTP error ({e.response.status_code}): {e}")
                    return None

            print(f"Attempt {attempt} failed: {e}")

            if attempt < max_retries:
                wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s...
                print(f"Waiting {wait_time}s before next retry...")
                time.sleep(wait_time)
            else:
                print("All retry attempts exhausted.")
                return None


if __name__ == "__main__":
    # சோதனை 1: வெற்றிகரமான endpoint
    success_data = fetch_with_retry("https://jsonplaceholder.typicode.com/todos/1")
    print("Success result title:", success_data.get("title") if success_data else None)

    print("-" * 40)

    # சோதனை 2: இல்லாத endpoint (404 - retry செய்யாமல் உடனே நிறுத்தும்)
    not_found_data = fetch_with_retry("https://jsonplaceholder.typicode.com/nonexistent-endpoint")
    print("Not found result:", not_found_data)