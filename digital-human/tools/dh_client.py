"""Minimal Python client for the Digital Human control API (no dependencies).

    from dh_client import DH
    dh = DH("http://localhost:8765")
    dh.walkTo({"x": 1, "z": 2})
    dh.setEmotion("joy", 0.7)
    dh.speak("안녕하세요!")
    print(dh.getState()["body"])

Any public API function name works as a method; positional args are forwarded.
"""
import json
import urllib.error
import urllib.request


class DHError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


class DH:
    def __init__(self, base="http://localhost:8765", timeout=120):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def call(self, cmd, *args, timeout=None):
        body = json.dumps({"cmd": cmd, "args": list(args), "timeout": timeout or self.timeout}).encode()
        req = urllib.request.Request(self.base + "/api/control", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=(timeout or self.timeout) + 5) as r:
                res = json.load(r)
        except urllib.error.HTTPError as e:
            res = json.load(e)
        if not res.get("ok"):
            raise DHError(res.get("error"), res.get("message"))
        return res.get("result")

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **kw: self.call(name, *a, **kw)


if __name__ == "__main__":
    import sys
    dh = DH(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765")
    print(json.dumps(dh.getState()["body"], indent=1))
