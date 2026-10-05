"""One-time browser sign-in for the read-only Gmail API client.

Run from the backend folder:
    python gmail_auth.py
"""

import truststore

truststore.inject_into_ssl()

from google_auth_oauthlib.flow import InstalledAppFlow

from mcp.gmail_client import GMAIL_SCOPE, keys_path, token_path


def main() -> None:
    keys = keys_path()
    if not keys.is_file():
        raise SystemExit(f"OAuth client file not found: {keys}")
    flow = InstalledAppFlow.from_client_secrets_file(str(keys), [GMAIL_SCOPE])
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    destination = token_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(creds.to_json(), encoding="utf-8")
    print(f"Saved Gmail token to {destination}")


if __name__ == "__main__":
    main()
