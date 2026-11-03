# Hardware test checklist (physical NAO)

**None of these tests has been run yet.** The automated tests cover the same
behaviours with simulated NAOqi services and a simulated player; this list is
what must be confirmed on the real robot before a public demo. Tick each box,
note the measured values, and keep the filled-in copy with the project.

Setup for every test: NAO on a flat, clear floor (1.5 m around it), battery
> 30 %, an operator within arm's reach, PC and NAO on the same local network,
Choregraphe connected with the v3 bridge box playing.

NAO fell several times with the v4 warm-up: do step 0 of
**docs/DANCE_VALIDATION.md** (robot checked after the falls) before anything
that makes NAO dance.

Date: ............  Robot: NAO V6 `nao` 192.168.2.121  NAOqi 2.8.7.4  Testers: ............

---

## A. Connection and bridge (robot sitting, motors off)

- [ ] A1. `ping 192.168.2.121` answers.
- [ ] A2. Choregraphe log shows `Just Nao bridge v3 pret : 0.0.0.0:8766`.
- [ ] A3. `Test-NetConnection 192.168.2.121 -Port 8766` → `TcpTestSucceeded : True`.
- [ ] A4. Diagnosis command (docs/CHOREGRAPHE.md §6) prints `pong-physique-v3`, battery, posture. Round trip: ........ ms.
- [ ] A5. Start the game: `.\.venv\Scripts\python.exe main.py --choregraphe --ui hmi --video 0`.
      **NAO does not move at start-up.** Status bar shows the robot and battery.
- [ ] A6. From another PC outside `192.168.2.*` (if available): connection refused, Choregraphe log `Client refuse`.

## B. Posture and safety (no music)

- [ ] B1. Wake up → NAO stands in StandInit, state "Ready".
- [ ] B2. Rest → NAO crouches, motors off, state "Resting".
- [ ] B3. Wake up again, select *Warm-up (arms)*, Start. Transition to the first pose is smooth (no jerk).
- [ ] B4. Press **Stop** in the middle: the arms stop **immediately** (< 0.5 s), NAO returns to StandInit. Measured reaction: ........ s.
- [ ] B5. Press the Space bar during a dance: same as Stop.
- [ ] B6. Close the window during a dance: motion stops, NAO goes to rest.
- [ ] B7. `--valider` lists every choreography as OK: `.\.venv\Scripts\python.exe main.py --choregraphe --valider`.

## C. Audio on NAO

- [ ] C1. Files copied: `ssh nao@192.168.2.121 "ls -l /home/nao/music"` shows `macarena_extrait.wav`, `mekassarat_extrait.wav` and `click.wav`.
- [ ] C2. *Sync calibration*: clicks come from NAO's speakers, volume OK.
- [ ] C3. Film the calibration; arm hit vs click offset: ........ s → `sync_offset` set to ........ (docs/AUDIO_MACARENA.md §3).
- [ ] C4. Macarena: music starts with the first move (offset by ear: ........).
- [ ] C5. Macarena ends: **music stops at the end** of the excerpt, no tail.
- [ ] C6. Stop during Macarena: music **and** motion stop at once.
- [ ] C6b. Mekassarat: music starts with the first move, stops at the end (48.5 s, short fade-out), the last hit lands on the "ta-da" (offset by ear: ........).
- [ ] C7. Replay right after Stop: only one music plays (no overlap).
- [ ] C8. Remove the WAV from the robot temporarily: the dance refuses to start with the English "audio file not found on NAO" message; put it back.

## D. Dances on the robot (upper body)

First follow **docs/DANCE_VALIDATION.md** (robot check, reduced speed 50 % → 75 %), then:

- [ ] D1. Whole Macarena and Mekassarat without collision of hands with head or hips.
- [ ] D2. No leg motion, NAO stays stable (no swaying, no sliding foot), no fall — Warm-up, NAO Party, Mekassarat, Macarena.
- [ ] D3. Moves in time with the music (note late moves: .............).
- [ ] D4. Motor temperature warning not reached after 3 dances in a row.

## E. Player, camera, score

- [ ] E1. Preparation screen: all five checks green with a player 2–3 m away.
- [ ] E2. Live messages are English and match what the player does
      (leave the frame → "Come back into the camera frame!").
- [ ] E3. Unplug the webcam during preparation: red Camera check, "Dance without score"; plug back + "Retry camera".
- [ ] E4. Score of a good imitation ≥ 75; of standing still ≤ 35.

## F. End of dance and NAO's comment

- [ ] F1. After a complete dance: music stopped, NAO back in StandInit, **then** "NN points!", short pause, one roast. Nothing spoken while the music played.
- [ ] F2. Results screen shows the same text under "NAO says"; History shows it too.
- [ ] F3. Skip comment cuts NAO mid-sentence.
- [ ] F4. Press Rest while NAO talks: NAO finishes the sentence, then rests.
- [ ] F5. Settings > Savage, then Friendly: the tone changes; sarcasm off → kind comment; voice off → text only.
- [ ] F6. Stop a dance early: short "you stopped early" comment, game saved as "stopped early", not counted as best score.
- [ ] F7. Comment length between 5 and 15 s (stopwatch): ........ s.

## G. Failures

- [ ] G1. Unplug the network cable / Wi-Fi of the PC during a dance: the app shows "connection lost", no crash; NAO keeps or finishes the current motion (operator ready to press NAO's chest button or catch it). Reconnect: "Liaison avec le robot retablie" in the log.
- [ ] G2. Stop the bridge box in Choregraphe while the app runs: clear "No answer from the Choregraphe bridge" error, no freeze.
- [ ] G3. Fall test **only with an operator holding the robot**, or skip it: tilt NAO until `robotHasFallen` fires (or simulate with Choregraphe's fall manager): dance and music stop, message "NAO fell! ...", Start refused, no automatic stand-up; Wake up only after NAO is back on its feet.

---

Result summary: ..................................................................

Problems found and fixes: ........................................................
