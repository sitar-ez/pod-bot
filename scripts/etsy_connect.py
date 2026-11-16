"""
One-time Etsy connection. Run on your own computer:

    python3 scripts/etsy_connect.py

It opens Etsy in your browser, you click "Allow access", and it prints the
ETSY_REFRESH_TOKEN to paste into GitHub Secrets. Uses only built-in Python.
"""
import base64
import hashlib
import http.server
import json
import secrets
import urllib.parse
import urllib.request
import webbrowser

PORT = 3003
REDIRECT = f"http://localhost:{PORT}/callback"
SCOPES = "listings_r listings_w listings_d shops_r shops_w transactions_r transactions_w profile_r"

keystring = input("Paste your Etsy app KEYSTRING and press Enter: ").strip()
verifier = secrets.token_urlsafe(64)[:96]
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
state = secrets.token_urlsafe(16)
url = "https://www.etsy.com/oauth/connect?" + urllib.parse.urlencode({
    "response_type": "code", "redirect_uri": REDIRECT, "scope": SCOPES, "client_id": keystring,
    "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
})
result = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if q.get("state", [""])[0] != state or "code" not in q:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Something went wrong. Close this tab and run the script again.")
            return
        body = urllib.parse.urlencode({"grant_type": "authorization_code", "client_id": keystring,
                                       "redirect_uri": REDIRECT, "code": q["code"][0],
                                       "code_verifier": verifier}).encode()
        req = urllib.request.Request("https://api.etsy.com/v3/public/oauth/token", data=body)
        result.update(json.load(urllib.request.urlopen(req)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Connected. You can close this tab and go back to the Terminal.</h2>")

    def log_message(self, *a):
        pass


print("\nOpening Etsy in your browser. Click 'Allow access'...")
webbrowser.open(url)
http.server.HTTPServer(("localhost", PORT), Handler).handle_request()
if "refresh_token" in result:
    print("\nSuccess! Copy everything on the next line into the GitHub secret ETSY_REFRESH_TOKEN:\n")
    print(result["refresh_token"])
    print()
else:
    print("Did not get a token:", result)
