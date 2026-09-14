# Verification Engine & System Integration — Documentation

Member 5: Hellen
Files covered: `src/verification/engine.py`, `src/controllers/application.py`

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

## 5. Test coverage

`tests/test_engine.py` exercises the pipeline against the real
`ApplicationController`/`VerificationEngine`, using fakes in `tests/fakes.py`
for the four teammate services (`SteganographyService`, `CryptoService`,
`PayloadService`, `StartLocationService`).

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

Run: `python -m pytest tests -v` from the repo root.

## 6. Open items for the team

- [ ] Confirm with Member 4 whether `StartLocationService.recover()` self-checks
      (see §4). This is the single highest-value fix left for Criterion 1.
- [ ] Confirm `SteganographyService.extract()` self-frames the payload (magic +
      length prefix) since the interface gives it no length argument — Members
      1 and 2 need to know this before they start, not discover it at
      integration time.
- [ ] Wire these tests into `.github/workflows/ci.yml` so they run on every
      push, not just locally.
