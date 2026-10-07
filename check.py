"""Does keyterm prompting fix how Deepgram hears YOUR terms? Measure it on your own audio.

Runs the same audio three ways and reports word error rate and per-term recall:
  1. no keyterms
  2. keyterms passed correctly (one repeated parameter per term)
  3. keyterms joined into one comma-separated string, a format the docs call invalid
     (the API accepts it without an error)

Usage:
    python check.py --audio call.wav --reference call.txt --keyterms terms.txt
    python check.py --synthesize --reference samples/support_call.txt --keyterms samples/keyterms.txt
    python check.py --lint-only --keyterms terms.txt
"""

from __future__ import annotations

import argparse
import io
import sys
import wave
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from dg import Deepgram, lint_keyterms, transcript_of
from scoring import term_hits, wer


def read_terms(path: str) -> list[str]:
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def add_noise(wav_bytes: bytes, snr_db: float, seed: int = 7) -> bytes:
    """Mix in white noise at a target signal-to-noise ratio, like a noisy phone line."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        params = w.getparams()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
    signal_power = np.mean(samples**2)
    noise = np.random.default_rng(seed).normal(0, np.sqrt(signal_power / 10 ** (snr_db / 10)), samples.shape)
    noisy = np.clip(samples + noise, -32768, 32767).astype(np.int16)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(noisy.tobytes())
    return out.getvalue()


def main() -> int:
    load_dotenv(".env")
    load_dotenv("env.txt")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keyterms", required=True, help="one term per line")
    ap.add_argument("--reference", help="what was actually said (plain text)")
    ap.add_argument("--audio", help="your recording (wav, mp3, m4a...)")
    ap.add_argument("--synthesize", action="store_true", help="generate 8 kHz phone-quality audio from --reference with Aura")
    ap.add_argument("--snr", type=float, default=None, help="add white noise at this SNR in dB, e.g. 10")
    ap.add_argument("--model", default="nova-3")
    ap.add_argument("--lint-only", action="store_true")
    ap.add_argument("--out", default="results/report.md")
    args = ap.parse_args()

    terms = read_terms(args.keyterms)
    problems = lint_keyterms(terms)
    print(f"Lint: {len(terms)} keyterms, {len(problems)} problem(s)")
    for p in problems:
        print(f"  - {p}")
    if args.lint_only:
        return 1 if problems else 0
    if not args.reference or not (args.audio or args.synthesize):
        ap.error("need --reference and either --audio or --synthesize")

    reference = Path(args.reference).read_text().strip()
    dg = Deepgram()
    if args.synthesize:
        audio, mimetype = dg.speak(reference), "audio/wav"
        Path("results").mkdir(exist_ok=True)
        Path("results/synthesized.wav").write_bytes(audio)
    else:
        audio = Path(args.audio).read_bytes()
        mimetype = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}.get(Path(args.audio).suffix.lstrip("."), "audio/wav")
    if args.snr is not None:
        audio = add_noise(audio, args.snr)

    runs = {
        "No keyterms": [],
        "Keyterms, correct": terms,
        "Keyterms, comma-joined": [", ".join(terms)],
    }
    transcripts = {name: transcript_of(dg.listen(audio, kt, args.model, mimetype)) for name, kt in runs.items()}

    names = list(runs)
    lines = [f"# Keyterm check: {args.model}\n",
             f"Audio: {'Aura TTS, 8 kHz' if args.synthesize else args.audio}"
             f"{f', white noise at {args.snr:g} dB SNR' if args.snr is not None else ''}\n",
             "| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines.append("| Word error rate | " + " | ".join(f"{wer(reference, transcripts[n]):.1%}" for n in names) + " |")
    total = {n: [0, 0] for n in names}
    for t in terms:
        cells = []
        for n in names:
            hit, said = term_hits(t, reference, transcripts[n])
            total[n][0] += hit
            total[n][1] += said
            cells.append(f"{hit}/{said}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines.append("| **All terms** | " + " | ".join(f"**{h}/{s}**" for h, s in total.values()) + " |")
    lines.append("\n## Transcripts\n")
    for n in names:
        lines.append(f"**{n}:** {transcripts[n]}\n")

    report = "\n".join(lines) + "\n"
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(report)
    print("\n".join(lines[:5 + len(terms) + 2]))
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
