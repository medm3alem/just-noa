# Validating the dances on the physical NAO

**NAO fell several times with the v4 warm-up.** The dances were rebuilt on
2 Nov 2026 (v5: Macarena, NAO Party, Warm-up, new Mekassarat) with a balance
estimate added to the safety check (docs/DANCES.md §0). They pass every
automatic check, **but none of them has been played by the physical robot
yet**. The checks use a model of NAO (oversized volumes, point masses,
nominal motor speeds); the real robot can differ (cable bundles, worn
joints after the falls, motor heating, low battery, the floor). Validate step
by step, and do not skip a step because the previous one went well.

Fill in one copy of this sheet per robot. Keep it with the project.

Date: ............ Robot: NAO V6 `nao`, NAOqi 2.8.7.4, battery ......% Operators: ............

---

## 0. Before anything: the robot itself

NAO has fallen several times (docs/WARMUP_SAFE.md).

- [ ] 0.1 The person in charge of the robot has checked it after the falls
  (no joint noise, no play in the arms or the hips, no warning in the robot
  web page / Choregraphe, fall manager ON).
- [ ] 0.2 NAO stands in StandInit and moves its head and each arm alone,
  slowly, without noise or shaking (Choregraphe, "Motion" panel).

Do not go further until both are checked.

## Rules for every step

- One operator **kneeling next to NAO**, hands ready (not touching), clear
  floor 1.5 m around, flat non-slippery surface (no thick carpet). NAO's
  fall manager stays ON.
- A second person at the PC, finger on **Stop** (or the Space bar).
- Battery > 40 % for the full-speed steps; stop if a motor temperature
  warning appears in the log (`[ATTENTION] ... temperature`).
- Any contact between the arms, the arms and the head or body, any shaking,
  sliding foot, swaying, or loss of balance → **Stop**, note the time shown
  in the window, do not continue to the next step. Fix (section 5) and start
  again at step A.
- After a fall: no automatic recovery. Leave NAO on the floor, check it
  (step 0), only then stand it up by hand or from Choregraphe.

---

## A. Desk checks (no robot)

- [ ] A1. Automated tests pass:
  ```powershell
  .\.venv\Scripts\python.exe -m unittest tests.test_dances -v
  ```
- [ ] A2. Generation report has no `[ERREUR]`, speeds ≤ 55 %, dynamic
  balance part ≤ 6 mm for every dance:
  ```powershell
  .\.venv\Scripts\python.exe tools\compose_choreographies.py --check
  .\.venv\Scripts\python.exe main.py --fake --valider
  ```
  Expected: Macarena 5.6 mm, NAO Party 5.7 mm, Warm-up 4.2 mm,
  Mekassarat 5.0 mm (the warm-up that fell: 13.7 mm, now refused).
- [ ] A3. Look at the pose sheets `docs\img\macarena_poses.png`,
  `nao_party_poses.png`, `echauffement_poses.png`, `mekassarat_poses.png`.
  Each pose looks like the move it is named after.
- [ ] A4. Play the game with the simulated robot and player:
  `.\.venv\Scripts\python.exe main.py --fake --ui hmi --joueur-simule`.
- [ ] A5. Music copied to NAO (only needed for steps D):
  ```powershell
  scp choreography\library\macarena\macarena_extrait.wav nao@192.168.2.121:/home/nao/music/
  scp choreography\library\mekassarat\mekassarat_extrait.wav nao@192.168.2.121:/home/nao/music/
  ```

## B. Virtual robot in Choregraphe (recommended)

Shows the real NAO 3D model moving with the real trajectories (no physics:
it does not detect collisions or falls).

- [ ] B1. In Choregraphe, connect to the **virtual robot**, put the bridge box
  in a project and press Play (log: `Just Nao bridge v3 pret : 0.0.0.0:8766`).
- [ ] B2. Run at half speed (no music):
  ```powershell
  .\.venv\Scripts\python.exe main.py --choregraphe --ip 127.0.0.1 --speed 0.5 --ui hmi --video 0
  ```
- [ ] B3. Watch each dance in the 3D view, especially: crossed arms (Macarena
  beats 5–6), hand passing in front of the face (7–8), hands behind the hips
  (11–12), disco arm across the body (NAO Party 33–48, Mekassarat 64–79),
  hands above the head (Warm-up 17–24, Mekassarat 48–63). Notes: ............

## C. Physical NAO, reduced speed, no music

`--speed` slows every dance down; NAO's music is switched off (it cannot be
slowed down), the score still works. Slower also means much gentler for the
balance: the dynamic push drops roughly with the square of the speed
(Warm-up: 4.2 mm at 100 %, 2.6 mm at 75 %, 1.2 mm at 50 %).

Order: **Warm-up first** (it is the one that fell before, and the gentlest
now), then NAO Party, then Mekassarat, then the Macarena.

- [ ] C1. Robot awake, StandInit, nothing moves at start-up.
- [ ] C2. **50 %** – Warm-up, block by block. Press Stop at the end of each
  block the first time:
  ```powershell
  .\.venv\Scripts\python.exe main.py --choregraphe --speed 0.5 --ui hmi --video 0
  ```
  | Block (beats) | OK | Notes (swaying, feet, noise) |
  |---|---|---|
  | 1–8 arms out to the sides | [ ] | |
  | 9–16 one arm forward, then the other | [ ] | |
  | 17–24 arms up through the sides (above the head: not in Med's cautious version) | [ ] | |
  | 25–32 elbow curls | [ ] | |
  | 33–44 open / close, end | [ ] | |
- [ ] C3. **50 %** – NAO Party and Mekassarat, full. Watch the punch guard,
  the disco arm in front of the chest, the hand waving above the head.
- [ ] C4. **50 %** – Macarena, first cycle only (press Stop after ~20 s):
  | Moment (beat) | OK | Notes (distance seen, sound, effort) |
  |---|---|---|
  | 1–4 arms out, palms down then up | [ ] | palms really down then up? (else section 5) |
  | 5–6 crossed arms, right above left | [ ] | gap between the forearms: ...... cm |
  | 7–8 hand beside the head | [ ] | gap hand–head: ...... cm |
  | 9–12 hands on / behind the hips | [ ] | gap hand–hip: ...... cm |
  | 13–16 elbows pump, "Ay!" fist up / arm out | [ ] | |
- [ ] C5. **75 %** (`--speed 0.75`) – each dance in full. NAO stays stable, no
  swaying, no sliding, no noise of a motor forcing. Stop works within half a
  second.
- [ ] C6. Watch the feet during C5: if a foot lifts or slides even slightly,
  stop there (section 5, "Robot unstable").

## D. Physical NAO, full speed

- [ ] D1. Warm-up at 100 % (no music anyway). If it was borderline at 75 %,
  keep playing it at `--speed 0.75`: that is a valid permanent choice.
- [ ] D2. NAO Party at 100 %.
- [ ] D3. Mekassarat at 100 % with music, without a player (`--video none`).
  Stable, no contact, music and moves together by ear.
- [ ] D4. Macarena at 100 % with music, without a player.
- [ ] D5. **Sync**: film NAO from the side (60 fps if possible). Macarena:
  compare the arm arriving straight in front (beats 1 and 2 of a cycle) with
  the kick drum; Mekassarat: the "ta-da" on the last hit (beat 88) or the
  wings from beat 16. Offset `d`: ...... s.
  - moves **late** by `d` → `"sync_offset": -d` in that dance's `meta.json`
  - moves **early** by `d` → `"sync_offset": +d`
  Then replay and check again. (Re-running the composer keeps `sync_offset`.)
- [ ] D6. Three dances in a row, then read the log: no temperature warning,
  battery used: ......%.
- [ ] D7. Full game with a player in front of the camera: score, results,
  NAO's comment, Replay. The player can follow NAO (ask them): ......

## 5. If something is wrong

| Problem | What to change |
|---|---|
| Robot sways, a foot slides or lifts | stop the trials. Note the move (time in the window, docs/DANCES.md tables). Make that move slower (larger `travel=`) or smaller, or replace a two-arm gesture by one arm at a time; lower the limits in `BALANCE_LIMITS` (`choreography/kinematics.py`) so the check catches it next time; regenerate |
| Warm-up still too risky | play it at `--speed 0.75`, or restore Med's cautious version (`tools/old_versions/choreographies_v4/echauffement_lent/`, copy its two files into `choreography/library/echauffement/`) |
| Arms above the head worry you | remove the "Arms up through the sides" block (docs/DANCES.md §4) |
| Palms up on beat 1, down on beat 3 | `PALM_TWIST_SIGN = -1` in `tools\compose_choreographies.py`, regenerate |
| Contact or too close somewhere | find the pose in `POSES` (same file), move it a little away (e.g. smaller `ShoulderRoll` inward, less `ElbowRoll`), regenerate; if the model did not see it, enlarge the matching volume in `choreography\kinematics.py` (`R_FORE`, `HEAD_RADIUS`, boxes) so the check catches it next time |
| A gesture looks too fast / jerky | lower `Dance.MAX_RATIO` (0.5) or the `ratio=` of that step, regenerate |
| A gesture lags behind the music | measure with D5 first; if only one gesture is late, start it earlier (`travel=` larger) |

After any change:

```powershell
.\.venv\Scripts\python.exe tools\compose_choreographies.py
.\.venv\Scripts\python.exe -m unittest tests.test_dances -v
```

and restart this sheet at step A. Previous versions:
`tools\old_versions\choreographies_v1\` and `choreographies_v4\`.

---

Result: ............................................................................
