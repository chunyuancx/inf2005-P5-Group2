# Verification Engine & System Integration — Documentation

Member 5: Hellen
Files covered: `src/verification/engine.py`, `src/controllers/application.py`,
`src/services/crypto_adapter.py`, `src/services/payload_service.py`, `src/__main__.py`

## 1. What this component does

`ApplicationController` is the single entry point the GUI talks to. It has
three public operations:

- `protect(path, lsb)` — load a cover file, build and sign a payload, embed it,
  return the stego media.
- `verify(path, lsb)` — load a file, recover the start location, extract and
  check the payload, return a `VerificationResult`.
- `save(media, path)` — write bytes to disk, refusing to overwrite an existing
  file.

`VerificationEngine` holds the actual verdict logic and is only ever called
from inside `ApplicationController.verify()`.

## 2. The verdict pipeline

`VerificationEngine.verify()` runs four stages in a fixed order and stops at
the first failure:

```
1. location.recover(media, lsb)         -> start unit
2. steganography.extract(media, lsb, start) -> raw envelope bytes
3. payload.unpack(encoded)              -> Payload(signed_data, digest, signature)
4. crypto.verify_signature(...)         -> bool
5. crypto.hash_media(...) vs payload.digest -> match / mismatch
```

| Stage fails | Verdict |
|---|---|
| `recover()` raises `WrongStartLocation` | **Wrong Start Location** |
| `extract()`/`unpack()` raises `PayloadMissing` | **Payload Missing** |
| signature check returns `False` | **Signature Invalid** |
| digest comparison mismatches | **Tampered** |
| any other `IntegrationError`, or an unexpected exception | **Cannot Verify** |
| all stages pass | **Authentic** |

**Signature is checked before the media hash on purpose.** If the signature
doesn't verify, the payload — including the digest inside it — cannot be
trusted, so comparing that digest against the media would be meaningless. The
only way to reach a Tampered verdict is: signature valid, but the media
doesn't match what was signed. That is the honest definition of "tampered
after protection."

## 3. Why the media hash isn't a hash of the file

Embedding the payload changes the low-order bits of the cover object, so
`hash(protected_file) != hash(original_file)` by construction — that's true
even for an untampered file. `CryptoService.hash_media(media, lsb)` must hash
a *canonical* representation that masks out the bits reserved for embedding,
so the same value is produced before and after protection. This is the "hash
agreed canonical media excluding reserved embedding bits" comment in the
interface. Both `protect()` and `verify()` must call this with the *same*
`lsb` value, or the mask won't line up and every file reports Tampered.

## 4. Known gap: Wrong Start Location may be unreachable

**This is the one finding worth raising with the team and the marker.**

`WRONG_START_LOCATION` can only be produced by
`StartLocationService.recover()` raising `WrongStartLocation`. The engine
never infers it from a failed extraction — `extract()` is only allowed to
signal `PayloadMissing`.

The natural way to implement `recover()` is to just re-run the same
deterministic formula used in `generate()` (same key, same media, same
formula ⇒ same offset). That implementation can **never** raise
`WrongStartLocation`, because it has no way to tell "this key is wrong" from
"this key is right" — it just computes an offset and hands it over. A wrong
key silently produces a wrong offset, extraction finds no valid envelope
there, and the verdict comes back **Payload Missing** instead of **Wrong
Start Location**, even though the real cause is a location/key mismatch.

Proven in `tests/test_engine.py::test_naive_locator_cannot_reach_wrong_start_location`
— that test passes today, and its passing is the demonstration of the gap.

**Fix**: `recover()` needs a way to self-check independently of the main
payload — e.g. a small fixed-size keyed marker embedded at a location that
does *not* depend on the payload's length, checked before the main offset is
returned. `tests/fakes.py::SelfCheckingStartLocation` is a worked example, and
`test_selfchecking_locator_raises_wrong_start_location` shows it working.

Action: confirm with whoever owns `StartLocationService` (Member 4) whether
their real implementation does this self-check. If not, either add it, or be
ready to explain in the demo why Wrong Start Location degrades to Payload
Missing in your design — that's a defensible answer too, but it must be
stated on purpose, not discovered by the marker.

## 5. How the real modules are wired

`src/__main__.py` builds the controller from the real services:

| Interface | Implementation | Owner |
|---|---|---|
| `ImageSteganographyService` | `ImageSteganography` | Member 1 |
| `AudioSteganographyService` | `WavSteganographyService` | Member 2 |
| `CryptoService` | `SignatureCrypto` (adapter over `CryptoService`) | Member 3, adapter by Member 5 |
| `PayloadService` | `EnvelopePayloadService` (built on `models/payload.py`) | Member 3, adapter by Member 5 |
| `StartLocationService` | `KeyedStartLocation` | Member 4 |

**Crypto adapter.** Member 3's `CryptoService` takes explicit keys and raw
bytes, so `SignatureCrypto` supplies both:

- `hash_media(media, lsb)` = SHA-256 of the steganography service's
  `canonical_bytes(media, lsb)` (samples with the reserved low bits cleared).
- Keys are RSA-2048 (PSS, SHA-256), stored as PEM in
  `~/.inf2005-stego/keys/`. The pair is created on the first protect; the
  private key file is owner-only (0600) and unencrypted.
- Verification never creates keys. With no public key the verdict is
  **Cannot Verify**, because a freshly generated key could only ever report
  a misleading Signature Invalid. To verify on another machine, copy
  `public_key.pem` into that folder.

**Payload envelope.** `>2sHH` = magic `b"P1"` | signed_data length |
signature length, then signed_data, then signature. The steganography
services already frame the whole envelope with their own magic and length.
`signed_data` is Member 3's `Payload` JSON (`media_id`, `timestamp`, `nonce`,
`metadata`), with the media digest stored in `metadata.digest`, so the
signature covers the digest. A malformed envelope reads as **Payload
Missing**; an edit inside a well-formed one fails the signature check.

## 6. Test coverage

Run: `pip install -r requirements-dev.txt`, then `python -m pytest` from the
repo root. CI runs the same command on every push.

`tests/test_engine.py` exercises the pipeline logic against fakes in
`tests/fakes.py`:

| Test | Verdict path proven |
|---|---|
| `test_authentic_round_trip` | Authentic |
| `test_all_lsb_depths` | Authentic at every LSB depth 1–8 |
| `test_tampered_media_detected` | Tampered |
| `test_signature_invalid_with_wrong_verify_key` | Signature Invalid |
| `test_payload_missing_on_unprotected_file` | Payload Missing |
| `test_cannot_verify_on_unsupported_format` | Cannot Verify |
| `test_capacity_rejected_before_writing` | capacity check blocks `protect()` |
| `test_selfchecking_locator_raises_wrong_start_location` | Wrong Start Location (fixable design) |
| `test_naive_locator_cannot_reach_wrong_start_location` | documents the gap in §4 |

`tests/test_real_pipeline.py` runs every real service end to end on
`samples/lambda-icon.png` and `samples/audio/original.wav`, with no fakes:

| Test | Verdict path proven |
|---|---|
| `test_authentic_round_trip` | Authentic, PNG and WAV, LSB 1/2/4 |
| `test_keys_persist_across_sessions` | Authentic after reloading keys from disk |
| `test_tampered_with_manual_start` | Tampered, PNG and WAV |
| `test_tampered` (xfail) | documents the limitation in §7 |
| `test_signature_invalid_with_other_public_key` | Signature Invalid, PNG and WAV |
| `test_payload_missing_on_unprotected_cover` | Payload Missing, PNG and WAV |
| `test_wrong_passphrase_reports_payload_missing` | wrong passphrase → Payload Missing (§4) |
| `test_wrong_lsb_depth_is_not_authentic` | wrong LSB depth never reads as Authentic |
| `test_verify_without_public_key_cannot_verify` | Cannot Verify |

## 7. Known limitations with the real start-location service

- **Wrong Start Location** is not produced: `KeyedStartLocation.recover()`
  re-runs `generate()` without a self-check, so a wrong passphrase reads as
  **Payload Missing** (§4).
- **Tampered** is only produced in manual start mode. In passphrase mode the
  start position is derived from the canonical media content, so editing
  the content also moves the start, and the payload reads as **Payload
  Missing**. The file is still rejected, just with a less specific verdict.
  `test_tampered` is marked `xfail(strict=True)` and will fail loudly once
  this changes, so the marker can be removed then.
