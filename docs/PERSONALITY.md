# NAO's personality: the end-of-dance comment

NAO is a confident, slightly arrogant robot dance coach. After each dance it
says the score, pauses, then delivers **one** short sarcastic line about the
**observed dance performance**. Everything is English, offline and local
(no Internet, no AI service): `evaluation/roast_library.py` holds the lines,
`evaluation/nao_personality.py` chooses one from the session report.

```
"63 points!"                                         <- score announcement
(0.7 s pause)
"Respectable. Not legendary, but respectable!"       <- roast
"You got 7 of 10 moves right."                       <- only in Long mode: one measured fact
```

---

## 1. When NAO speaks

At the end of a **completed** dance, in this order:

1. the music stops (`audio_stop`), the movement finishes and NAO returns to
   StandInit; the score is frozen;
2. the Results screen opens and the report is saved **with** the comment
   text (`nao_comment` in the JSON, shown in History and in CSV exports);
3. NAO says the score, then the roast (5–15 s in total).

Rules enforced by `app/controller.py` (and tested in tests/test_end_of_dance.py):

- never while the music plays, never two sentences at once;
- one announcement per game (no repeats);
- **Skip comment** (Results screen, main menu, or key `s` in the console)
  cuts the sentence and drops the rest;
- **Rest** waits for the end of the sentence before NAO sits down; closing
  the app skips the comment and waits for the sentence to stop;
- starting a new dance cuts the comment;
- after a **fall**: no comment at all;
- **interrupted** dance (Stop): a separate, short comment
  ("55 points, but you stopped early." + "Leaving already? I was just getting
  warmed up!"), unless `ANNOUNCE_INTERRUPTED = False`;
- **not enough tracking** (unevaluable): no score, a fair camera comment
  ("No score this time." + "I couldn't see enough of your moves to give you a
  fair score. Were you dancing or hiding from the camera?");
- no camera / no detection (demo mode): no score, no comment.

---

## 2. How the line is chosen

1. **Special cases**: interrupted, unevaluable.
2. **Score band** (`ROAST_BANDS` in config.py):

   | Score | Band | Tone |
   |---|---|---|
   | 0–30 | poor | strong roast |
   | 31–50 | weak | sarcastic |
   | 51–70 | average | mild sarcasm + encouragement |
   | 71–89 | good | compliment + tease |
   | 90–100 | excellent | jealous robot |

3. **Diagnostics** – only from measurements present in the report, never invented:

   | Diagnostic | Measured condition |
   |---|---|
   | barely_moves | activity factor < 0.6 |
   | out_of_frame | tracked < 75 % of the time |
   | late / early | average delay ≥ 0.7 s / ≤ −0.25 s (only if well tracked) |
   | arms_wrong | both arm scores < 55 while moving enough |
   | arms_asymmetric | left/right arm scores differ by ≥ 20 |
   | rigid | elbows ≥ 20° straighter than NAO's on average |
   | great_sync | delay within 0.35 s and score ≥ 75 |

   For poor/weak/average bands the first matching negative diagnostic gives
   a targeted line ("I've seen elevators move faster than you!" when late).
   For good/excellent bands a positive diagnostic is used half of the time.
   The current choreographies score the arms only, so **no line mentions legs**.
4. **Intensity**: Friendly, Sarcastic (default) or Savage.
5. **No repetition**: the last 15 lines are remembered
   (`results\roast_history.json`, kept across restarts) and avoided while
   other lines are available.
6. Randomness comes from an injectable `random.Random`: tests use a fixed seed.

**Wording rules** (checked by tests/test_personality.py): about the dance
only – never the player's appearance, body, identity, age, abilities or
personal characteristics; no insults; plain ASCII English for the TTS;
at most 26 words per line.

The library has **134 unique lines** (bands, diagnostics and special cases,
each in the three intensities) plus kind neutral lines used when sarcasm is off.

---

## 3. Settings

In the game window, *Settings > NAO's voice and personality* (saved in
`results\settings.json`), or in `config.py`:

| Setting | Default | Effect |
|---|---|---|
| `NAO_SPEAKS` | `True` | NAO says the comment; `False` = shown on screen only |
| `ROAST_ENABLED` | `True` | `False` = kind neutral comments ("Nice dancing! You're getting better.") |
| `ROAST_INTENSITY` | `"sarcastic"` | `"friendly"`, `"sarcastic"` or `"savage"` |
| `COMMENTARY_LENGTH` | `"short"` | `"long"` adds one measured fact ("You were about 0.8 seconds behind me.") |
| `ROAST_PAUSE` | `0.7` | seconds of silence after the score |
| `ROAST_BANDS` | see above | score thresholds of the bands |
| `ANNOUNCE_INTERRUPTED` | `True` | comment also when the player presses Stop |
| `VOICE_FEEDBACK` | `False` | rare "Great job!" *during* the dance (off: the music is loud) |

NAO's voice language is set by the bridge (`TTS_LANGUAGE = "English"`); the
English voice must be installed on the robot (it is on standard NAO V6).

---

## 4. Adding lines

Edit `evaluation/roast_library.py`: `ROASTS[category][intensity]` is a list
of strings. Keep them short (3–8 s when spoken), about the dance, in English,
then run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_personality -v
```

Preview what NAO would say for a saved game:

```powershell
.\.venv\Scripts\python.exe -c "import json,glob,config; from evaluation.nao_personality import NaoPersonality as P; r=json.load(open(sorted(glob.glob('results/sessions/*.json'))[-1], encoding='utf-8')); print(P(config).comment(r)['lines'])"
```
