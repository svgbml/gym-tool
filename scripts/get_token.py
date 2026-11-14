"""Eenmalig: haal een Strava refresh token op (scope activity:read_all).

Gebruik (op je eigen pc):
  python scripts/get_token.py <CLIENT_ID> <CLIENT_SECRET>

1. Het script toont een link. Open die, log in bij Strava en klik op Authorize.
2. Je browser gaat naar http://localhost/exchange_token?...&code=XXXX
   (de pagina laadt niet; dat is normaal). Kopieer de waarde achter code=.
3. Plak die code hier. Het script toont je refresh token: zet die als
   GitHub Secret STRAVA_REFRESH_TOKEN.
"""
import sys
import urllib.parse

import requests

if len(sys.argv) != 3:
    sys.exit("Gebruik: python scripts/get_token.py <CLIENT_ID> <CLIENT_SECRET>")
client_id, client_secret = sys.argv[1], sys.argv[2]
url = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode({
    "client_id": client_id,
    "response_type": "code",
    "redirect_uri": "http://localhost/exchange_token",
    "approval_prompt": "force",
    "scope": "read,activity:read_all",
})
print("Open deze link en klik op Authorize:\n", url, "\n")
code = input("Plak de code (achter code= in de adresbalk): ").strip()
r = requests.post("https://www.strava.com/oauth/token", data={
    "client_id": client_id, "client_secret": client_secret,
    "code": code, "grant_type": "authorization_code"}, timeout=30)
r.raise_for_status()
print("\nSTRAVA_REFRESH_TOKEN =", r.json()["refresh_token"])
