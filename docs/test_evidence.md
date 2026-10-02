# Test Evidence

Verification results from the automated attack suite.

## How to reproduce

```bash
python -m src.testing --lsb 1 --lsb 2 --lsb 4
```

Writes a timestamped folder under `test-evidence/` containing `results.md`,
`results.json` and `results.log`.

## Run summary

Run of 2026-10-02, **198 of 198 scenarios passed**.

| Breakdown | |
|---|---|
| Media | 105 image, 93 audio |
| LSB depths | 66 each at 1, 2 and 4 |
| Start modes | manual and automatic |

| Verdict | Count |
|---|---|
| Payload Missing | 99 |
| Signature Invalid | 42 |
| Authentic | 24 |
| Tampered | 21 |
| Cannot Verify | 12 |
| Wrong Start Location | 0 |

## Attacks on a protected file

Each attack is applied to a stego file, which is then verified.

| Attack | Manual mode | Automatic mode |
|---|---|---|
| `clean` (no attack) | Authentic | Authentic |
| `reencode_lossless` | Authentic | Authentic |
| `pixel_edit` | Tampered | Payload Missing |
| `region_edit` | Tampered | Payload Missing |
| `crop_bottom` | Tampered | Payload Missing |
| `convert_container` | Tampered | Payload Missing |
| `sample_edit` | Tampered | Payload Missing |
| `silence_tail` | Tampered | Payload Missing |
| `truncate` | Tampered | Payload Missing |
| `corrupt_signature` | Signature Invalid | Signature Invalid |
| `edit_payload` | Signature Invalid | Signature Invalid |
| `forge_message` | Signature Invalid | Signature Invalid |
| `lsb_noise` | Payload Missing | Payload Missing |
| `lsb_strip` | Payload Missing | Payload Missing |
| `wipe_payload` | Payload Missing | Payload Missing |
| `resize` | Payload Missing | Payload Missing |
| `jpeg_roundtrip` | Payload Missing | Payload Missing |
| `gain` | Payload Missing | Payload Missing |

Content edits give different verdicts per mode. Automatic mode derives the
start position from the cover's content, so editing the content moves the
payload and it cannot be located. Manual mode pins the position, so the payload
is still found and the signature reports the edit. Both reject the file.

## Verifier-side cases

| Case | Verdict |
|---|---|
| `unprotected_cover` | Payload Missing |
| `wrong_passphrase` | Payload Missing |
| `wrong_start_position` | Payload Missing |
| `wrong_lsb_depth` | Payload Missing |
| `wrong_public_key` | Signature Invalid |
| `missing_public_key` | Cannot Verify |
| `unsupported_format` | Cannot Verify |

## Notes

`Wrong Start Location` is never produced. Start recovery always returns a
position and cannot check its own answer, so a wrong passphrase reads as
Payload Missing. See §4 of `verification_integration.md`.

Raw evidence folders are not committed; `test-evidence/` is in `.gitignore`.
