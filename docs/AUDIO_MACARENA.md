# Music on NAO and synchronisation (Macarena, Mekassarat)

With the bridge v3, the music is played **by NAO's own speakers**
(ALAudioPlayer). The file must therefore be **on the robot**; the copy in the
project folder is only used by the simulated robot and for the duration.

| Choreography | File in the project | File on NAO (`audio_robot` in meta.json) |
|---|---|---|
| Macarena | `choreography\library\macarena\macarena_extrait.wav` (66.0 s, 22.05 kHz stereo) | `/home/nao/music/macarena_extrait.wav` |
| Mekassarat (Ahmed Saad) | `choreography\library\mekassarat\mekassarat_extrait.wav` (48.45 s, 22.05 kHz stereo) | `/home/nao/music/mekassarat_extrait.wav` |
| Sync calibration (90 BPM) | `choreography\library\calibration\click.wav` | `/home/nao/music/click.wav` |
| Warm-up (arms), NAO Party | no music | – |

The Macarena WAV is the excerpt **00:48 → 01:54** of *Macarena (Bayside Boys
Remix)* by Los Del Rio, cut from the track the team provided. The
choreography's time 0 is the first sample of this excerpt.

The Mekassarat WAV is the excerpt **0:17.55 → 1:06.00** of *Ahmed Saad –
Mekassarat* (Official Music Video, أحمد سعد - مكسرات), cut from the audio Med
provided (0:18 → 1:06 chosen by Med; the start was moved half a beat earlier
so that the excerpt begins exactly on a phrase), with a 0.3 s fade-out.

Check that your use of the tracks is allowed (school demo, no public
distribution).

---

## 1. Copy the files to NAO (once)

Windows 10/11 includes `ssh` and `scp`. From the project folder:

```powershell
ssh nao@192.168.2.121 "mkdir -p /home/nao/music"
scp .\choreography\library\macarena\macarena_extrait.wav nao@192.168.2.121:/home/nao/music/
scp .\choreography\library\mekassarat\mekassarat_extrait.wav nao@192.168.2.121:/home/nao/music/
scp .\choreography\library\calibration\click.wav nao@192.168.2.121:/home/nao/music/
ssh nao@192.168.2.121 "ls -l /home/nao/music"
```

The password is the robot's `nao` user password (`nao` unless it was changed).
Without `scp`, use WinSCP (protocol SFTP, host 192.168.2.121, port 22, user
`nao`) and drop the three files into `/home/nao/music/`.

If the file is missing, the dance does not start and the app says:
`Robot error: NAO (audio_load): audio file not found on NAO: /home/nao/music/macarena_extrait.wav`.
This is deliberate: better no dance than a dance on the wrong music.

---

## 2. What happens when a dance starts

1. `audio_load`: NAO preloads the file (ALAudioPlayer.loadFile) and returns
   its id and duration. Any music still playing is stopped first.
2. NAO goes to StandInit, then moves smoothly (1.5 s) to the first pose.
3. The PC fixes a common start time `t_go` on its own monotonic clock.
4. At `t_go`, two threads send at the same moment:
   `audio_play {id, volume}` and `play {names, times, keys}`, each on its own
   TCP connection. The bridge starts the music in a worker thread and the
   motion in the connection thread: neither waits for the other.
5. At `end` (66.0 s for Macarena) the PC sends `audio_stop` (and stops the
   motion if it is still running).
6. **Stop**, a fall or closing the app sends `stop` + `audio_stop`
   immediately (they never wait behind the motion).
7. **Replay**: `audio_load`/`audio_play` always stop the previous track, so
   two Macarenas can never play on top of each other.

The scoring clock uses the same `t_go`:
`tau = (t_image − CAMERA_LATENCY) − t_go − ROBOT_LATENCY`.

---

## 3. Start-up delay: what is and is not guaranteed

- In the automated test (simulated NAOqi on the PC) music and motion start
  less than **0.15 s** apart and both stop at the end.
- On the real robot, extra delays add up: network (the app logs the
  measured round trip at connection, e.g. `aller-retour 12 ms`), the bridge
  thread, ALAudioPlayer's output buffer, and ALMotion's first interpolation
  step. Typical order of magnitude: tens of ms to ~0.2 s. **This has not been
  measured on your NAO yet.**
- A constant delay is corrected with `sync_offset` in the choreography's
  `meta.json` (seconds): **positive = the motion starts later than the music**,
  negative = the music starts later than the motion.
- A drift during the dance would come from the choreography timing itself;
  the Macarena now follows the measured beats (constant tempo, residual 23 ms).
- The big Macarena trajectory (14 joints, ~2,000 keys) is planned by ALMotion
  when it arrives; if that takes longer than for the small calibration
  motion, the calibration offset will not include it. Measure the offset on
  the Macarena itself too (docs/DANCE_VALIDATION.md, step D3).

### Measure it with the calibration choreography

1. Copy `click.wav` (above). Wake NAO up.
2. Film NAO and its speaker with a phone (side view, 60 fps if possible).
3. Run **Sync calibration (90 BPM)**: the right arm hits on every click,
   the LEDs flash red on the first beat of each bar.
4. In the video, compare the click and the bottom of each arm hit:
   - arm hits **after** the click by `d` seconds → set `"sync_offset": -d`
   - arm hits **before** the click by `d` seconds → set `"sync_offset": +d`
5. Copy the same value into `choreography\library\macarena\meta.json`, then
   check by ear on the Macarena chorus.

`ROBOT_LATENCY` in Settings (0.10 s by default) is the delay between the
command and NAO's visible motion, used only for the scoring clock.

---

## 4. Macarena choreography

- Timed on the **measured** beat grid (`beats.json`, `tools/analyze_audio.py`):
  103.15 BPM, first beat 0.235 s (kick drum), 16-beat phrases from 0.817 s,
  7 full Macarena cycles. Each pose is reached on its beat.
- 14 joints (head yaw/pitch, both arms with wrists and hands), Bezier curves,
  **no leg motion** (also refused by the bridge). Every move is described in
  **docs/DANCES.md**.
- Checked by the app before every dance: joint limits, peak speed
  (≤ 46 % here), arm/head/body distances, head envelope, balance. Not yet
  played on the physical robot: **docs/DANCE_VALIDATION.md**.
- Scoring window: 0.82 s → 65.9 s; arms only; 56 named moves.
- The music starts 0.235 s before the first beat: NAO starts in its first pose
  (right arm already raised in front) and the first gesture lands on beat 1.

### Mekassarat

- Measured beat grid: 109.98 BPM, first beat 0.064 s, 89 beats (5 phrases of
  16 beats + 9-beat finale). Moves: docs/DANCES.md §2.
- Scoring window 1.16 s → 48.37 s, arms only, 11 named moves.
- For the sync check (docs/DANCE_VALIDATION.md D5): the "ta-da" on the last
  hit (beat 88, 48.07 s) or the wings that start with the kick drum (beat 16,
  8.79 s). Correct with `"sync_offset"` in
  `choreography\library\mekassarat\meta.json`, like the Macarena.

---

## 5. Using another song

1. Cut the excerpt to a WAV (or MP3/OGG) file, e.g. with Audacity, or with
   ffmpeg as described in docs/DANCES.md ("Adding another song").
2. Put it in the choreography folder and copy it to `/home/nao/music/`.
3. In `meta.json`:
   ```json
   "audio": "my_song.wav",
   "audio_robot": "/home/nao/music/my_song.wav",
   "audio_start": 0.0,
   "end": 60.0
   ```
   `audio_start` (seconds) starts the robot file later (ALAudioPlayer
   `playFileFromPosition`) if you prefer to copy the whole song instead of
   an excerpt; the choreography's time 0 is then that position.
