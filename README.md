# Just Nao

A Just Dance–style game with the NAO humanoid robot. NAO dances a choreography
to music played through its own speakers, the player copies it in front of a
webcam, MediaPipe tracks the player's skeleton, and the app scores the
imitation live. At the end NAO announces the score in English and adds one
short, sarcastic comment about the dance. Every game is saved and can be
reviewed or exported.

Team: Med (robot and synchronisation), Ram (choreographies), Armin (interfaces).

> **Status, honestly.** Everything in this package was tested automatically on
> a PC with a simulated robot, simulated NAOqi services and a simulated player
> (142 tests). **Nothing in this version has been run on the physical NAO
> yet**, including the rebuilt dances. NAO **fell several times** with the
> previous warm-up: every dance now also passes a balance check, but that check
> is a model, not a proof. Before a demo, follow **docs/DANCE_VALIDATION.md**
> (starting with the robot check after the falls) and **docs/HARDWARE_TESTS.md**
> step by step.

Dances: **Macarena** and **Mekassarat** (Ahmed Saad) with music on NAO's
speakers, **NAO Party** and **Warm-up (arms)** without music, and **Sync
calibration**. All moves: **docs/DANCES.md**.

---

## 1. Quick start (Windows, PowerShell)

Requirements: Windows 10/11 64-bit, **Python 3.12** (3.12.9 is the reference;
3.11 and 3.13 also pass the tests; Python 3.14 is *not* needed and MediaPipe
may not support it yet), a webcam, and for the robot part Choregraphe 2.8.7.4.

```powershell
cd C:\Users\USER\Desktop\just_nao        # the folder that contains main.py

# One time: virtual environment with Python 3.12
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\download_model.py      # skip if models\pose_landmarker_full.task exists

# Automated tests (about 3-4 minutes; the window tests need a desktop session)
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .

# Play WITHOUT the robot (simulated NAO), with webcam 0
.\.venv\Scripts\python.exe main.py --fake --ui hmi --video 0

# Demo without robot AND without camera (simulated player, shown as such)
.\.venv\Scripts\python.exe main.py --fake --ui hmi --joueur-simule

# Play WITH the physical NAO (bridge box running in Choregraphe, see section 4)
.\.venv\Scripts\python.exe main.py --choregraphe --ui hmi --video 0
```

If PowerShell refuses `py -3.12`, install Python 3.12 from python.org (tick
"Add python.exe to PATH") or use the full path, e.g.
`& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv`.
There is no need to activate the venv: every command calls `.venv\Scripts\python.exe`.

| Option | Effect |
|---|---|
| `--choregraphe` | NAO (physical or virtual) through the Choregraphe bridge box |
| `--ip 192.168.2.121` | robot IP (default: Settings window, else `config.py`) |
| `--bridge-port 8766` | bridge port (default: Settings window, else `config.py`) |
| `--fake` | simulated robot (no robot, no SDK) |
| `--ui hmi` / `--ui clavier` | game window / console |
| `--video 0`, `--video 1`, `--video <URL>`, `--video none` | camera |
| `--joueur-simule` | simulated player instead of the camera |
| `--valider` | check every choreography (limits, speeds, arm/head/body distances, balance), then quit |
| `--speed 0.5` | every dance slower (0.1–1.0), without music: first trials on the robot |

Priority of settings: **command line > Settings window (`results\settings.json`) > `config.py`**.

---

## 2. The game

1. **Main menu**: choreographies (length, level, best score), robot card
   (Wake up / Rest / Skip NAO's comment), operator log, History, Settings.
2. **Preparation**: live checklist (robot connected, camera, pose detection,
   player visible, choreography ready), video with skeleton, then a 3-2-1
   countdown. Without camera or detection: "Dance without score" (demo mode).
3. **Dance**: mirrored video with coloured arms, live score, per-arm bars,
   target pose, remaining time, Stop. Live messages are English and come
   from measurements only: "Come back into the camera frame!", "Raise your
   left arm!", "Bend your right elbow!", "You're a little late!", "Don't stop now!"...
4. **End of the dance** (in this order): the music stops, NAO finishes its
   movement and returns to StandInit, the score is frozen, the **Results**
   screen opens, the report is saved, then NAO says the score and **one**
   roast ("63 points!" … "Respectable. Not legendary, but respectable!").
   The text is shown under **NAO says**; **Skip comment** cuts it.
5. **Results**: final score and rating (Excellent / Great / Good / Needs work
   / Try again), tracked time, correct poses, moves done right, average
   delay, score curve, per-arm scores, tips, **Replay**, **Export**, **Main menu**.
6. **History**: every saved game with NAO's comment; open, export one game
   (CSV + JSON) or the whole history (CSV).
7. **Settings**: language (English), NAO announces the score on/off,
   sarcastic comments on/off, roast intensity (Friendly / Sarcastic / Savage),
   comment length (Short / Long), spoken encouragements during the dance,
   mirror/same-side matching, camera (number or URL), latencies, NAO IP and
   bridge port (applied immediately to the Choregraphe bridge connection).

Scoring is explained in **docs/EVALUATION.md**, NAO's personality in
**docs/PERSONALITY.md**.

---

## 3. Architecture

```
PC (Windows, Python 3.12)                                NAO V6 (NAOqi 2.8.7.4)
┌──────────────────────────────────────────┐   JSON/TCP   ┌──────────────────────────────┐
│ ui/hmi.py ── app/controller.py           │  one command │ Choregraphe Python box       │
│                │      │                  │  per         │ choregraphe_bridge.py (v3)   │
│      sync/player.py   app/game_session   │  connection  │ 0.0.0.0:8766, LAN only       │
│   (music, motion,     (score, report)    │ ───────────> │  ALMotion, ALRobotPosture,   │
│    events, t = 0)          ▲             │ 192.168.2.121│  ALAudioPlayer, ALTextToSpeech│
│                │      vision/pipeline    │    :8766     │  ALLeds, ALBattery, ALMemory │
│ robot/choregraphe_robot.py   ▲ webcam    │              │  (fall detection)            │
└──────────────────────────────────────────┘              └──────────────────────────────┘
```

```
just_nao/
├── main.py                   picks robot, interface, camera; wires everything
├── config.py                 every setting (robot, safety, vision, scoring, NAO voice)
├── choregraphe_bridge.py     bridge v3: paste into ONE Choregraphe Python box (Python 2.7)
├── app/controller.py         state machine; end-of-dance announcement; skip; rest waits for speech
├── app/game_session.py       one game: clocks, live score, report
├── app/settings.py           settings editable in the window (whitelist, validated)
├── robot/                    base.py (contract), choregraphe_robot.py (bridge client),
│                             fake_robot.py (simulation), nao_robot.py (direct NAOqi SDK, Python 2.7)
├── sync/player.py            music + motion + events on a common clock; Stop interrupts every phase
├── choreography/
│   ├── library/              macarena, mekassarat (+ beats.json and WAV), echauffement (warm-up), nao_party, calibration, _modele
│   ├── choreography.py       loading + validation of the real trajectory (limits, speed, collisions)
│   ├── reference_pose.py     NAO's pose at time t (also used to score the player)
│   ├── kinematics.py         NAO upper-body geometry, collision volumes, head envelope, balance (ZMP)
│   ├── beatgrid.py           beats, bars, 16-beat phrases
│   └── composer.py           poses on beats -> smooth Bezier motion.json
├── vision/                   camera, MediaPipe Pose Landmarker (Tasks API), filter, features, overlay
├── evaluation/
│   ├── scoring.py, comparator.py, pose_mapping.py   scoring
│   ├── feedback.py           English live messages and tips
│   ├── roast_library.py      134 English lines (bands, diagnostics, intensities)
│   └── nao_personality.py    picks the end-of-dance comment from the measurements
├── reports/session_store.py  JSON per game, history, CSV/JSON exports
├── ui/                       hmi.py, game_screen.py, results_screen.py, settings_dialog.py,
│                             widgets.py, keyboard_ui.py, hmi_classic.py (Python 2.7 window)
├── tests/                    unit, integration, bridge (fake NAOqi, also under Python 2.7), HMI
├── tools/                    analyze_audio (tempo/beats), compose_choreographies (the 4 composed dances),
│                             render_dance (pose sheets), download_model, check_nao,
│                             import_choregraphe, make_calibration,
│                             old_versions/ (bridge v1, old clients, dances v1 and v4)
├── docs/                     see below
├── models/                   pose_landmarker_full.task
└── results/                  sessions/, exports/, settings.json, roast_history.json
```

**Threads.** Camera capture; vision (detection, scoring, display image);
controller (dance, wake, rest); player (audio, motion, events); robot status
monitor; NAO's end-of-dance speech; Tkinter (display only, every 100 ms).
On the robot: one thread per bridge connection, a motion lock for long
motions only, an audio worker thread.

**Python versions.** The app runs on Python 3.12 (the game needs MediaPipe,
which does not exist for Python 2). The bridge runs inside Choregraphe in
Python 2.7 and is also tested under Python 2.7 and 3 on the PC. The old
direct-SDK mode (`--ip` without `--choregraphe`, NAOqi Python 2.7 SDK) is
kept but has no game (no MediaPipe in Python 2.7).

---

## 4. Physical NAO in 6 steps

Details: **docs/CHOREGRAPHE.md** (bridge) and **docs/AUDIO_MACARENA.md** (music).

1. **Network**: PC and NAO on the same trusted local network (NAO
   `192.168.2.121`; press the chest button once and NAO says its IP).
   ```powershell
   ping 192.168.2.121
   ```
2. **Copy the music to NAO** (password asked; default `nao` unless changed):
   ```powershell
   ssh nao@192.168.2.121 "mkdir -p /home/nao/music"
   scp .\choreography\library\macarena\macarena_extrait.wav nao@192.168.2.121:/home/nao/music/
   scp .\choreography\library\mekassarat\mekassarat_extrait.wav nao@192.168.2.121:/home/nao/music/
   scp .\choreography\library\calibration\click.wav nao@192.168.2.121:/home/nao/music/
   ```
3. **Bridge box**: in Choregraphe, connect to the NAO, create one Python box,
   paste the whole `choregraphe_bridge.py`, press Play. The log must show
   `Just Nao bridge v3 pret : 0.0.0.0:8766`.
4. **Check the link** (no robot motion):
   ```powershell
   Test-NetConnection 192.168.2.121 -Port 8766
   ```
5. **Start the game** and keep an operator next to the robot:
   ```powershell
   .\.venv\Scripts\python.exe main.py --choregraphe --ip 192.168.2.121 --bridge-port 8766 --ui hmi --video 0
   ```
   The operator log shows `[OK] Passerelle pong-physique-v3 sur 192.168.2.121:8766 (aller-retour N ms)`.
6. **First run**: the dances were never played by the robot, and NAO fell
   with the previous warm-up. Have the robot checked first, then start at
   reduced speed (`--speed 0.5`, then 0.75) following
   **docs/DANCE_VALIDATION.md** (Warm-up first, block by block), and only then
   full speed (upper body only). Then **docs/HARDWARE_TESTS.md**.

Nothing moves at start-up: the app only connects and reads the robot status.
NAO moves only when the operator presses Wake up or starts a dance.

---

## 5. Safety

- Upper-body choreographies only; the bridge refuses leg joints (`ALLOW_LEG_MOTION = False`).
- Every choreography is checked before it can be selected, on the curve NAO
  will really play: joint limits, peak speed, distances between the arms, the
  head and the body (geometric model), head pitch/yaw envelope. A refused one
  cannot be run (see `--valider`). The composed dances stay at ≤ 55 % of the
  nominal motor speeds.
- **Balance** (since the falls of the v4 warm-up): the check also estimates
  how much the arm movements push NAO's weight around (ZMP, docs/DANCES.md
  §0) and refuses a dance that pushes too hard (the warm-up that fell is now
  refused). The model was calibrated on one observed fall: it compares
  dances, it does not guarantee that NAO stays up. Big two-arm gestures go
  sideways or in opposition, never both arms together through the front.
- Smooth 1.5 s transition to the first pose; StandInit before and after.
- **Stop** is never queued behind a motion: it reaches the robot through its
  own connection and kills the motion and the music immediately.
- **Fall**: dance and music are stopped, motion is refused until the operator
  puts NAO back on its feet and presses **Wake up** or **Rest**. There is no
  automatic stand-up after a fall.
- The bridge accepts commands only from `127.*` and `192.168.2.*` (edit
  `ALLOWED_CLIENTS` to your PC's exact IP for a stricter setup). Never expose
  port 8766 outside the local network: it moves a real robot.
- Keep a person next to the robot, a clear floor, and the battery above 30 %.

---

## 6. Documentation

| File | Content |
|---|---|
| docs/CHOREGRAPHE.md | bridge v3: install, configuration, commands, security, upgrade from v1/v2 |
| docs/DANCES.md | every move of every dance, balance (why NAO fell), the music analysis, how dances are composed and checked, adding a song |
| docs/DANCE_VALIDATION.md | progressive validation of the dances on the physical NAO (robot check, 50 % → 100 %) |
| docs/WARMUP_SAFE.md, docs/WARMUP_RYTHME_ET_COMMENTAIRES.md | Med's notes on the warm-up after the falls, and on the remarks during the dances (French) |
| docs/AUDIO_MACARENA.md | copying audio to NAO, Macarena and Mekassarat sync, calibration, start-up delay limits |
| docs/PERSONALITY.md | NAO's end-of-dance comments: bands, diagnostics, intensities, settings |
| docs/HARDWARE_TESTS.md | checklist to run on the physical robot (not done yet) |
| docs/TROUBLESHOOTING.md | common problems and fixes |
| docs/EVALUATION.md | scoring method (French) |
| docs/CAMERA.md | camera and MediaPipe setup (French) |
| docs/GUIDE_ROBOT.md | direct NAOqi SDK mode, choreography format (French) |
| docs/DEMO.md | demo script (French) |

---

## 7. Tests

```powershell
# Everything (unit + integration + bridge + windows)
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v

# One file
.\.venv\Scripts\python.exe -m unittest tests.test_personality -v
.\.venv\Scripts\python.exe -m unittest tests.test_bridge -v
.\.venv\Scripts\python.exe -m unittest tests.test_end_of_dance -v
.\.venv\Scripts\python.exe -m unittest tests.test_dances -v

# Also run the bridge under Python 2.7 (if a Python 2.7 is installed)
$env:JN_PY27 = "C:\Python27\python.exe"
.\.venv\Scripts\python.exe -m unittest tests.test_bridge -v
Remove-Item Env:JN_PY27
```

| File | What it checks |
|---|---|
| test_dances.py | the composed dances: limits, peak speed ≤ 55 %, collisions along the whole trajectory, head envelope, no leg joint, balance (the warm-up that fell is refused, every dance well below), Mekassarat beat grid and moves, Bezier format and continuity, gesture durations, no long stillness, generator in sync with the files, Macarena beat grid, moves on the beats, recognisable poses, variation between cycles, audio analysis on a synthetic beat, calibration hits on clicks, scoring compatibility (wrists/hands not scored, distinct gestures, good/still/late players, named moves in tips), Stop in the middle of the real Macarena through the bridge, reduced speed |
| test_bridge.py | the real bridge with fake NAOqi: command format, Stop during a 20 s motion, busy refusal, audio load/play/stop, no overlapping audio on replay, start position, speech interruption, leg refusal, fall handling, client filter, audio/motion start within 0.15 s, unreachable bridge, v2 compatibility, Python 2.7 run |
| test_end_of_dance.py | music stopped and posture reached before speaking, score then one roast, saved with the report, announced once, skip, rest waits for speech, new dance cuts the comment, voice off, sarcasm off, interrupted dance, no comment after a fall, unevaluable game, robot unreachable |
| test_personality.py | ≥ 50 unique English lines, every intensity, wording rules (no body, appearance or legs), score bands, measured diagnostics only, no repeats (also across restarts), seeded randomness, missing score, unevaluable, interrupted, long mode, 5–15 s length |
| test_hmi_screens.py | results with NAO's comment, Replay, history + exports, Settings (voice, roast, robot address, camera), English-only screens, camera failure → demo mode, connection lost |
| test_hmi.py | full game in the window: menu → preparation → dance → results (with NAO's comment) → history → settings |
| test_controller_pipeline.py, test_session_reports.py, test_features_scoring.py, test_reference.py | controller (an unbalanced dance cannot be started), vision pipeline, feedback, reports, scoring (player delay measured to ±0.05 s), reference pose |

The window tests are skipped automatically when no display is available.

---

## 7b. Adding a choreography

A folder in `choreography/library/` with `meta.json` and `motion.json`
(docs/GUIDE_ROBOT.md, section 6), or better, composed from poses on a beat
grid like the composed dances (docs/DANCES.md §6 "Adding another song",
`tools/compose_choreographies.py`).
For music played by NAO, add the robot path of the file and copy it to the robot:

```json
"audio": "my_song.wav",
"audio_robot": "/home/nao/music/my_song.wav",
"audio_start": 0.0,
"difficulty": "easy",
"scoring": {"start": 1.0, "end": 60.0}
```

---

## 8. Known limitations

- **No physical validation yet**: bridge v3, audio on NAO, timing on the real
  network and the end-of-dance speech were tested with simulated NAOqi
  services only.
- **Start-up delay between music and motion**: both start from the same PC
  clock, but each command crosses the network and NAOqi separately. The
  simulated test keeps the gap under 0.15 s; on the robot, measure it with
  *Sync calibration* and set `sync_offset` (docs/AUDIO_MACARENA.md).
- The Macarena is an upper-body adaptation of the classic sequence (no hip
  roll, no jump or quarter turn, same-side hips, the hand leaves the head
  early), timed on the measured beat grid (103.15 BPM, kick drum).
  Mekassarat: 109.98 BPM; its bar and phrase start were set by ear (forced
  in the analysis), the beats themselves are measured.
- The collision check uses a geometric model with oversized volumes, and the
  balance check point masses and one observed fall; neither is a substitute
  for the reduced-speed trials.
- To stay balanced, the Macarena's "Ay!" is one fist up and one arm out (not
  both arms up in a V), and the two arms are no longer crossed at the same
  moment (docs/DANCES.md §1.2). The palm orientation of
  NAO's zero posture is an assumption (one switch to flip it).
- MediaPipe depth is the least reliable measurement (2D scoring available in Settings).
- Head, torso and legs are not scored for the current choreographies; one player at a time.
- Player-facing text is English only; operator log lines stay in French.
- Choregraphe can only run one copy of the bridge per robot (port 8766).

## Physical NAO Connection

The robot IP address can be configured using the --ip argument.

Example:

    python main.py --choregraphe --ip 192.168.2.121 --bridge-port 8766 --ui hmi --video 0

For network setup, IP changes and troubleshooting, see:

[NAO Connection Guide](docs/NAO_CONNECTION.md)
