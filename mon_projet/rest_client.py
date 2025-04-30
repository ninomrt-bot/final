# rest_client.py ───────────────────────────────────────────────
import requests, json, pathlib

API      = "http://10.10.0.23:5000/api"     # ← IP du Pi + port exposé
CACHE    = pathlib.Path("/tmp/of_cache.json")
TIMEOUT  = 3

# --- helpers -------------------------------------------------- #
def _get(url):
    r = requests.get(f"{API}{url}", timeout=TIMEOUT); r.raise_for_status()
    return r.json()

def _post(url, payload=None):
    r = requests.post(f"{API}{url}", json=payload, timeout=TIMEOUT)
    return r

# --- liste OF (avec cache) ----------------------------------- #
def get_of_list_cached():
    try:
        data = _get("/orders")["orders"]
        CACHE.write_text(json.dumps(data)); return data
    except Exception as e:
        print("[REST] fallback cache:", e)
        return json.loads(CACHE.read_text()) if CACHE.exists() else []

# --- composants ---------------------------------------------- #
def get_of_components(of_num):
    return _get(f"/orders/components?of_name={of_num}")["components"]

# --- statut des îlots ---------------------------------------- #
def status():
    return _get("/status")["ilots"]

# --- démarrer un OF ------------------------------------------ #
def start(ilot, of_num, code, qty, date=None):
    payload = {
        "ilot":     ilot,
        "code":     code,
        "quantity": qty,
    }
    if date:
        payload["date"] = date
    r = requests.post(f"{API}/orders/{of_num}/start", json=payload, timeout=TIMEOUT)
    return r.status_code == 200


# --- simple ping --------------------------------------------- #
def can_connect_to_rest():
    try:
        _get("/test"); return True
    except Exception:  return False
