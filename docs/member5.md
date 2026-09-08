# Member 5 Developer Guide

## Scope and architecture

This is a Python standard-library skeleton. No teammate algorithms are implemented.

| Directory | Responsibility |
| --- | --- |
| `src/gui/` | Tkinter widgets, file dialogs, displaying controller results |
| `src/controllers/` | Input validation, media routing, protect/verify orchestration, saving |
| `src/verification/` | Ordered verification stages and verdict mapping |
| `src/interfaces/` | Typed protocols for teammate adapters |
| `src/models/` | Media, payload, verdict, and verification status objects |
| `src/exceptions/` | Expected integration failures |
| `src/services/` | Fail-closed unconfigured adapter |
| `tests/` | Mock-based integration tests |

`src/__main__.py` is the composition root: replace unconfigured services there
with concrete adapters. The GUI receives a controller and does not call services.
The controller can also be used without Tkinter.

## Expected interfaces

The executable contracts are in [src/interfaces](../src/interfaces/__init__.py).

| Owner | Service | Expected operations |
| --- | --- | --- |
| Member 1 | `ImageSteganographyService` | `capacity`, `embed`, `extract` |
| Member 2 | `AudioSteganographyService` | `capacity`, `embed`, `extract` |
| Member 3 | `CryptoService` | `hash_media`, `sign`, `verify_signature` |
| Member 3 | `PayloadService` | `create`, `pack`, `unpack` |
| Member 4 | `StartLocationService` | `generate`, `recover` |

- Media contains file bytes, normalized extension, and image/audio type.
- PNG/BMP and WAV extensions are routed provisionally. Adapters must validate
  actual format, lossless image encoding, and PCM WAV support.
- All LSB values are integers from 1–8. Capacity is in payload **bytes**, after
  framing overhead and the start offset. The adapter must enforce actual bounds.
- `embed` returns a complete encoded file in the input format.
- Agree start units with Members 1, 2, and 4 (pixels/channels/samples). Recovery
  must work for Party B without depending on a payload that is not yet extracted.
  Header/bootstrap persistence and required recovery context remain integration TODOs.
- Crypto keys are configured in the crypto adapter; no keys or secrets are
  generated, stored, or hardcoded by Member 5.
- Payload creation owns ID, timestamp, nonce, metadata, versioning, and canonical
  signed bytes. Parsing must derive the digest from those signed bytes and reject
  malformed envelopes. Unsigned duplicate digest fields must never be trusted.
- Agree a canonical media hash before implementing adapters. Raw file hashes
  cannot survive LSB embedding. Reserved bits and recovery headers need consistent
  treatment before and after embedding; excluded bits reduce integrity coverage.
  Record exactly which changes can and cannot be detected, especially at 8 LSB.
- Bind relevant media type, LSB, version, and algorithm identifiers into the
  signed schema. Adapters must validate them during verification.

## Workflows

Protect: validate → load/route → generate location → canonical media hash →
create signed content → sign → pack → capacity check → embed → return media.
Saving is a separate controller operation and refuses to overwrite existing files.

Verify: validate → load/route → recover location → extract/parse → verify
signature → compare canonical digest → return verdict and stage statuses.
Digest checking stops when the signature is invalid.

| Verdict | Condition |
| --- | --- |
| Authentic | Signature valid and canonical digest matches |
| Tampered | Valid signed payload, canonical digest differs |
| Signature Invalid | Signature verification returns false |
| Payload Missing | Extractor raises `PayloadMissing` or returns empty bytes |
| Wrong Start Location | Adapter explicitly raises `WrongStartLocation` |
| Cannot Verify | Invalid input, unavailable service, malformed payload, or other failure |

Do not infer wrong start location from arbitrary parse failures: damaged media,
wrong settings, and absent payloads may be indistinguishable. Authentic is limited
to the agreed hash coverage and configured key trust; it does not prove freshness.
Expected errors use `IntegrationError` subclasses. Unexpected verification errors
are logged and return Cannot Verify, never Authentic.

## GUI

Run `python3 -m src` on a desktop with Tkinter. Choose PNG/BMP/WAV, select 1–8 LSB,
then protect or verify. Save becomes enabled only after successful protection.
Changing file or LSB clears pending output. Party B selects the saved stego file
and the agreed LSB setting. Image comparison and audio playback are visible,
inactive placeholders. No simulated security result is shown in the GUI.

The skeleton invokes the controller synchronously. Before using large files,
add a worker/executor and marshal widget updates to Tkinter's main thread.

## Testing

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
git diff --check
git check-ignore .agents/README.md
```

Tests cover image/audio routing, all six verdicts, invalid input, missing files,
capacity rejection, all LSB selections, signature short-circuiting, safe saving,
unconfigured adapters, and Party A → saved file → Party B with mocks.
Fixture bytes are deliberately not real media. Real tamper detection and
cryptographic correctness require teammates' implementations and later tests.

Desktop smoke check: choose both media types, switch LSB, exercise protect and
verify with unconfigured adapters, and confirm comparison/playback are inactive.
With concrete adapters, also check saved output and repeat verification from
a fresh application instance.

## Integration TODOs

1. Agree canonical hashing coverage, signed payload schema, start units, recovery
   bootstrap, output formats, and key configuration with Members 1–4.
2. Implement thin adapters around teammates' existing public APIs and inject them
   in the composition root; avoid restructuring their modules.
3. Add real image/PCM WAV fixtures, capacity boundary cases, corrupted envelopes,
   wrong keys/settings, and tampering evidence for every supported LSB value.
4. Add background work, image comparison, audio playback, and key/recovery controls
   only after their interfaces are agreed.
5. Reconcile ambiguous verdicts with attack tests, document coverage limitations,
   and prepare the Party A/Party B demo.
