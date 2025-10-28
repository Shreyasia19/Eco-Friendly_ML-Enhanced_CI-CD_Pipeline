import werkzeug
werkzeug.__version__ = "3.0.0"

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app import app

def test_root_route():
    client = app.test_client()
    res = client.get("/")
    assert res.status_code == 200
    assert res.get_json() == {"message": "Hello from Eco-CI!"}
