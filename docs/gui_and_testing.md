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
  (never overwriting), selected, and verified immediately; the verdict is
  shown in the lab and in the workspace card. The verification step needs
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

| Attack | What it does | Simulates |
|---|---|---|
| `pixel_edit` | flips the top bit of one channel of the centre pixel | the smallest visible edit |
| `region_edit` | paints a solid block over the bottom-right tenth | a stamp or watermark |
| `crop_bottom` | removes the bottom tenth of the rows | trimming that leaves earlier pixels intact |
| `resize` | scales to 90% with resampling | every pixel recomputed |
| `jpeg_roundtrip` | saves as JPEG quality 90 and converts back (alpha kept) | lossy compression |
| `lsb_noise` | randomises the lowest bit of every channel | invisible payload destruction |
| `lsb_strip` | clears the lowest bits at the chosen depth | invisible payload wipe |
| `reencode_lossless` | decodes and re-saves in the same format | a benign re-save; must survive |
| `convert_container` | rewrites the pixels as BMP (or PNG) | a benign conversion; RGBA PNGs lose alpha |

### Audio files (16-bit PCM WAV)

| Attack | What it does | Simulates |
|---|---|---|
| `sample_edit` | flips a high-order bit of the middle sample | a single click |
| `silence_tail` | zeroes the last twentieth of the samples | a muted ending |
| `truncate` | drops the last tenth of the samples | trimming that leaves earlier samples intact |
| `gain` | scales every sample to 80% | a volume change |
| `lsb_noise` | randomises the lowest bit of every sample | inaudible payload destruction |
| `lsb_strip` | clears the lowest bits at the chosen depth | inaudible payload wipe |
| `reencode_lossless` | rewrites the WAV with identical samples | a benign re-save; must survive |

### Payload-level attacks (both file types)

| Attack | What it does | Simulates |
|---|---|---|
| `edit_payload` | changes the media ID inside the signed JSON, signature untouched | forging the hidden record |
| `forge_message` | rewrites the hidden message text inside the signed JSON, signature untouched | forging what Party B reads |
| `corrupt_signature` | flips one bit in the embedded signature | a damaged or forged signature |
| `wipe_payload` | overwrites the whole envelope with zeros | scrubbing the hidden data |

## 4. Automated test runner and evidence

`python -m src.testing` builds the real suite and writes a fresh folder under
`test-evidence/` containing `results.json`, `results.log` and `results.md`. It
exits non-zero if any scenario fails, so CI fails with it. Options: `--cover`
(repeatable), `--lsb` (repeatable), `--mode manual|auto|both`, `--demo` (the
two canned reporting scenarios).

For each cover, depth and start mode the suite protects the cover, applies each
attack to the saved stego copy, and verifies the result. It also covers the
verifier-side cases: unprotected cover, wrong public key, wrong passphrase,
wrong manual position, wrong LSB depth, missing public key and an unsupported
format. Each scenario states the verdict expected **today**:

| Scenario | Manual start | Passphrase start |
|---|---|---|
| clean, lossless re-save | Authentic | Authentic |
| visible edits, crop, truncate | Tampered | Payload Missing (note) |
| LSB noise or strip, resize, gain, JPEG | Payload Missing | Payload Missing |
| edited payload, corrupted signature | Signature Invalid | Signature Invalid |
| wiped payload, unprotected cover, wrong depth | Payload Missing | Payload Missing |
| wrong passphrase or position | Payload Missing (note) | Payload Missing (note) |
| missing public key, unsupported format | Cannot Verify | Cannot Verify |

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
