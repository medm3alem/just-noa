# The dances: moves, timing and how they are built

Five choreographies ship with Just Nao. Four are **composed** by
`tools/compose_choreographies.py` from named poses placed on a rhythmic grid
(Macarena, Mekassarat, NAO Party, Warm-up); the fifth (Sync calibration) is
deliberately kept simple and precise.

> **NAO fell with the previous warm-up (v4).** Since then every dance is also
> checked for **balance** (section 0). The dances below were rebuilt to stay
> far from what made NAO fall, but they are **not yet validated on the
> physical robot**. Follow **docs/DANCE_VALIDATION.md** before showing them.

| Dance | Music | Tempo | Length | Moves scored | Peak joint speed | Balance: dynamic part |
|---|---|---|---|---|---|---|
| Macarena | NAO's speakers, `macarena_extrait.wav` | 103.15 BPM (measured) | 66 s, 7 × 16 beats | 56 | ≤ 46 % | 5.6 mm |
| Mekassarat (Ahmed Saad) | NAO's speakers, `mekassarat_extrait.wav` | 109.98 BPM (measured) | 48.5 s, 89 beats | 11 | ≤ 47 % | 5.0 mm |
| NAO Party | none (speech + LEDs) | 112 BPM grid | 41.6 s | 8 | ≤ 48 % | 5.7 mm |
| Warm-up (arms) | none (spoken cues) | 96 BPM grid | 29.7 s | 5 | ≤ 42 % | 4.2 mm |
| Sync calibration | `click.wav` | 90 BPM | 13.7 s | – | – | 2.7 mm |
| *warm-up v4, made NAO fall* | | | | | | *13.7 mm* |

All dances use 14 joints at most (head yaw/pitch, both arms with wrists and
hands), never the legs. Pictures of every pose (front and side view,
collision volumes, palm direction) and joint curves with the musical beats:
`docs/img/*_poses.png`, `docs/img/*_curves.png` (`tools/render_dance.py`).

---

## 0. Balance: what made NAO fall, and the new rule

`choreography/kinematics.py` now estimates where NAO's weight presses on the
floor (the **ZMP**) while the arms and head move, from the masses of NAO's
segments. Two parts:

- **static**: holding the arms in front moves the centre of mass forward
  (both arms straight in front: ~13 mm). NAO copes with that;
- **dynamic**: when arms **accelerate**, they push the body the other way. This
  is what made NAO fall: the v4 warm-up raised and lowered **both arms
  together in front** (forward, up, down) every ~1.3 s → 13.7 mm of dynamic
  shift. The v4 Macarena and NAO Party were even worse (19 mm), and are
  replaced.

| (mm, model estimate) | dynamic | back | forward | side |
|---|---|---|---|---|
| warm-up v4 — **NAO fell** | **13.7** | 16.4 | 22.1 | 3.2 |
| Macarena v4 / NAO Party v4 (replaced) | 19.2 / 18.8 | 21.7 / 18.9 | 28.5 / 26.5 | 12.3 / 14.7 |
| Med's first test (ran fine on NAO) | 1.0 | – | 10.0 | 2.4 |
| slow warm-up of 2 Nov (no fall, but too slow) | 0.4 | 3.1 | 4.5 | 4.2 |
| **new dances** | **4.2 – 5.7** | 9 – 13 | 12 – 17 | 3 – 11 |

The rule now checked before every dance (`BALANCE_LIMITS`): dynamic part
warning above 6 mm, **refused above 9 mm**; total backward 14 / 20 mm, forward
18 / 25 mm, sideways 16 / 24 mm. The v4 warm-up would now be refused (a test
checks it). These thresholds come from **one** observed fall and a simplified
model: they compare dances, they do not guarantee stability.

How the new dances stay lively without big pushes:

1. **Never both arms together forward / backward / up quickly.** Two-arm
   gestures go **sideways** (frontal plane: `ShoulderRoll` with the arm down),
   symmetric, so the left and right pushes cancel.
2. Big up/down gestures are done by **one arm at a time**, over 2 beats or
   more, or **through the side** (arms up via the sides, never via the front).
3. Forearm and hand gestures (curls, waves, twirls, punches) are light: they
   can be fast.
4. Each gesture lasts at least ~0.8–0.9 beat (smooth acceleration).

Careful: "one arm up while the other goes down" does **not** cancel when both
arms pass in front at the same time (their pushes add up): such swings go
through the side or are spread over more beats.

---

## 1. Macarena

### 1.1 What the music analysis found (`tools/analyze_audio.py`)

| | Value |
|---|---|
| Tempo | **103.15 BPM** (one beat = 0.582 s), constant over the excerpt (fit residual 23 ms) |
| First beat | **0.235 s** after the start of `macarena_extrait.wav` |
| Beat reference | the **kick drum** (four-on-the-floor): kick energy 2.3 × higher on the beat than on the off-beat |
| Bars | first beat of the bar = beat n° 1 (0.817 s) |
| Phrases | 16-beat phrases from beat n° 1 → **7 full Macarena cycles** (beats 1–112), the last one ends at 66.0 s |
| Phrase similarity | A B C A A D C (harmonic similarity; energy drops by ~3 dB in the last two phrases) |

Important detail: a general-purpose beat tracker (librosa) locks onto the
off-beat open hi-hat and puts the beats **0.29 s too early**. The previous
Macarena was timed on such a grid. The analysis tool deliberately uses the
kick drum. Check by ear: `tools/analyze_audio.py ... --click check.wav`
writes the music with a click on every beat (higher click on the first beat
of each bar).

The result is stored in `choreography/library/macarena/beats.json`; the
composer and the tests use it.

### 1.2 One cycle (16 beats, about 9.3 s)

A pose is **reached on the beat**; the gesture happens during the time before
it. Each arm keeps its pose while the other one moves (no return to a neutral
posture between gestures). Since 2 Nov every gesture lasts at least 0.9 beat
(softer accelerations, for balance).

| Beat | Right arm | Left arm | Head | Classic Macarena | NAO adaptation |
|---|---|---|---|---|---|
| 1 | straight in front, palm **down** | starts rising slowly (from the "Ay!") | | right arm out | arms 12° apart so the camera sees them |
| 2 | holds | straight in front, palm down | | left arm out | the left arm takes ~1.8 beats to come up: no jerk right after the "Ay!" |
| 3 | palm turns **up** | holds | | right palm up | forearm + wrist rotation (~180°) |
| 4 | holds | palm up | | left palm up | |
| 5 | hand to the **left** shoulder, crossing **high** | holds | | right hand on left shoulder | NAO's hand reaches the front of the opposite chest |
| 6 | already leaving towards the head | hand to the right shoulder, crossing **below** | | left hand on right shoulder | the two arms are no longer crossed together (see "trade-offs") |
| 7 | hand **beside/behind the head** | leaves the shoulder | | right hand behind head | passes in front of the face through a waypoint, without stopping |
| 8 | starts going down | hand beside the head | | left hand behind head | |
| 9 | hand on the **side of the hip** | starts going down | | right hand on left/right front hip | same-side hip (NAO's arms cannot cross that low); longest gesture of the dance, ≤ 47 % of motor speed |
| 10 | holds | hand on the side of the hip | | left hand on hip | |
| 11 | hand **behind** the hip | holds | | right hand on back pocket | shoulder 100° back, elbow less bent than before |
| 12 | holds | hand behind the hip | | left hand on back pocket | |
| 13 | elbow pumps out | elbow pumps | sways right | "Dale a tu cuerpo..." hip roll | NAO's pelvis does not move: elbows and head carry the groove |
| 14 | starts rising slowly towards the sky | elbow pumps | sways left | hip roll | |
| 15 | rising | elbow pumps | faces front | hip roll | |
| 16 | **fist to the sky** | **arm open to the side**, eyes flash yellow | looks up | jump + quarter turn ("Ay!") | no jump, no turn; one arm up, one out (see below) |

Then the cycle starts again. Hands open/close with the gesture (open in
front and on "Ay!", half-closed on the shoulders, closed on the hips).

**Trade-offs made for balance (2 Nov).** The v4 Macarena pushed NAO's weight
around more than the warm-up that made NAO fall (dynamic part 19 mm against
13.7 mm). The moves are the same, the biggest pushes were removed:

- "Ay!" was **both arms up in a V**, raised in less than a beat through the
  front: the worst push of the dance. Now the right fist goes up slowly from
  beat 13.5 and the left arm opens **sideways** on 16.
- The right hand leaves the crossed position about half a beat before 6
  (the moment where both arms were crossed together is gone) and leaves the
  head earlier: the head → hip gesture is spread over 1.6 beats.
- The "groove" head nods pause during the head → hip gesture.

Measured on the model: dynamic part 19.2 → **5.6 mm**, backward 21.7 →
13.3 mm, forward 28.5 → 17.0 mm.

### 1.3 Variations between cycles (same moves, different details)

| Cycle | Beats | Head | Amplitude |
|---|---|---|---|
| 1 | 1–16 | looks straight, small nod at the hips | basic, most readable |
| 2 | 17–32 | **follows the hand** that just moved | basic |
| 3 | 33–48 | **nods on every beat** | arms 3° higher, wider "Ay!" |
| 4 | 49–64 | follows the hands | bigger |
| 5 | 65–80 | nods on every beat | bigger |
| 6 | 81–96 | straight (the music gets quieter) | basic |
| 7 | 97–112 | follows the hands, **final "Ay!" held to the end** | bigger |

Eyes: blue / pink flash on the first beat of each cycle, yellow on every "Ay!".
Two short remarks in the middle of the dance (Med's additions, kept): cycle 3
"Come on, my grandma has more rhythm!", cycle 6 "Are you dancing, or
buffering?".

### 1.4 What the player is scored on

- Only the **upper arms and forearms** directions (MediaPipe can measure
  them). Wrist rotation and hand opening are **never scored**: palms down and
  palms up give the same target pose (difference < 1° for the upper arm,
  < 8° for the forearm, far below the 25° no-penalty tolerance).
- The main gestures (arms out, crossed, head, hips, "Ay!") differ by more
  than 25° on at least one arm: they are distinct for the camera.
- The report lists 56 named moves (8 per cycle). The tips name the moves the
  player missed most often, e.g. "Moves to practice: Hands behind head
  (3 times), Palms up (2 times)."
- Simulated players: a good imitation scores ≥ 85, standing still < 35.

---

## 2. Mekassarat (Ahmed Saad), excerpt 0:18 → 1:06

Egyptian pop, Ahmed Saad – *Mekassarat* (Official Music Video). Med chose
the part from 0:18 to 1:06.

### 2.1 The excerpt and what the analysis found

| | Value |
|---|---|
| File | `choreography/library/mekassarat/mekassarat_extrait.wav` (22 050 Hz stereo, 48.45 s), on NAO: `/home/nao/music/mekassarat_extrait.wav` |
| Cut | from **0:17.55** of the track (half a beat before 0:18, exactly on the start of a 16-beat phrase) to **1:06.00**, 0.3 s fade-out |
| Tempo | **109.98 BPM** (one beat = 0.546 s), constant (fit residual 18 ms) |
| First beat | 0.064 s after the start of the WAV |
| Beat reference | kick drum (1.7 × more energy on the beat than on the off-beat) |
| Bars / phrases | first beat of the WAV = first beat of a bar and of a phrase: set with `--bar-phase 0 --phrase-phase 0`, because the automatic guess was ambiguous on this song; checked with the click track and the energy jumps (kick drum comes in at beat 16, louder groove at 32, loudest part at 80) |
| Structure | 89 beats: 5 phrases of 16 beats + 9-beat finale (A A B B B C) |

```powershell
.\.venv\Scripts\python.exe tools\analyze_audio.py choreography\library\mekassarat\mekassarat_extrait.wav --bpm-min 80 --bpm-max 160 --bar-phase 0 --phrase-phase 0 --click check.wav
```

### 2.2 The routine

j = beat of the excerpt (0 = first beat, 0.06 s).

| Beats j | Music | Move | Description |
|---|---|---|---|
| 0–7 | intro, little percussion | **Hand twirls** | hands in front of the chest, wrists rolling in turn on every beat (oriental "twirl"), head nods |
| 8–15 | | **Hand twirls up high** | same, hands higher |
| 16–23 | the kick drum comes in | **Wings** | hands at the chest, elbows open and close on every beat |
| 24–31 | | **Point to the sky** | one finger to the sky, the other hand at the chest, swapping every 2 beats |
| 32–47 | louder groove ("Yalla! Show me your moves!") | **Snake arms** | arms open to the sides, waving up/down in opposition on every beat; head sways |
| 48–55 | | **Wave up high** | left hand on the hip, right hand waves above the head |
| 56–63 | | **Wave with the other hand** | right hand back to the hip, then the left hand waves |
| 64–79 | ("Even my circuits are dancing!") | **Disco** | one finger to the sky, the other arm down across the body, swapping every 2 beats, hands sparkle |
| 80–87 | finale, loudest part | **Big finish** | fast wings, white flashes in the eyes |
| 88 | last hit | **Ta-da** | both arms open to the sides, held, yellow eyes |

Eyes change colour at every phrase. 11 named moves are scored (the report
names the ones to practise). Model: dynamic part 5.0 mm, peak speed 47 %
(hands), 22 mm minimum clearance.

---

## 3. NAO Party (no music, 112 BPM)

Med's first Choregraphe test, rebuilt as a party routine, and rebuilt again
on 2 Nov for balance (the v4 version had a dynamic part of 18.8 mm, more than
the warm-up that made NAO fall). NAO talks ("Hey everybody! Are you ready to
party? Let's go!") before the first beat, then 4 phrases of 16 beats, each
announced by a short line:

| Beats | Move | Description |
|---|---|---|
| 1–8 | **Wave** | left hand waves, then the right hand |
| 9–16 | **Wave with both hands** | both hands wave, then the arms open to the sides |
| 17–28 | **Punches** ("Punch! Punch!") | guard in front of the chest, **one** punch per beat, left and right alternate (one arm goes out while the other comes back: the pushes cancel) |
| 29–32 | **Guard** | |
| 33–48 | **Disco** ("Disco time!") | one finger to the sky, the other arm down across the body, swapping every 2 beats; hands open on the off-beats |
| 49–56 | **Wings** ("Big finish!") | hands at the chest, elbows open and close on every beat |
| 57–64 | **Snake arms and big finish** | arms open to the sides, waving in opposition, then both arms open sideways ("ta-da"), held, "Thank you!" |

What changed for balance: no more "both arms up in a V" through the front,
no more elbow curls with both arms together in front, punches one at a time
on every beat instead of every 2 beats with both arms moving, the big finish
opens sideways. The head turns left/right every two beats and stays straight
during the punches. Eye colour changes every bar. Two remarks (Med's
additions, kept): "Nice moves! Keep up with me!" and "Those arms look a
little rusty!".

## 4. Warm-up (arms) (no music, 96 BPM)

History: the v4 warm-up (92 BPM, both arms together forward, up, down, every
~1.3 s) **made NAO fall, several times**. Med then made a cautious version
(`docs/WARMUP_SAFE.md`): one arm at a time, never above the shoulders, each
gesture rising over 4 beats and coming down over 4 beats. NAO no longer fell, but it was much too slow to be fun, and too
small for the camera to tell a player who copies from one who stands still.

The new version (2 Nov) keeps a lively rhythm (one pose every 2 beats =
1.25 s, then one gesture per beat for the elbows) and follows the balance
rules of section 0:

| Beats | Move (spoken cue) | Description |
|---|---|---|
| 1–8 | **Arms out to the sides** ("Open your arms to the sides!") | both arms rise **sideways** to shoulder height, down, again |
| 9–16 | **One arm forward, then the other** ("One arm forward, then the other!") | one arm goes forward while the other comes down: pushes in opposition; the head looks at the arm in front |
| 17–24 | **Arms up through the sides** ("Now reach up, through the sides!") | arms go up **by the sides** in one continuous gesture, then back down by the sides |
| 25–32 | **Elbow curls** ("Bend your elbows, one after the other!") | arms down, elbows bend one after the other, on every beat |
| 33–40 | **Open and close** ("Open your chest!") | forearms in front of the chest, then opened to the sides (chest stretch) |
| 42–44 | "Great warm-up!" | arms out halfway, then down |

Remarks kept from Med's version: "Easy there, I am not a helicopter!" (beat
21) and "Looking good! My grandma approves!" (beat 37). Same length as
before (29.7 s).

| | v4 (fell) | Med's cautious version | **new** |
|---|---|---|---|
| gestures | both arms together, forward / up / down | one arm at a time, very slow | sideways (symmetric) or in opposition |
| peak motor speed (model) | 48 % | ≤ 10 % | 42 % |
| balance, dynamic part (model) | **13.7 mm** | 0.4 mm | 4.2 mm |
| still player / good player (simulated score) | – | not distinguishable | 19 / 100 |

**Different from Med's cautious version:** in beats 17–24 the arms go
**above the head** (through the sides, never through the front). The model
says this is a sideways, symmetric gesture that balances itself, but it
breaks the "never above the shoulders" rule of `WARMUP_SAFE.md`: test this
block on its own first (docs/DANCE_VALIDATION.md). To remove it, replace the
block `(17, "Arms up through the sides", ...)` in `warmup()` of
`tools/compose_choreographies.py` by a copy of the first block (arms out to
the sides) and regenerate with
`python tools/compose_choreographies.py echauffement`.

At reduced speed the dynamic part drops roughly with the square of the
speed: `--speed 0.75` → 2.6 mm, `--speed 0.5` → 1.2 mm (the level of Med's
first test, which ran fine). The warm-up has no music, so playing it at
`--speed 0.75` for good is a valid option.

## 5. Sync calibration

`click.wav` (90 BPM) and a single joint: the right arm hits down on every
click (`RShoulderPitch` = 0.6 rad exactly on each click, checked by a test).
Since 2 Nov the arm rises half as high between two clicks (0.2 rad instead of
−0.2 rad: dynamic part 11 → 2.7 mm); the low point is unchanged.
It must stay simple and repeatable to measure the music/motion offset
(docs/AUDIO_MACARENA.md §3). It is generated by `tools/make_calibration.py`,
not by the composer.

---

## 6. How the dances are built

```
<song excerpt>.wav ──tools/analyze_audio.py──> beats.json (tempo, beats, bars, phrases)
                                                     │
named poses (POSES)  ──tools/compose_choreographies.py (choreography/composer.py)──> motion.json + meta.json
                                                     │
                       Choreography.validate() ─────┴──> limits, speed, collisions, head envelope, balance
                       (also before every dance in the app)
```

- **Poses** (`POSES` in `tools/compose_choreographies.py`) are written for
  the left arm; the right arm is the mirror. Each one was designed with the
  kinematic model (`choreography/kinematics.py`) and the hard ones (crossed
  arms, hand to the head) were searched numerically for clearance and speed.
- **Steps**: `Dance.arm(side, beat, pose)` = "this arm reaches this pose on
  this beat", `Dance.arms(beat, left, right)` = both arms together. The
  composer holds the previous pose as long as possible, then starts the
  gesture just early enough to stay under **50 % of the joint's nominal max
  speed** (`ratio=`), and never in less than the dance's minimum gesture
  length (0.8 beat for NAO Party and Mekassarat, 0.9 for the Macarena, 1.2
  for the warm-up; `travel=` makes one gesture longer). `flow=True` chains
  gestures without stopping.
- **Curves**: monotone cubic Hermite (Fritsch–Carlson) written as explicit
  NAOqi Bezier keys (`[angle, [3, -dt/3, -slope·dt/3], [3, dt/3, slope·dt/3]]`):
  continuous speed through a gesture, zero speed on holds, **no overshoot**
  beyond the keys (so never beyond the joint limits), and exactly the curve
  `reference_pose.py` uses to score the player.
- **Smallest distance between NAO's volumes** in the model, over the whole
  dance: Macarena 20 mm, NAO Party, Warm-up and Mekassarat 22 mm. The volumes
  are deliberately oversized, but a model is not the robot: watch the crossed
  arms, the hands near the head and the disco arm in front of the chest
  during the first trials.
- **Validation** (`Choreography.validate`, run at generation, at start-up in
  the background, and before each dance): keys and curve within joint limits,
  peak speed (refused above 100 %, warning above 60 %), arm/arm, arm/head,
  arm/torso/pelvis/thigh distances along the whole trajectory (refused if the
  model volumes touch, warning under 8 mm), head pitch inside the yaw-dependent
  envelope, no leg joints, and since 2 Nov **balance** (section 0: refused
  above the `BALANCE_LIMITS`). A dance that fails is refused by the app before
  NAO moves ("... refused for safety", details in the log).

Regenerate after editing poses or steps:

```powershell
.\.venv\Scripts\python.exe tools\compose_choreographies.py              # the 4 composed dances + report
.\.venv\Scripts\python.exe tools\compose_choreographies.py echauffement # only one dance
.\.venv\Scripts\python.exe tools\compose_choreographies.py --check      # report only, nothing written
.\.venv\Scripts\python.exe tools\render_dance.py mekassarat             # pictures (needs matplotlib)
.\.venv\Scripts\python.exe -m unittest tests.test_dances -v
```

The report gives, for each dance, the balance estimate (backward, forward,
sideways, dynamic part, in mm), the number of keys, the fastest joints, and
any `[ERREUR]` / `[ATTENTION]`.

If NAO shows palms **up** on beat 1 of the Macarena, set `PALM_TWIST_SIGN = -1`
in `tools/compose_choreographies.py` and regenerate (the palm orientation of
NAO's zero posture is an assumption, see `choreography/kinematics.py`).

Previous versions: `tools/old_versions/choreographies_v1/` (before the first
rebuild) and `tools/old_versions/choreographies_v4/` (the v4 Macarena and NAO
Party, the warm-up that fell, Med's cautious warm-up). Copy `motion.json`
and `meta.json` back into `choreography/library/<dance>/` to restore one; the
v4 Macarena, NAO Party and fallen warm-up will be **refused** by the balance
check.

### Adding another song

1. Cut the excerpt to start on a phrase (a click track helps), WAV 22 050 Hz:
   `ffmpeg -ss <start> -to <end> -i song.mp3 -ar 22050 -ac 2 -af "afade=t=out:st=<len-0.3>:d=0.3" excerpt.wav`
2. `tools/analyze_audio.py excerpt.wav --click check.wav`, listen to
   `check.wav`, force `--bar-phase` / `--phrase-phase` if the downbeat is
   wrong.
3. Create `choreography/library/<id>/meta.json` (copy Mekassarat's), write a
   function like `mekassarat(grid)` in the composer, add it to `main()`.
4. Generate, check the report (no `[ERREUR]`, dynamic part ≤ 6 mm), copy the
   WAV to NAO, then docs/DANCE_VALIDATION.md.
