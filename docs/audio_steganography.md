# Audio Steganography

## Overview

For this project, I implemented the Audio Steganography component.

My implementation hides payload data inside audio files using Least Significant Bit (LSB) steganography. I use uncompressed 16-bit PCM WAV files as the cover media.

During encoding, I convert the payload into bits and embed those bits into the least significant bits of the audio PCM samples.

During decoding, I read the same least significant bits from the audio samples and reconstruct them back into the original payload bytes.

The main goal of my implementation is to allow data to be hidden inside an audio file while keeping the resulting stego audio as a valid and playable WAV file.

---

## Supported Audio Format

My audio steganography implementation currently supports:

- File format: `.wav`
- Audio encoding: Uncompressed PCM
- Sample width: 16-bit
- LSB depth: 1 to 8 bits
- Maximum payload size: 8 MiB
- Configurable start location for payload embedding

Audio formats such as MP3, M4A, AAC and FLAC are not supported by my current implementation.

Compressed WAV files are also not supported.

The WAV file must use 16-bit PCM samples.

---

## How My Audio Steganography Works

My implementation follows this general process:

```text
Original WAV
    ↓
Read PCM samples
    ↓
Prepare payload
    ↓
Convert payload bytes into bits
    ↓
Embed payload bits into audio LSBs
    ↓
Write modified PCM samples
    ↓
Stego WAV
```

For decoding:

```text
Stego WAV
    ↓
Read PCM samples
    ↓
Read selected LSBs
    ↓
Reconstruct bit stream
    ↓
Convert bits back into bytes
    ↓
Read payload header
    ↓
Recover payload
```

---

## Encoding / Embedding

The main embedding function in my audio implementation is:

```python
def embed(
    self,
    media: Media,
    payload: bytes,
    lsb: int,
    start: int
) -> bytes:
```

The function performs the following steps:

1. Validates the selected LSB value.
2. Validates the start location.
3. Reads the WAV audio samples.
4. Checks whether the payload exceeds the maximum allowed size.
5. Checks whether the selected WAV file has enough capacity.
6. Creates a small header containing a magic value and payload length.
7. Converts the header and payload into bits.
8. Groups the bits based on the selected LSB depth.
9. Inserts the bits into the least significant bits of the PCM samples.
10. Writes the modified samples back into a valid WAV file.

The actual modification of each PCM sample is performed using:

```python
samples[sample_index] = self._set_sample_lsb(
    samples[sample_index],
    value,
    lsb
)
```

The `_set_sample_lsb()` function clears the selected least significant bits and replaces them with payload bits.

The important logic is:

```python
low_mask = (1 << lsb) - 1

unsigned &= (0xFFFF ^ low_mask)

unsigned |= (value & low_mask)
```

This allows me to modify only the selected least significant bits while preserving the rest of the 16-bit audio sample.

---

## Decoding / Extraction

The main extraction function is:

```python
def extract(
    self,
    media: Media,
    lsb: int,
    start: int
) -> bytes:
```

The extraction process reverses the embedding process.

My decoder:

1. Validates the selected LSB value.
2. Validates the supplied start location.
3. Reads the PCM samples from the WAV file.
4. Reads the embedded payload header.
5. Checks the magic value to determine whether a valid payload exists.
6. Reads the stored payload length.
7. Determines how many PCM samples are required.
8. Reads the required LSB values.
9. Converts the recovered bits back into bytes.
10. Removes the audio steganography header.
11. Returns the recovered payload bytes.

The actual LSB reading is performed by my `_read_bits()` function.

The important masking operation is:

```python
value = unsigned & low_mask
```

This keeps only the required least significant bits from each audio sample.

The bits are then reconstructed into bytes using:

```python
framed = self._bits_to_bytes(
    all_bits[:total_bits]
)
```

Finally, I return the recovered payload using:

```python
return framed[
    self.HEADER.size:
    self.HEADER.size + payload_length
]
```

My audio component therefore handles the hiding and recovery of the raw payload bytes.

Any additional interpretation, cryptographic verification or payload processing is handled by the shared project components.

---

## Payload Header

I use a small header before the actual payload.

The header contains:

```python
MAGIC = b"E1"

HEADER = struct.Struct(">2sI")
```

The magic value allows my decoder to determine whether the selected audio file contains a valid embedded payload.

The payload length tells the extraction function how many bytes need to be recovered.

The encoded data therefore follows this structure:

```text
MAGIC
+
Payload Length
+
Payload
```

This prevents the decoder from reading unnecessary PCM samples after the payload has ended.

---

## LSB Depth

My implementation supports an LSB depth from:

```text
1 to 8 bits
```

A lower LSB value modifies fewer bits from each PCM sample.

For example:

```text
1 LSB
```

uses only the lowest bit of each PCM sample.

A higher value such as:

```text
8 LSB
```

allows more payload data to be stored per sample, but modifies more of the original audio sample.

The program validates the LSB value and rejects values outside the range of 1 to 8.

---

## Audio Capacity

The amount of payload that can actually be stored depends on:

```text
Number of available PCM samples
×
Selected LSB depth
```

My capacity function calculates the available payload capacity based on:

- number of PCM samples
- selected start location
- selected LSB depth
- payload header size

Although my implementation has a hard payload limit of:

```text
8 MiB
```

the actual usable payload may be smaller depending on the selected WAV file.

The absolute maximum is:

```text
8 MiB
=
8,388,608 bytes
```

For plain ASCII text, this is approximately:

```text
8,388,608 characters
```

However, the practical capacity is normally limited by the WAV file before the 8 MiB limit is reached.

---

## Start Location

My audio steganography implementation also supports specifying a start location.

The start location determines which PCM sample the embedding process begins from.

Instead of always embedding the payload from the first audio sample, the system can begin from another valid sample location.

The same start location must be correctly determined during extraction so that the payload can be recovered.

The start location must be a non-negative integer.

---

## Canonical Audio Bytes

I also implemented a helper function:

```python
canonical_bytes()
```

This prepares a canonical representation of the WAV data for use by other project components such as hashing and start-location derivation.

The function clears the same low LSB bits that are used for steganography.

This means that the representation can remain consistent between the original cover audio and its stego version when only the selected LSB bits have been modified.

My audio module prepares these canonical bytes, while the shared cryptographic components perform the actual hashing where required.

---

## Running the Project

### Windows

I open PowerShell and navigate to the project directory:

```powershell
cd "C:\path\to\inf2005-P5-Group2"
```

I activate the Python virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

I then run the application using:

```powershell
python -m src
```

If the application provides a localhost URL, I open the displayed address in my browser.

---

### macOS

I navigate to the project directory:

```bash
cd /path/to/inf2005-P5-Group2
```

I activate the virtual environment:

```bash
source .venv/bin/activate
```

I then run:

```bash
python -m src
```

---

## Audio Encoding Procedure

To demonstrate my audio steganography implementation, I perform the following steps:

1. Start the application.
2. Select the audio steganography function.
3. Select a supported 16-bit PCM WAV file.
4. Enter or select the required payload.
5. Select an LSB depth.
6. Perform the encoding operation.
7. Save the generated stego WAV file.
8. Play the resulting WAV file to confirm that it is still valid audio.

The expected workflow is:

```text
Original WAV
    ↓
Payload
    ↓
Audio LSB Encoding
    ↓
Stego WAV
```

---

## Audio Decoding Procedure

To recover the payload:

1. Select the generated stego WAV file.
2. Select the required decoding options.
3. Use the correct parameters required by the application.
4. Run the extraction operation.
5. The program reads the embedded LSB values.
6. The payload bits are reconstructed into bytes.
7. The recovered payload is passed back to the application.

The expected workflow is:

```text
Stego WAV
    ↓
Audio LSB Extraction
    ↓
Recovered Payload Bytes
    ↓
Shared Payload / Verification Logic
```

---

## Expected Output

For successful encoding, I expect the program to generate a new WAV file containing the hidden payload.

Example:

```text
Input:
original_audio.wav

Output:
original_audio_stego.wav
```

The generated stego WAV should:

- remain a valid WAV file
- remain playable
- contain the embedded payload
- be successfully decoded using the correct parameters

For successful decoding, I expect the application to recover the embedded payload.

---

## Negative and Error Cases

I also handle a number of invalid cases.

### Unsupported Audio Type

Files such as:

```text
audio.mp3
audio.m4a
audio.flac
audio.aac
```

are rejected because my implementation currently only supports WAV.

---

### Unsupported WAV Encoding

Compressed WAV files are rejected.

The implementation requires:

```text
Uncompressed PCM WAV
```

---

### Unsupported Sample Width

My implementation currently requires:

```text
16-bit PCM
```

Other WAV sample widths are rejected.

---

### Invalid LSB Value

Only values from:

```text
1 to 8
```

are accepted.

Values outside this range cause an error.

---

### Payload Too Large

If the payload is larger than:

```text
8 MiB
```

the program rejects it.

The payload is also rejected if it is smaller than 8 MiB but still exceeds the capacity of the selected WAV file.

---

### Invalid Start Location

Negative start locations are rejected.

A start location outside the usable audio payload region will also prevent successful extraction.

---

### Audio Without Embedded Payload

If I attempt to decode a WAV file that does not contain the correct embedded payload header, the decoder reports that no valid audio payload was found.

---

### Incomplete Payload

If the audio does not contain enough samples to recover the complete stored payload, the decoder rejects the payload as incomplete.

---

## Testing

I tested my audio steganography implementation using both positive and negative cases.

My tests include:

- valid WAV embedding
- valid WAV extraction
- different LSB depths
- payload capacity checking
- invalid LSB values
- unsupported audio formats
- invalid WAV files
- invalid start locations
- WAV files without embedded payloads
- payloads that exceed capacity
- extraction of the original payload after embedding

The automated project test suite also includes audio steganography tests.

A successful test run should show the audio steganography tests passing together with the rest of the project test suite.

---

## Suggested Demo Files

For demonstration purposes, I include or prepare files such as:

```text
original_audio.wav
stego_audio.wav
tampered_audio.wav
```

These files allow me to demonstrate:

```text
Original audio
→
Encoding
→
Stego audio
→
Decoding
→
Recovered payload
```

I can also use a modified audio file to demonstrate negative or tampering-related behaviour.

---

## Demonstration Walkthrough

For my audio demonstration, I use the following sequence:

```text
1. Load original 16-bit PCM WAV
        ↓
2. Play original audio
        ↓
3. Select LSB depth
        ↓
4. Provide payload
        ↓
5. Encode payload
        ↓
6. Save stego WAV
        ↓
7. Play stego WAV
        ↓
8. Load stego WAV for decoding
        ↓
9. Extract payload
        ↓
10. Show recovered payload
```

During the demonstration, I explain that the payload is stored by modifying the least significant bits of the PCM samples.

Because the most significant portions of the samples remain unchanged, the generated audio can remain usable and playable after embedding.

---

## Main Audio Steganography Functions

The main functions I use in my implementation are:

### `_validate_lsb()`

Validates that the selected LSB depth is between 1 and 8.

### `_validate_start()`

Validates the start location.

### `_bytes_to_bits()`

Converts payload bytes into individual bits before embedding.

### `_bits_to_bytes()`

Reconstructs extracted bits into bytes.

### `_set_sample_lsb()`

Performs the actual modification of the selected least significant bits of a PCM sample.

### `_read_bits()`

Reads the selected least significant bits from PCM samples.

### `_read_wav()`

Reads and validates the WAV file.

### `_write_wav()`

Writes the modified PCM samples back into WAV format.

### `sample_count()`

Returns the number of PCM samples available for embedding.

### `canonical_bytes()`

Produces a canonical representation of the audio for shared hashing and start-location operations.

### `capacity()`

Calculates how much payload data can be stored.

### `embed()`

Performs the complete audio payload embedding operation.

### `extract()`

Performs the complete audio payload extraction operation.

---

## My Contribution

My main contribution to the project is the Audio Steganography component.

I implemented and worked on:

- WAV audio support
- 16-bit PCM validation
- LSB-based audio steganography
- configurable LSB depth from 1 to 8
- audio payload embedding
- audio payload extraction
- payload capacity calculation
- payload header handling
- audio start-location support
- audio canonical-byte generation for shared components
- audio validation and error handling
- positive audio testing
- negative audio testing
- audio steganography integration with the overall application
- audio demonstration and documentation

The shared parts of the project handle areas such as payload processing, cryptographic verification and other application-level functionality.

My audio component is responsible for taking the payload bytes supplied by the application, hiding them inside WAV PCM samples, and later recovering those payload bytes from the stego audio.

---

## Summary

My Audio Steganography implementation allows payload data to be hidden inside uncompressed 16-bit PCM WAV files using LSB steganography.

The encoder converts the payload into bits and stores them inside selected least significant bits of PCM samples.

The decoder performs the reverse process by reading those bits and reconstructing the original payload bytes.

My implementation supports LSB depths from 1 to 8, configurable start locations, audio capacity validation and a maximum payload size of 8 MiB.

The resulting stego file remains a valid WAV file and can be passed back into the application for payload extraction and verification.
