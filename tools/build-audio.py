"""Préparer la page statique et générer les capsules de révision."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RATE = 22050
VOICE = "fr_FR-siwis-medium"

def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], check=True)

def duration(path):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], text=True))

def build(output):
    from piper import PiperVoice
    import wave

    episodes = json.loads(Path("audio/episodes.json").read_text(encoding="utf-8"))
    audio = output / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    shutil.copyfile("index.html", output / "index.html")
    voice = PiperVoice.load(str(Path(sys.argv[2]) / (VOICE + ".onnx")))

    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        raw = work / "voice.wav"
        files = []
        position = 0.0
        for episode in episodes:
            episode["start"] = round(position, 2)
            for role, text in episode["lines"] + [["Pause", 1.3]]:
                segment = work / f"{len(files):03}.wav"
                if role == "Pause":
                    ffmpeg("-f", "lavfi", "-i", f"anullsrc=r={RATE}:cl=mono", "-t", text, "-c:a", "pcm_s16le", segment)
                else:
                    with wave.open(str(raw), "wb") as wav:
                        voice.synthesize_wav(text, wav)
                    if duration(raw) < 0.3:
                        raise ValueError(f"Segment vide : {episode['id']}")
                    # Deux personnages, à partir de la même voix de synthèse.
                    filters = "apad=pad_dur=0.28"
                    if role == "Guide":
                        filters = f"asetrate=19200,aresample={RATE},atempo=1.1484,{filters}"
                    ffmpeg("-i", raw, "-af", filters, "-ar", RATE, "-ac", 1, "-c:a", "pcm_s16le", segment)
                position += duration(segment)
                files.append(segment)
            episode["end"] = round(position, 2)

        concat = work / "playlist.txt"
        concat.write_text("".join(f"file '{p.name}'\n" for p in files), encoding="utf-8")
        track = audio / "revision-mooi.mp3"
        ffmpeg("-f", "concat", "-safe", "1", "-i", concat, "-ar", RATE, "-ac", 1,
               "-c:a", "libmp3lame", "-b:a", "48k", "-metadata", "title=MOOI · Réviser aux écouteurs", track)
        if abs(duration(track) - position) > 0.5 or position < 120:
            raise ValueError("Durée de la piste incohérente")
        for episode in episodes:
            print(f"{episode['id']}: {episode['start']:.2f} → {episode['end']:.2f} s")
        (audio / "chapitres.js").write_text(
            "window.mooiAudioOffsets = " + json.dumps({episode["id"]: episode["start"] for episode in episodes}) + ";\n",
            encoding="utf-8",
        )

if __name__ == "__main__":
    build(Path(sys.argv[1]))
