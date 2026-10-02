# Steganographic Image and Audio Integrity Verification

A GUI tool that hides a signed verification payload inside an image or audio
file, then later checks whether that file is still authentic.

Protecting a file hashes the cover, builds a payload containing that hash plus
metadata, signs it with a private key, and embeds the result using LSB
replacement at a start position that is either derived from a passphrase or
chosen by hand. Verifying reverses the process and reports a verdict.

## Dependencies

- **Python 3.13 or newer**
- **Tkinter**. Bundled with the python.org installers on Windows and macOS. On
  Debian or Ubuntu, install `python3-tk`.
- A Chromium browser (Edge or Chrome) for the default interface. Without one,
  use the `--native` option below.

Python packages, declared in `requirements.txt`:

| Package | Minimum | Used for |
|---|---|---|
| `cryptography` | 42 | RSA key generation, signing, signature verification |
| `numpy` | 1.26 | image pixel manipulation |
| `pillow` | 10 | PNG and BMP decoding and encoding |

## Setup

From the repository root, create a virtual environment:

```bash
python -m venv .venv
```

Activate it. Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

If you would rather not activate the environment, call its interpreter
directly instead: `.\.venv\Scripts\python.exe` on Windows, `.venv/bin/python`
on macOS and Linux. The commands below assume an activated environment.

### Keys

An RSA keypair is generated automatically the first time the application
signs or verifies anything. No setup step is needed. The keys are written to:

```
~/.inf2005-stego/keys/private_key.pem
~/.inf2005-stego/keys/public_key.pem
```

On Windows that path is `C:\Users\<you>\.inf2005-stego\keys\`.

The private key signs payloads and the public key verifies them. To verify a
protected file on a different machine, copy the **public** key to the same
path on that machine. The private key does not need to leave the machine that
protected the file.

## Commands

Launch the application:

```bash
python -m src
```

The interface opens in an Edge or Chrome application window, served from a
random loopback port with a random session path. Nothing leaves the machine;
all processing is local.

| Command | Effect |
|---|---|
| `python -m src` | open the default interface in a browser window |
| `python -m src --native` | open the Tkinter window instead |
| `python -m src --no-open` | start the local server and print its URL without opening a window |

Use `--native` if no Chromium browser is installed, or `--no-open` to open the
printed URL in a browser of your choice.

## Using the interface

Both interfaces offer the same workflow. Control names below are from the
default browser view; the Tkinter view uses slightly different wording, noted
in brackets.

**To protect a file:**

1. **Choose a media file** [Choose file] and select a PNG, BMP, or 16-bit PCM
   WAV
2. Select an **LSB depth** from 1 to 8
3. Enter a **passphrase**, or switch the start mode to **Manual** [Choose start
   position manually] and type a position
4. **Protect file** [Protect / encode]
5. **Save stego file**, and choose where to write it

**To verify a file:**

1. **Choose a media file** and select the stego file that was saved
2. Set the **same LSB depth** and the **same passphrase**, or the same manual
   position, that were used when protecting
3. **Verify file** [Verify]

After saving, the file selector still points at the original cover. Select the
saved stego file before verifying.

### Start-location modes

**Automatic** derives the position from the passphrase and the cover's own
content, so every file gets a different position and nothing about it is
stored in the file. The verifier needs the same passphrase.

**Manual** uses the position typed into the box and ignores the passphrase.
The verifier needs the same position.

Both modes require the same LSB depth at protect and verify time.

## Accepted files

| Medium | Formats | Notes |
|---|---|---|
| Image | PNG, BMP | lossless only; grayscale, palette and RGBA images are accepted |
| Audio | WAV | 16-bit PCM only, mono or stereo |

JPEG is rejected. Lossy compression destroys the low bits the payload occupies.

Sample covers are provided under `samples/`.

## Further information

Each component has its own design notes under `docs/`:

| Component | Document |
|---|---|
| Audio embedding and extraction | [docs/audio_steganography.md](docs/audio_steganography.md) |
| Payload structure, hashing and signatures | [docs/crypto_doc.md](docs/crypto_doc.md) |
| Start location derivation | [docs/start_location.md](docs/start_location.md) |
| Verification engine and system integration | [docs/verification_integration.md](docs/verification_integration.md) |
| GUI, attack simulation and automated testing | [docs/gui_and_testing.md](docs/gui_and_testing.md) |

## Troubleshooting

**`ModuleNotFoundError: No module named 'cryptography'`**: the virtual
environment is not activated, or the dependencies are not installed. Follow the
setup steps above.

**`ModuleNotFoundError: No module named 'tkinter'`**: install the Tk package
for your platform (`python3-tk` on Debian or Ubuntu). On Windows and macOS,
reinstall Python from python.org with the default options.

**No browser window opens**: use `python -m src --native`, or run
`python -m src --no-open` and open the printed URL yourself.

**A file that was just protected does not verify**: confirm that the saved
stego file is selected rather than the original cover, and that the LSB depth
and passphrase match the values used when protecting. The LSB depth resets to 1
each time the application starts.
