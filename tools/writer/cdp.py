import json
import urllib.request
import urllib.parse
from wsclient import connect, WebSocket

def list_tabs(port: int = 9222, host: str = "127.0.0.1", timeout: float = 5):
    url = f"http://{host}:{port}/json"
    # disable proxies
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, method="GET")
    with opener.open(req, timeout=timeout) as resp:
        data = resp.read()
        tabs = json.loads(data.decode('utf-8'))
        return [t for t in tabs if t.get("type") == "page"]

class CDP:
    def __init__(self, ws_url: str, timeout: float = 10):
        self.ws: WebSocket = connect(ws_url, timeout)
        self._msg_id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params
        self.ws.send_text(json.dumps(msg))
        while True:
            txt = self.ws.recv_text()
            data = json.loads(txt)
            if data.get("id") == self._msg_id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error'].get('message', data['error'])}")
                return data.get("result") or {}
            # skip events
    def evaluate(self, expression: str):
        res = self.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"].get("text", "JavaScript error"))
        return res.get("result", {}).get("value")  # undefined / functions have no value
    def close(self):
        self.ws.close()
