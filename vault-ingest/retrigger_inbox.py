import os, requests
env = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

account_id = env.get("CLOUDFLARE_ACCOUNT_ID")
api_token = env.get("CLOUDFLARE_API_TOKEN")
worker_url = env.get("VAULT_INGEST_WORKER_URL", "https://vault-ingest.risheeg.workers.dev")
secret = env.get("VAULT_INGEST_HTTP_SECRET")

r2_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/r2/buckets/vault-ingest/objects"
headers = {"Authorization": f"Bearer {api_token}"}
resp = requests.get(r2_url, headers=headers)
count = 0

trigger_headers = {
    "x-vault-ingest-secret": secret,
    "Content-Type": "application/json"
}

for obj in resp.json().get("result", []):
    key = obj.get("key")
    if "/inbox/" in key:
        print(f"Triggering {key}...")
        trigger_url = f"{worker_url}/__vault_ingest/trigger"
        r = requests.post(trigger_url, json={"key": key}, headers=trigger_headers)
        print(f"Response for {key}: {r.status_code} - {r.text}")
        count += 1
print(f"Triggered {count} items")
