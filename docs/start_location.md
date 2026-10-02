# Start Location Derivation: Documentation

Member 4: Galvin \
Files covered: `src/services/start_location.py`

## 1. What this component does

Plain LSB steganography writes from the first unit of the cover, so anyone who
suspects a file carries hidden data knows where to look. My component decides
**where** a payload begins instead, and lets the verifier find that same place
again.

| Name | Purpose |
|---|---|
| `KeyedStartLocation` | implements `StartLocationService`: `generate()` and `recover()` |
| `derive_nonce(key, canonical, lsb)` | a cover's 4-byte nonce |
| `derive_start(unit_count, key, nonce, payload_units)` | the position itself |
| `image_capacity()`, `audio_capacity()` | embeddable bit counts |

A **unit** is one embeddable sample: a colour sample for images, a PCM sample
for audio. Positions are flat unit indices, so the same logic serves both
media. The component never touches a pixel, a sample, a hash or a signature;
only `KeyedStartLocation._describe()` knows about concrete media services.

## 2. How a position is chosen

**Manual:** The user selects a position by hand via an input on the GUI.

**Automatic:** The position is derived from a passphrase and the cover, in two
HMAC-SHA256 stages:

```
key + canonical cover  --HMAC-SHA256-->  nonce (4 bytes)
key + nonce + bounds   --HMAC-SHA256-->  start unit index
```

HMAC-SHA256 is a keyed pseudo-random function, so without the passphrase the
output is uniform over the valid range and unpredictable. The digest is reduced
modulo the available span and offset by one, so unit 0 is never produced and
the payload never begins at the very first unit. The passphrase is mixed into
**both** stages: if the first were unkeyed, anyone holding the file could
compute the nonce from it.

`generate()` runs before the payload exists, so the position must be chosen
without knowing its length. Half the cover is held in reserve, guaranteeing
room for any payload that will subsequently be accepted, at a cost of one bit
of search space. Being a pure function of the unit count, `recover()`
recomputes the identical reserve.

## 3. Why the nonce comes from the cover

Nothing about the position is written into the file. The verifier recomputes
it, which works because of one property:

> Canonicalisation masks off the low `lsb` bits of every sample, exactly the
> bits embedding overwrites, so a cover and its stego output canonicalise to
> byte-identical data.

Same canonical bytes plus same passphrase gives the same nonce, hence the same
position. `generate()` and `recover()` run the identical derivation; there is
no stored state, which is what makes recovery possible.

This is also why the nonce is derived rather than random. A fresh random nonce
would have to be stored in the file to be recoverable, but reading it would
require knowing where it is, which is the problem being solved. Determinism is
the requirement here, not a weakness.

A stored nonce was considered and rejected. A reserved region at a known offset
would be a constant tell for steganalysis, and a cheap targeted attack: those
units could be destroyed to relocate the payload without touching anything
visible.

## 4. File Type detail

| | Image | Audio |
|---|---|---|
| Unit | colour sample, alpha excluded | PCM sample, channels interleaved |
| Unit count | `ImageSteganography.unit_count()` | `WavSteganographyService.sample_count()` |
| Canonical form | `ImageSteganography.canonical_bytes()` | `WavSteganographyService.canonical_bytes()` |
| Formats | PNG, BMP | 16-bit PCM WAV |

Both canonical forms come from **decoded** samples, not file bytes.

The audio service validates its start with `type(start) is not int`, which
rejects numpy integers, so `derive_start()` returns a plain `int`.

## 5. How it is wired in

`src/__main__.py` constructs one `KeyedStartLocation` with no passphrase. The
GUI assigns one before each operation, because whoever verifies a file may
supply a different passphrase than whoever protected it:

```python
locator.key = "party-A-passphrase"   # automatic mode
locator.manual_start = 5000          # manual mode, bypasses the passphrase
```

The controller and the verification engine share the one instance, so setting
either property covers both protect and verify. Setting `manual_start` to
`None` returns to keyed derivation.

Deriving with no passphrase set raises `IntegrationError` naming the problem,
so an empty field produces a verdict rather than a traceback. The passphrase is
suppressed in `__repr__` so it cannot leak into a log.

## 6. Security

The passphrase defeats casual extraction, since standard LSB tools read from
offset 0 and find nothing. It makes the position unpredictable: every cover
yields a different one, and a one-bit passphrase change relocates it entirely.
The passphrase itself is never written to disk.

It does not defeat exhaustive search. On a 128x128 RGB cover of 49,152 units,
an attacker who knows the scheme but not the passphrase recovered the payload
after 669 candidate positions in 0.06 seconds.

Passphrase strength does not change this, because the attack targets the size
of the position space rather than the key. The start location provides
obscurity, not confidentiality; integrity rests on the digital signature. Which was a learning point when implementing this system.

## 7. Known limitations

1. **Deterministic.** The same cover under the same passphrase always
   yields the same position.
2. **At `lsb = 8` the position stops depending on cover content.** The mask
   clears every sample, so nothing survives canonicalisation and two unrelated
   64x64 RGB covers both derive position 864. Inherent: at 8 bits there is no
   cover content left to bind to. The passphrase still governs the position,
   and the regime is unusable anyway, since replacing all 8 bits destroys the
   cover visually.
3. **Automatic mode uses only the first half of the cover**, because of the
   reserve in section 2. Manual mode can address any valid position.
4. **No resistance to exhaustive search**, as measured in section 6.
5. **Bound to decoded samples**, so re-encoding, resampling or format
   conversion breaks recovery, as they break the payload itself.
6. **Wrong Start Location is never produced.** `recover()` always returns a
   number and cannot validate its own answer, so a wrong passphrase reads as
   Payload Missing. See §4 of `verification_integration.md`.
7. **Tampered is only produced in manual mode.** In automatic mode a content
   edit moves the position, so the payload is never located and the signature
   is never reached. The file is still rejected, with a less specific verdict.
   See §7 of `verification_integration.md`.

Limitation 7 follows from the design rather than from a defect: binding the
position to cover content is exactly what removes the need to store anything.
