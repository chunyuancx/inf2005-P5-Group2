import wave

path = "samples/audio/stego.wav"

with wave.open(path, "rb") as wav:
    print("Channels:", wav.getnchannels())
    print("Sample width:", wav.getsampwidth(), "bytes")
    print("Sample rate:", wav.getframerate(), "Hz")
    print("Frames:", wav.getnframes())
    print("Compression:", wav.getcomptype())
    print("Compression name:", wav.getcompname())
    print("Duration:", wav.getnframes() / wav.getframerate(), "seconds")