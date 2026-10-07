# deepgram-keyterm-check

A self-serve kit for one of the most common speech-to-text questions:

> "Your transcripts keep getting our product names wrong. Will keyterm prompting fix it, and are we using it right?"

It runs the same audio through [Deepgram](https://deepgram.com) Nova-3 with and without your keyterms, scores the results against what was actually said, and lints your keyterm list. Any team can run it on their own recordings in a few minutes, without filing a ticket.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "DEEPGRAM_API_KEY=your_key" > .env      # free credit at console.deepgram.com
pytest -q                                     # offline tests, no key needed

# Your own audio + a transcript of what was really said + your terms, one per line
python check.py --audio call.wav --reference call.txt --keyterms terms.txt

# No recording handy? Synthesize a phone-quality call with Aura and add line noise
python check.py --synthesize --reference samples/support_call.txt --keyterms samples/keyterms.txt --snr 5

# Just check a keyterm list
python check.py --lint-only --keyterms terms.txt
```

The report (`results/report.md`) shows word error rate and, for each term, how many times it was heard correctly out of how many times it was said.

## What I found

Sample: a made-up support call full of names a model could miss (Gainsight, ChurnZero, Vitally, Adaptalytics, Dayforce, tretinoin, semaglutide, and others), synthesized with Aura at 8 kHz, the same bandwidth as a phone line, then mixed with white noise.

### 1. Keyterms help, and they help more as audio gets worse

| Audio | Terms heard, no keyterms | Terms heard, with keyterms | Word error rate, no keyterms → with |
|---|---|---|---|
| Clean 8 kHz | 10/12 | 12/12 | 3.4% → 0.0% |
| Noise, 10 dB SNR | 9/12 | 12/12 | 5.5% → 2.1% |
| Heavy noise, 5 dB SNR | 6/12 | 11/12 | 9.7% → 4.8% |

Without keyterms, "ChurnZero" came out as "churn zero" and "Vitally" as "Vitaly" even on clean audio. Under heavy noise, Gainsight and Adaptalytics dropped out too. With keyterms, every name came through except one in the noisiest run. Full transcripts are in `results/`.

### 2. The keyterm formats the docs call invalid worked just as well

The [keyterm docs](https://developers.deepgram.com/docs/keyterm) say comma-separated lists, semicolon-separated lists, and legacy weights (`term:0.15`) are accepted without an error but "silently boost nothing." I tested each one on the same noisy audio (`format_check.py`, 5 dB SNR):

| Format | Word error rate | Terms heard |
|---|---|---|
| No keyterms | 6.9% | 9/12 |
| Unrelated keyterms (control) | 7.6% | 8/12 |
| **Documented: one parameter per term** | **3.4%** | **12/12** |
| Comma-joined into one string | 3.4% | 12/12 |
| Semicolon-joined into one string | 3.4% | 12/12 |
| Legacy weights (`term:2`) | 3.4% | 12/12 |

The control rules out a placebo: unrelated keyterms did nothing, so the boost comes from the right terms being present. But on Nova-3 pre-recorded audio, all four formats boosted identically in every run (comma-joined in four runs, semicolon and weights in two each).

**Why it matters:** a customer who reads the docs, sees their comma-separated setup "should" be broken, and "fixes" it will see no change, then wonder if keyterms work at all. Or support tells them to reformat, nothing improves, and the ticket bounces. I would raise this with Docs and Product: either the docs are stale, or the failure only shows up in cases I did not test (streaming, Flux, long lists near the 500-token limit, or terms whose meaning changes when glued together). Either answer is worth one line in the docs.

The linter still flags these formats, since the documented one is the safe bet, but it no longer claims they fail.

### Caveats

- Synthetic speech is cleaner and more consistent than real callers, so absolute error rates here are optimistic. The *comparison* between runs is the useful part, and `check.py --audio` exists so teams can rerun it on real calls.
- Aura returns slightly different audio on each request, so exact counts move between runs (the baseline ranged from 6/12 to 9/12 at 5 dB). The direction never changed.
- One script, one voice, 12 terms. Enough to answer "is this worth turning on?", not a benchmark.

## Files

```
check.py          Baseline vs keyterms vs comma-joined on your audio, with a report
format_check.py   Every keyterm format the docs mention, plus a control
dg.py             Small Deepgram REST client (listen + speak) and the keyterm linter
scoring.py        Word error rate and per-term recall, no dependencies
samples/          Example call script and keyterm list
results/          Reports from the runs above
tests/            Offline tests: linter, scoring, request format, retries
```
