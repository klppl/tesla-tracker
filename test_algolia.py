import requests
import json

URL = "https://izs3uhkhl4-dsn.algolia.net/1/indexes/*/queries"
HEADERS = {
    "x-algolia-agent": "Algolia for JavaScript (4.25.2)",
    "x-algolia-application-id": "IZS3UHKHL4",
    "x-algolia-api-key": "05ebd9cb812d1c6ebe07ab6de7dc28bb"
}

payload = {
    "requests": [{
        "indexName": "new_created_at_desc",
        "params": "filters=manufacturer%3A%22Tesla%22&offset=0&length=1"
    }]
}

response = requests.post(URL, params=HEADERS, json=payload)
data = response.json()['results'][0]['hits'][0]
print(json.dumps(data, indent=2))
