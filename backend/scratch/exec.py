import sys
import os
sys.path.insert(0, '/home/ubuntu/tlh/backend')

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

user_id = '45a10eec-1398-483e-b7cd-be90fbd2c77c'

# 1. Sync snapshot to spreadsheet
print("Pushing snapshot...")
res = client.post(f"/portfolio/{user_id}/snapshot/sync")
print(res.status_code, res.json())
