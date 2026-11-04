import json, time
from websocket import create_connection

URLS = ["wss://api.derivws.com/trading/v1/options/ws/public",
        "wss://ws.derivws.com/websockets/v3?app_id=1089",
        "wss://ws.binaryws.com/websockets/v3?app_id=1089"]

class Deriv:
    # Appels publics uniquement (aucun token). Garde la derniere erreur pour diagnostic.
    def __init__(self, urls=None, pause=0.3):
        self.urls = urls or URLS
        self.pause = pause
        self.ws = None
        self.idx = 0
        self.last_error = None

    def _connect(self):
        url = self.urls[self.idx % len(self.urls)]
        try:
            return create_connection(url, timeout=20)
        except Exception:
            return create_connection(url, timeout=20, origin="https://developers.deriv.com")

    def call(self, req, retries=5):
        for i in range(retries):
            try:
                if self.ws is None:
                    self.ws = self._connect()
                self.ws.send(json.dumps(req))
                out = json.loads(self.ws.recv())
                time.sleep(self.pause)
                if out.get("error", {}).get("code") == "RateLimit":
                    time.sleep(4)
                    continue
                return out
            except Exception as e:
                self.last_error = type(e).__name__ + " " + str(e)[:120]
                self.ws = None
                self.idx += 1
                time.sleep(1 + i)
        return {"error": {"code": "ConnectionFailed", "message": str(self.last_error)}}
