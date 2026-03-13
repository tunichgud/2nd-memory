import requests
import json
import uuid

# 2nd Memory dev server should be running
req = {
    "user_id": "00000000-0000-0000-0000-000000000001",
    "masked_query": "Wo war ich im August mit Anna?",
    "person_tokens": ["[PER_1]"],
    "location_tokens": [],
    "location_names": [],
    "collections": ["photos", "messages"],
    "n_results": 6,
    "min_score": 0.2
}

print("Starting Stream...")
with requests.post("http://localhost:8000/api/v1/query_stream", json=req, stream=True) as r:
    for line in r.iter_lines():
        if line:
            chunk = json.loads(line.decode('utf-8'))
            print(f"> [{chunk['type']}]", chunk['content'][:200])
