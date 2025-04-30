# opcua_client.py ────────────────────────────────────────────────
"""
Wrapper "friendly" autour de la librairie *freeopcua*.
─ Gestion de plusieurs îlots : LGN01 / LGN02 / LGN03
─ Lecture / écriture de tags (NodeId)
─ Fonctions utilitaires : start_order, send_order_details + get_states
"""

from __future__ import annotations
import os
from dotenv import load_dotenv
from opcua import Client, ua

# -----------------------------------------------------------------------------
# 1) Chargement des variables d’environnement (.env facultatif)
# -----------------------------------------------------------------------------
load_dotenv()

# Un endpoint par îlot ▸ surchargeable via `.env`, nettoyage des espaces
OPCUA_ENDPOINTS: dict[str, str] = {
    "LGN01": os.getenv("OPCUA_LGN01", "opc.tcp://172.30.30.110:4840").strip(),
    "LGN02": os.getenv("OPCUA_LGN02", "opc.tcp://172.30.30.120:4840").strip(),
    "LGN03": os.getenv("OPCUA_LGN03", "opc.tcp://172.30.30.130:4840").strip(),
}

# -----------------------------------------------------------------------------
# 2) NodeIds standards (à adapter selon ta config automate)
# -----------------------------------------------------------------------------
NODE_START_ORDER   = "ns=4;s=StartOrder"      # OK:  OF
NODE_ORDER_CODE    = "ns=4;s=OrderCode"       # code article
NODE_ORDER_QTY     = "ns=4;s=OrderQuantity"   # quantité
NODE_ORDER_DATE    = "ns=4;s=OrderDate"       # date ou timestamp
NODE_STATE_MACHINE = "ns=2;s=State"           # état machine (0=STOP,1=RUN,2=ALARM...)

# -----------------------------------------------------------------------------
# 3) Classe bas niveau : connexion + lecture / écriture
# -----------------------------------------------------------------------------
class OPCUAHandler:
    """
    Usage:
        with OPCUAHandler("LGN01") as plc:
            plc.write(NODE_START_ORDER, "WH/MO/00012")
            status = plc.read(NODE_STATE_MACHINE)
    """
    def __init__(self, key_or_url: str) -> None:
        # clé (ex: "LGN01") ou URL complète
        url = OPCUA_ENDPOINTS.get(key_or_url, key_or_url)
        self._client = Client(url)

    def __enter__(self) -> "OPCUAHandler":
        self._client.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self._client.disconnect()

    def write(self, node_id: str, value) -> None:
        """
        Écrit *value* dans *node_id* (auto-détection de type).
        Lève une exception si échec réseau ou NodeId inconnu.
        """
        node = self._client.get_node(node_id)
        # auto-cast: str → String, int → Int32, bool → Boolean
        variant = ua.Variant(value, ua.VariantType.String) if isinstance(value, str) else \
                  ua.Variant(value, ua.VariantType.Int32) if isinstance(value, int) else \
                  ua.Variant(value, ua.VariantType.Boolean) if isinstance(value, bool) else \
                  ua.Variant(value, ua.VariantType.String)
        node.set_value(variant)

    def read(self, node_id: str):
        """Renvoie la valeur brute du nœud."""
        node = self._client.get_node(node_id)
        return node.get_value()

# -----------------------------------------------------------------------------
# 4) Fonctions haut niveau utilisées par l’IHM ou la REST
# -----------------------------------------------------------------------------
def start_order(ilot: str, of_number: str) -> bool:
    """
    Écrit uniquement le numéro d’OF dans le tag StartOrder.
    Retourne True si succès, False sinon.
    """
    try:
        with OPCUAHandler(ilot) as plc:
            plc.write(NODE_START_ORDER, of_number)
        return True
    except Exception as e:
        print(f"[OPCUA] start_order KO sur {ilot}: {e}")
        return False


def send_order_details(
    ilot: str,
    of_number: str,
    code: str,
    qty: float | int,
    date_str: str
) -> bool:
    """
    Envoie plusieurs champs à l’automate:
      - StartOrder
      - OrderCode
      - OrderQuantity
      - OrderDate
    Retourne True si tous les writes aboutissent.
    """
    try:
        with OPCUAHandler(ilot) as plc:
            plc.write(NODE_START_ORDER, of_number)
            plc.write(NODE_ORDER_CODE, code)
            # quantité en Int32 pour éviter float sur automates
            plc.write(NODE_ORDER_QTY, int(qty))
            plc.write(NODE_ORDER_DATE, date_str)
        return True
    except Exception as e:
        print(f"[OPCUA] send_order_details KO sur {ilot}: {e}")
        return False


def get_states() -> dict[str, str]:
    """
    Retourne un dict {"LGN01":"RUN",...}. "OFF" si îlot injoignable.
    """
    res: dict[str, str] = {}
    for ilot, _url in OPCUA_ENDPOINTS.items():
        try:
            with OPCUAHandler(ilot) as plc:
                code = plc.read(NODE_STATE_MACHINE)
            res[ilot] = {0: "STOP", 1: "RUN", 2: "ALARM"}.get(code, str(code))
        except Exception:
            res[ilot] = "OFF"
    return res

# -----------------------------------------------------------------------------
# 5) Petit test local
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys, pprint
    # usage: python3 opcua_client.py start LGN02 WH/MO/00012
    #        python3 opcua_client.py send LGN02 WH/MO/00012 Code 1 2025-04-29T13:00:00
    if len(sys.argv) >= 3 and sys.argv[1] == "start":
        _, _, ilot, ofn = sys.argv
        print("→ start_order :", start_order(ilot, ofn))
    elif len(sys.argv) == 7 and sys.argv[1] == "send":
        _, _, ilot, ofn, code, qty, date = sys.argv
        ok = send_order_details(ilot, ofn, code, float(qty), date)
        print("→ send_order_details :", ok)
    else:
        pprint.pp(get_states())
