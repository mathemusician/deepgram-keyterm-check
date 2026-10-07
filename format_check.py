"""Do the keyterm formats the docs call invalid actually fail? Test each one on the same audio.

Usage:
    python format_check.py --reference samples/support_call.txt --keyterms samples/keyterms.txt --snr 5
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from check import add_noise, read_terms
from dg import Deepgram, transcript_of
from scoring import term_hits, wer

CONTROL = ["Salesforce", "Snowflake", "Datadog", "HubSpot", "Okta", "Stripe"]


def main() -> None:
    load_dotenv(".env")
    load_dotenv("env.txt")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", required=True)
    ap.add_argument("--keyterms", required=True)
    ap.add_argument("--snr", type=float, default=5.0)
    ap.add_argument("--out", default="results/format_check.md")
    args = ap.parse_args()

    dg = Deepgram()
    ref = Path(args.reference).read_text().strip()
    terms = read_terms(args.keyterms)
    audio = add_noise(dg.speak(ref), args.snr)

    variants = {
        "No keyterms": [],
        "Unrelated keyterms (control)": CONTROL,
        "Documented: one parameter per term": terms,
        "Comma-joined into one string": [", ".join(terms)],
        "Semicolon-joined into one string": ["; ".join(terms)],
        "Legacy weights (term:2)": [f"{t}:2" for t in terms],
    }
    lines = [f"# Keyterm format check (Aura TTS, 8 kHz, {args.snr:g} dB SNR)\n",
             "| Format | Word error rate | Terms heard correctly |", "|---|---|---|"]
    for name, kt in variants.items():
        tx = transcript_of(dg.listen(audio, kt))
        hits = sum(term_hits(t, ref, tx)[0] for t in terms)
        lines.append(f"| {name} | {wer(ref, tx):.1%} | {hits}/{len(terms)} |")
        print(lines[-1])
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
