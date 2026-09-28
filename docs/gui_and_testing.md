# GUI, Attack Simulation & Automated Testing — Documentation

Member 6: Chun Yuan
Files covered: `src/gui/`, `src/attacks/`, `src/testing/`, `tests/test_attacks.py`,
`tests/test_scenarios.py`, `tests/test_gui*.py`, `tests/gui_browser*.py`

## 1. What this component does

Three things, all built on the other members' modules through `ApplicationController`:

- **GUI** for Protect, Verify and the attack functions, in two views: the glass
  desktop (default) and a native Tk fallback.
- **Attack simulation** (`src/attacks/`): a registry of named attacks that take a
  stego file and return a modified copy, for the GUI attack lab and the suite.
- **Automated test runner** (`src/testing/`): protects real covers, applies every
  attack and verifier misconfiguration, verifies, and records expected versus
  actual verdicts as evidence.

## 2. Glass desktop

Run `python -m src` from the repository root. The GUI opens maximised in an Edge
or Chrome app window. It uses local HTML/CSS with the existing Python workflows
and native file dialogs. No server framework, hosted service, frontend build
step or extra package is needed. `python -m src --native` opens the Tk view;
`--no-open` starts the renderer and prints its local URL without a window.

The renderer binds only to a random loopback port and a random session path.
Closing the app lets any active operation finish; refreshing reconnects to the
same session. The page is served uncached, so edits to the HTML, CSS or script
show on the next refresh.

### Workspace view

1. **Media preview.** The selected file is shown on the left (images inline,
   WAV files with an audio player). After Protect, the protected copy appears
   beside it and the third pane zooms into the region whose low bits changed,
   painting changed pixels in yellow; for audio it reports how many samples
   changed. The note states the counts and the zoomed rows and columns.
2. **Source.** Choose a PNG, BMP or PCM WAV file.
3. **Protection.** LSB depth 1 to 8, the start-location passphrase or a manual
   position, and the Protect button. Protect creates the protected copy in
   memory and does not claim a verdict.
4. **Verification.** Verify has two jobs. While an unsaved protected copy exists
   it self-checks that copy (Party A); on Authentic the Save button appears
   inside the results. Otherwise it verifies the selected file on disk
   (Party B). The four engine stages are listed live as they run, using the
   engine's optional `on_stage` observer.

### Test studio view

- **Attack lab.** The lab has its own file and settings, independent of the
  workspace: its own file picker, LSB depth, passphrase or manual position,
  and an optional hidden message that the suite embeds in every cover it
  protects. Choose a file, pick an attack for its type, and click Run
  attack simulation. The attacked copy is saved as
  `attacks/<file name>/<date>_<time>_<attack>.<ext>` next to the source
  (never overwriting) and verified immediately. The Attack result card shows
  the verdict, the four verification stages, the decoded message if any, and
  a before/after/what-changed comparison of the attacked copy. The chosen
  file stays selected, so the next attack starts from the clean stego again. The verification step needs
  the passphrase or manual position the file was protected with, exactly as
  Party B would; payload-level attacks need it before they run, because they
  must find the envelope to rewrite it. Media-level attacks run without it
  and the verification then reports what is missing.
- **Full simulation suite.** The first entry in the attack list runs the
  whole scenario suite (section 4) on the bundled samples plus the selected
  file. Each run writes its evidence to `run-<date>_<time>` inside the folder
  you choose. Failed scenarios are listed first, passed ones below, with a
  shared search box and a note column for known degradations.

## 3. Attack simulation (`src/attacks/`)

Attacks are registered with `@register(id, label, description, kinds)` and
listed by `describe(kind)`; the GUI, the suite and the tests share the
registry. The attack lab lists only the attacks that apply to the selected
file's type (nothing until a file is chosen), plus the "Every attack" entry
that runs the full suite. Media-level attacks need only the file.
Payload-level attacks rewrite the embedded envelope in place and need an
`AttackContext` with the LSB depth, the start unit and the steganography
service.

### Image files (PNG, BMP)

Expected verdict after the attack, verified with the same depth and settings
the file was protected with. "Manual" is a manual start position; "Automatic"
is a passphrase-derived start.

| Attack | What it does | Manual | Automatic |
|---|---|---|---|
| `reencode_lossless` Re-save losslessly | decodes and re-saves in the same format | Authentic | Authentic |
| `convert_container` Convert PNG to BMP or back | rewrites the pixels in the other lossless container | Authentic (RGB); Tampered / Payload Missing for RGBA PNGs, which lose their alpha channel | same |
| `pixel_edit` Edit one pixel | flips the top bit of one channel of the centre pixel | Tampered | Payload Missing (note) |
| `region_edit` Paint a block | paints a solid block over the bottom-right tenth | Tampered | Payload Missing (note) |
| `crop_bottom` Crop the bottom | removes the bottom tenth of the rows | Tampered | Payload Missing (note) |
| `lsb_noise` Randomise low bits | randomises the lowest bit of every channel | Payload Missing | Payload Missing |
| `lsb_strip` Clear low bits | clears the lowest bits at the chosen depth | Payload Missing | Payload Missing |
| `resize` Resize to 90% | scales with resampling, every pixel recomputed | Payload Missing | Payload Missing |
| `jpeg_roundtrip` JPEG round trip | saves as JPEG quality 90 and converts back, alpha kept | Payload Missing | Payload Missing |
| `edit_payload` Edit the payload | changes the media ID inside the signed JSON | Signature Invalid | Signature Invalid |
| `forge_message` Forge the hidden message | rewrites the hidden message inside the signed JSON | Signature Invalid | Signature Invalid |
| `corrupt_signature` Corrupt the signature | flips one bit in the embedded signature | Signature Invalid | Signature Invalid |
| `wipe_payload` Wipe the payload | overwrites the whole envelope with zeros | Payload Missing | Payload Missing |

### Audio files (16-bit PCM WAV)

| Attack | What it does | Manual | Automatic |
|---|---|---|---|
| `reencode_lossless` Re-write the WAV | rewrites the WAV with identical samples | Authentic | Authentic |
| `sample_edit` Edit one sample | flips a high-order bit of the middle sample | Tampered | Payload Missing (note) |
| `silence_tail` Silence the tail | zeroes the last twentieth of the samples | Tampered | Payload Missing (note) |
| `truncate` Truncate the end | drops the last tenth of the samples | Tampered | Payload Missing (note) |
| `lsb_noise` Randomise low bits | randomises the lowest bit of every sample | Payload Missing | Payload Missing |
| `lsb_strip` Clear low bits | clears the lowest bits at the chosen depth | Payload Missing | Payload Missing |
| `gain` Change volume | scales every sample to 80% | Payload Missing | Payload Missing |
| `edit_payload` Edit the payload | changes the media ID inside the signed JSON | Signature Invalid | Signature Invalid |
| `forge_message` Forge the hidden message | rewrites the hidden message inside the signed JSON | Signature Invalid | Signature Invalid |
| `corrupt_signature` Corrupt the signature | flips one bit in the embedded signature | Signature Invalid | Signature Invalid |
| `wipe_payload` Wipe the payload | overwrites the whole envelope with zeros | Payload Missing | Payload Missing |

(note) In automatic mode the start position is derived from the file content,
so a content edit moves it and the payload cannot be found; the file is still
rejected, with a less specific verdict. See `verification_integration.md`
section 7. The three payload-level attacks need the LSB depth and start
location of the payload, so the attack lab asks for them before running.

Verified end to end on 28 September 2026: all 13 image attacks and all 11
audio attacks produced these verdicts through the app's own workflow, in
both modes, on the bundled samples and on a 2004 by 1187 RGB photo.

## 4. Automated test runner and evidence

`python -m src.testing` builds the real suite and writes a fresh folder under
`test-evidence/` named `run-<date>_<time>` containing `results.json`,
`results.log` and `results.md`. It exits non-zero if any scenario fails, so CI
fails with it. Options: `--cover` (repeatable), `--lsb` (repeatable),
`--mode manual|auto|both`, `--message` (the hidden text embedded in every
cover), `--demo` (the two canned reporting scenarios). The Test studio runs the
same suite from the "Every attack (full simulation suite)" entry, adding the
studio's file as an extra cover and using the studio's hidden message.

### What one run contains

For every cover (bundled `lambda-icon.png` and `original.wav`, plus any
`--cover` or studio file), every depth (default 1) and both start modes
(manual position 100, and the passphrase `group2 attack suite`), the suite:

1. protects a fresh copy of the cover with the hidden message and saves it;
2. runs the **clean** scenario: verifies the untouched stego copy, expecting
   Authentic **and** the hidden message to decode exactly;
3. runs every attack from section 3 that applies to the cover's type on the
   saved stego copy, expecting the verdict in the Manual or Automatic column;
4. runs the verifier-side cases below once per cover and depth.

| Verifier case | Mode | What it does | Expected |
|---|---|---|---|
| `unprotected_cover` | manual | verifies the original cover | Payload Missing |
| `wrong_public_key` | manual | verifies with a different key pair | Signature Invalid |
| `wrong_passphrase` | auto | verifies with another passphrase | Payload Missing (note) |
| `wrong_start_position` | manual | verifies at position 107 instead of 100 | Payload Missing (note) |
| `wrong_lsb_depth` | manual | verifies at the next depth | Payload Missing |
| `missing_public_key` | manual | verifies with no public key on the machine | Cannot Verify |
| `unsupported_format` | manual | verifies a copy renamed to .jpg | Cannot Verify |

With the two bundled covers at depth 1 this is 62 scenarios; with a third
cover it is about 94 to 100. Each row records the expected verdict, the actual
verdict, the decoded message where one was expected, and a note. The
`unprotected_cover` case is skipped for a studio file, which may itself be a
stego file.

### Reading the results

A scenario **passes** when the actual verdict equals the expected one, and,
for clean scenarios, the hidden message decodes exactly. An execution error
always fails. PASS therefore means "the system reacted correctly", not "the
file was authentic": a Tampered result for a painted block is a pass.

The notes record the two known degradations from `verification_integration.md`:
in passphrase mode an edit moves the derived start so Tampered reads as Payload
Missing (section 7), and start recovery has no self-check so Wrong Start
Location is never produced (section 4). `tests/test_scenarios.py` asserts that
every other verdict is exercised and that the whole suite passes, so the
expected values must be updated deliberately when Member 4 changes the
start-location design.

## 5. Regression checks

Run the full suite with `python -m pytest -q`. If the temp folder is not
writable, add `--basetemp .\test-tmp`. Coverage relevant to this component:

| Test file | What it proves |
|---|---|
| `tests/test_attacks.py` | every attack produces decodable media and changes what it claims; payload attacks reach their verdicts |
| `tests/test_scenarios.py` | the real suite passes end to end and the evidence files are complete |
| `tests/test_preview.py` | the changed-bits zoom keeps small changes visible |
| `tests/test_gui.py`, `tests/test_glass_desktop.py` | workflow logic, self-check gating, HTTP bridge |
| `tests/test_automated_runner.py` | runner reporting with canned results |

The browser suite drives the real glass page in headless Edge with test
doubles for the media services and stubbed native dialogs:

```powershell
pip install -r tests\requirements-gui.txt
python -m tests.gui_browser
```

Pass `--tk-python <path>` if the current Python has no working Tk, and
`--browser <path>` for another Edge or Chrome location. Screenshots, reports and
a check summary are saved under `test-evidence/gui-*`.
