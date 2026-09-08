# INF2005 ACW1 — Member 5 Skeleton

Steganographic Image and Audio Integrity Verification with Digital Signature-Based Authentication.

This repository currently contains the Member 5 controller, verification engine,
service contracts, Tkinter GUI, and mock integration tests. Actual media,
cryptography, payload, and start-location algorithms await Members 1–4.
No AI functionality is included in the application.

## Run

Use Python 3.10 or newer, with Tkinter available for the GUI. No third-party
Python packages are required.

```sh
python3 -m src
python3 -m unittest discover -s tests -v
```

The GUI initially uses unconfigured adapters. Protect reports an adapter error;
verify reports **Cannot Verify**. Mock test results do not establish real media
integrity or cryptographic security.

See [Member 5 developer guide](docs/member5.md) for interfaces, workflows,
verdict semantics, and integration tasks.
