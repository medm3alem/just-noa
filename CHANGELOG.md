# Changelog

## 2026-11-02 (evening) — v5: balance after NAO's falls, livelier warm-up, Mekassarat

Starting point: Med's `just_nao_v4_warmup_rythme_commentaires.zip` (cautious
slow warm-up after NAO fell several times with the v4 warm-up, English
remarks during the dances). Med's remarks, safety notes and per-dance
regeneration are kept. **No dance was played by the physical NAO**
(docs/DANCE_VALIDATION.md, which now starts with a check of the robot).

### Why NAO fell, and the new balance check
- `choreography/kinematics.py`: masses of NAO's segments, `zmp_profile()` and
  `balance_summary()`: where NAO's weight presses on the floor while the arms
  move, split into a static part (arms held in front) and a **dynamic** part
  (arms accelerating).
- The v4 warm-up (both arms together forward / up / down every ~1.3 s) had a
  dynamic part of **13.7 mm**; the v4 Macarena and NAO Party were even higher
  (19 mm). Med's first Choregraphe test (ran fine): 1.0 mm; Med's slow
  warm-up: 0.4 mm.
- `Choreography.validate(..., balance=True)`: dynamic part refused above
  9 mm (warning 6 mm), total backward / forward / sideways shift refused above
  20 / 25 / 24 mm (`BALANCE_LIMITS`). The fallen warm-up is refused by this
  check (`tests/fixtures/echauffement_v4_fell`, also checked through the
  controller). Calibrated on one fall: it compares dances, it guarantees
  nothing.

### Dances (all rebuilt with the same moves or better, dynamic part 4–6 mm)
- **Warm-up**: 96 BPM, a pose every 2 beats then a gesture per beat, sideways
  and in-opposition gestures only (arms out to the sides, one arm forward
  then the other, arms up through the sides, elbow curls one after the other,
  open the chest). 4.2 mm. Med's two remarks kept. Arms go above the head in
  one block (unlike Med's cautious version): flagged in the docs, easy to
  remove. The player is scored again (still player 19, good player 100).
- **Macarena**: gestures over ≥ 0.9 beat, slower left arm after the "Ay!",
  hand leaves the cross and the head earlier, "Ay!" = right fist up + left
  arm out to the side (no more both arms up through the front). 19.2 → 5.6 mm.
- **NAO Party**: waves, one punch per beat in alternation, disco in
  opposition, new "wings" and "snake arms", sideways "ta-da". 18.8 → 5.7 mm.
- **New: Mekassarat (Ahmed Saad)**, excerpt 0:17.55 → 1:06 of the track Med
  sent (`mekassarat_extrait.wav`, 48.45 s): 109.98 BPM, 5 phrases + finale;
  hand twirls, wings, point to the sky, snake arms, waves above the head,
  disco, big finish; two English remarks. 5.0 mm, 11 named moves.
- **Sync calibration**: the arm rises half as high between clicks (11 →
  2.7 mm); the hit on each click is unchanged.
- New poses in the composer (side, lateral raise, twirls, wings, snake, point
  up, ta-da...); `Dance.arm()/arms()` accept `flow`, `hold`, `ratio`.
- Old versions in `tools/old_versions/choreographies_v4/` (v4 Macarena,
  v4 NAO Party, the warm-up that fell, Med's slow warm-up).

### Music analysis
- `tools/analyze_audio.py`: bar phase from chord changes **and** kick
  strength, phrase phase from level jumps / vocal entries / chord changes;
  `--bar-phase` and `--phrase-phase` force them when a song is ambiguous
  (used for Mekassarat).

### Scoring
- Player delay: the middle of the plateau of the delay correlation is used
  instead of its edge; it was underestimated by 0.05–0.1 s on slow gestures
  (now exact on Macarena, NAO Party and Mekassarat in simulation).

### Tests and docs
- Test fixtures of the controller tests use sideways arm swings (the old
  "both arms up and down every 0.8 s" fixture is now refused for balance).
- New tests: balance of every dance, the fallen warm-up refused (validation
  and controller), Mekassarat grid / moves / scoring, delay precision.
- docs/DANCES.md (balance section, new warm-up, Mekassarat, adding a song),
  DANCE_VALIDATION.md (robot check after falls, warm-up block by block,
  50 % → 75 % → 100 %), AUDIO_MACARENA.md (copy `mekassarat_extrait.wav` to
  NAO), README, Med's warm-up notes updated.

## 2026-11-02 (afternoon) — Dances rebuilt: Macarena, NAO Party, Warm-up

Nothing else was rebuilt: bridge v3, music on NAO, scoring engine, history,
English roasts and the window are unchanged except where listed. **No dance
was played by the physical NAO** (docs/DANCE_VALIDATION.md).

### Music analysis
- New `tools/analyze_audio.py` (numpy only): tempo, beats, bars, 16-beat
  phrases, phrase similarity, accents → `choreography/library/macarena/beats.json`.
- Macarena excerpt: **103.15 BPM**, first beat **0.235 s** on the kick drum,
  bars from beat 1, 7 full 16-beat cycles. The previous timing followed the
  off-beat hi-hat (0.29 s too early), the trap a general beat tracker falls into.
- `--click` writes the music with a click on every beat to check by ear.

### Composer and safety checks
- New `choreography/kinematics.py`: NAO arm forward kinematics (mm), palm
  direction, collision volumes (head, torso, pelvis, thighs, shoulders, arm
  capsules), yaw-dependent head pitch envelope.
- New `choreography/beatgrid.py` and `choreography/composer.py`: poses reached
  on beats, previous pose held as long as possible, gesture duration computed
  to stay under 50 % (55 % for head → hip) of nominal motor speed, monotone
  cubic curves (no overshoot) written as explicit NAOqi Bezier keys.
- `Choreography.validate()` now checks the **real curve** (sampled every
  10 ms): limits between keys, **peak** speed (was: average between keys,
  which hid peaks — the old warm-up reached 63 % of max), arm/arm, arm/head,
  arm/body distances along the trajectory, head envelope, duplicate joints,
  named moves. The controller caches the result and checks every dance in the
  background at start-up (no freeze when pressing Dance).
- New `tools/compose_choreographies.py` (generates the three dances, `--check`)
  and `tools/render_dance.py` (pose sheets and joint curves, needs matplotlib).

### Dances
- **Macarena**: recognisable 16-beat sequence on the measured beats — right
  then left arm out (palms down), palms up, hands to the opposite shoulders
  (crossed high/low), hands behind the head (via a waypoint around the face),
  hands on the hips, behind the hips, shoulder/elbow "wiggle" with head sway,
  hands up, "Ay!" arms in a V. 14 joints (head, shoulders, elbows, wrists,
  hands), 7 cycles with head and amplitude variations, final "Ay!" held,
  56 named moves, LED accents. Peak speed ≤ 51 %, min clearance 20 mm (model).
- **NAO Party**: 112 BPM routine — waves, two-hand waves, boxing punches with
  guard, disco points, curls, big finish; spoken intro and phrase cues, LEDs.
- **Warm-up**: 92 BPM, progressive (one pose every 2 beats, then every beat),
  spoken cues, 5 named blocks.
- **Calibration**: unchanged on purpose (precision first); a test checks the
  arm hits on every click.
- Previous versions kept in `tools/old_versions/choreographies_v1/`;
  Med's original NAO Party kept as a test fixture (`tests/fixtures/nao_party_v1`).

### Scoring, sync, app
- Named moves from `meta.json` drive the move count of the report; tips name
  the moves missed most often ("Moves to practice: Hands behind head (3 times)").
- Wrist rotation and hand opening are not scored (unchanged features, now tested).
- `main.py --speed 0.25…1.0`: every dance slowed down without music, for the
  first trials on the robot (Bezier handles stretched correctly).
- No change to the bridge, the player or the start-up synchronisation:
  `sync_offset` per dance stays the correction for a measured constant delay.

### Tests and docs
- 132 tests (was 103): new `tests/test_dances.py` (29 tests).
- New docs: `docs/DANCES.md` (every move, music analysis, how dances are
  built), `docs/DANCE_VALIDATION.md` (desk → virtual robot → 25 % → 50 % →
  75 % → 100 % with an operator, sync measurement, what to change).

## 2026-11-02 (morning) — Changes since `just_nao_physique_actuel.zip` (2026-11-02)

Nothing was rebuilt from scratch: the scoring, vision, choreographies, player
and the 15 saved sessions are the ones from the ZIP. Changes:

### Robot link
- `choregraphe_bridge.py` rewritten as **bridge v3** (`pong-physique-v3`,
  0.0.0.0:8766, Python 2.7 box): one thread per connection, Stop /
  emergency stop / audio stop / speech stop never wait behind a motion,
  audio preload + play in a worker thread + stop, no overlapping music,
  client IP filter, leg joints refused, motion refused after a fall until
  Wake up, clear English error messages. Still answers v2 clients.
- `robot/choregraphe_robot.py` rewritten for v3: host/port configurable
  (command line, Settings window, config.py), live address change, latency
  measured at connection, `audio_load`/`audio_play`/`audio_stop`, speech
  interruption, fall reporting; warns when the robot still runs v2.
- `sync/player.py`: Stop also interrupts the transition to the first pose
  and the countdown speech.
- Macarena and calibration use files **on NAO** (`audio_robot` in meta.json).
- Old bridge v1 and old clients moved to `tools/old_versions/`.

### English and NAO's personality
- All player-facing text is English: window, console menu, live feedback,
  tips, ratings, robot errors, NAO's voice. Operator log stays French.
- New `evaluation/roast_library.py` (134 lines) and
  `evaluation/nao_personality.py`: score bands, measured diagnostics,
  Friendly / Sarcastic / Savage, sarcasm off, Short / Long, no repeats
  (saved across restarts), seeded randomness.
- `app/controller.py`: end-of-dance sequence (music stopped → StandInit →
  report saved with `nao_comment` → score + one roast), Skip, Rest waits
  for speech, new dance cuts the comment, nothing after a fall, interrupted
  dances handled separately; robot unreachable at start-up no longer crashes.

### Window
- Results: "NAO says" card + Skip comment; Replay / Export / Main menu.
- History: NAO's comment column, export selected game, export all (CSV).
- Settings: language, NAO voice on/off, sarcasm on/off, intensity, length,
  in-dance encouragements, matching, camera (number or URL), latencies,
  NAO IP and bridge port.
- Main menu: Skip NAO's comment; status bar shows "connection lost" in red.

### Tests and docs
- 103 automated tests (was 48): bridge (also under Python 2.7), end of
  dance, personality, HMI screens, camera failure, robot unreachable.
- New docs: CHOREGRAPHE.md (v3), AUDIO_MACARENA.md, PERSONALITY.md,
  HARDWARE_TESTS.md, TROUBLESHOOTING.md; README in English.
- **Not done: any test on the physical NAO** (see docs/HARDWARE_TESTS.md).
