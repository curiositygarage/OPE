#!/usr/bin/env python3
"""Reusable CDP helpers for the shared browser (default port 18800).

Consolidated from on-page-editor verification work (2026-08-01).
Key gotcha baked in: Chrome rejects cross-origin WebSocket connections unless
Origin is suppressed — always create connections with suppress_origin=True.

Usage (import or run directly):
    from cdp_helpers import CDP
    c = CDP("B02A...TAB_ID")          # or CDP() for first page tab
    c.eval("document.title")
    c.reload(ignore_cache=True)
    c.mobile_viewport()               # emulate a phone, e.g. 412x915
    c.screenshot("/tmp/shot.png")
    c.close_tab()
"""
import base64
import json
import sys
import time
import urllib.request
import websocket


class CDP:
    def __init__(self, tab_id=None, port=18800, timeout=45):
        self.port = port
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
        pages = [t for t in tabs if t.get("type") == "page"]
        tab = next((t for t in pages if t["id"] == tab_id), pages[0]) if pages else None
        if not tab:
            raise RuntimeError(f"no page tabs on :{port}")
        self.ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], timeout=timeout, suppress_origin=True
        )
        self._mid = 0
        self.send("Page.enable")

    def send(self, method, params=None):
        self._mid += 1
        mid = self._mid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                resp = json.loads(self.ws.recv())
            except Exception:
                continue
            if resp.get("id") == mid:
                return resp
        return None

    def eval(self, expression):
        r = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if r and "result" in r and "result" in r["result"]:
            return r["result"]["result"].get("value")
        return None

    def reload(self, ignore_cache=True):
        self.send("Page.reload", {"ignoreCache": ignore_cache})
        time.sleep(3.5)

    def mobile_viewport(self, width=412, height=915, scale=2.6):
        self.send("Emulation.setDeviceMetricsOverride",
                  {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": True})
        self.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})

    def screenshot(self, out_path):
        r = self.send("Page.captureScreenshot", {"format": "png"})
        if r and "result" in r and "data" in r["result"]:
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(r["result"]["data"]))
            return out_path
        return None

    def close_tab(self):
        try:
            self.send("Page.close")
        finally:
            self.ws.close()

    def close(self):
        self.ws.close()


def close_all_tabs_except(keeper_id=None, port=18800):
    """Close every page tab on the shared browser except keeper_id (if given)."""
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    closed = []
    for t in tabs:
        if t.get("type") != "page":
            continue
        if keeper_id and t["id"] == keeper_id:
            continue
        try:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=8, suppress_origin=True)
            ws.send(json.dumps({"id": 1, "method": "Page.close"}))
            ws.close()
            closed.append(t.get("url", ""))
        except Exception:
            pass
    return closed


if __name__ == "__main__":
    c = CDP()
    print(json.dumps(c.eval("({t: document.title, w: innerWidth, h: innerHeight})"), indent=1))
    c.close()
