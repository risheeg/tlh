import sys
sys.path.insert(0, '/home/ubuntu/tlh/backend')
from fastapi.testclient import TestClient
from main import app
import uuid

client = TestClient(app)

user_id = '45a10eec-1398-483e-b7cd-be90fbd2c77c'

payload = {
    "user_id": user_id,
    "name": "ETrade Savings Account",
    "type": "savings",
    "institution": "ETrade"
}

res = client.post("/accounts", json=payload)
print(res.status_code, res.json())
