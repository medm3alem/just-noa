# Choregraphe bridge v3 (physical NAO)

The game runs on the PC in Python 3.12. NAO is driven through **one Python box
in Choregraphe 2.8.7.4** that contains `choregraphe_bridge.py`. When
Choregraphe is connected to the physical NAO and you press Play, the box runs
**on the robot** (Python 2.7 inside NAOqi 2.8.7.4) and listens on port 8766.

```
PC  main.py --choregraphe  ──TCP, one JSON line per connection──>  NAO 192.168.2.121:8766
                                                                    (box bound to 0.0.0.0:8766)
```

> Status: the v3 bridge was tested on the PC with simulated NAOqi services,
> under Python 3 and Python 2.7 (tests/test_bridge.py). It has **not** been run
> on the physical robot yet: use docs/HARDWARE_TESTS.md for the first run.

---

## 1. Install the box

1. Start **Choregraphe 2.8.7.4** and connect to the robot
   (*Connection > Connect to...*, pick `nao` / `192.168.2.121`).
2. **Keep a copy of your current working box** before replacing anything:
   right-click the box > *Edit box script*, select all, paste into
   `tools\choregraphe_bridge_v2_my_copy.py` on the PC (or export the whole
   Choregraphe project with *File > Save project as...*). The ZIP only
   contains the old v1 bridge (`tools\old_versions\choregraphe_bridge_v1.py`); the v2
   that worked on your robot exists only in your Choregraphe project.
3. Create a new box: right-click in the flow diagram > *Create a new box >
   Python...*, name it `JustNaoBridge`, keep one `onStart` input
   (bang) and one `onStopped` output.
4. Double-click the box and **replace the whole script** with the content of
   `choregraphe_bridge.py` (the class must stay `MyClass(GeneratedClass)`).
5. Link the diagram's start (left arrow) to the box's `onStart`.
   Only **one** bridge box may run at a time (one port 8766 per robot):
   delete or unlink the old v2 box.
6. Press **Play** (green arrow). Open *View > Log viewer* and check:
   ```
   Just Nao bridge v3 pret : 0.0.0.0:8766
   ```
7. From PowerShell on the PC:
   ```powershell
   Test-NetConnection 192.168.2.121 -Port 8766        # TcpTestSucceeded : True
   ```

The behaviour keeps running while Choregraphe stays connected. Pressing Stop
in Choregraphe stops the bridge and the music.

### Optional: run the bridge without Choregraphe open

Choregraphe can install the project on the robot (*Robot applications* panel,
*Package and install current project*). Then start it from the robot's
applications. Do this only after the bridge was validated with Choregraphe open.

---

## 2. Configuration (top of `choregraphe_bridge.py`)

| Setting | Default | Meaning |
|---|---|---|
| `BIND_HOST` | `"0.0.0.0"` | listen on the robot's network interfaces. **Do not put back `127.0.0.1`**: the PC could not reach the bridge (this was the v1 problem). |
| `PORT` | `8766` | must match `BRIDGE_PORT` (config.py or Settings window) |
| `ALLOWED_CLIENTS` | `("127.", "192.168.2.")` | IP prefixes allowed to send commands. For a stricter setup use your PC's exact IP, e.g. `("127.", "192.168.2.50")`. `()` = everybody: avoid. |
| `TTS_LANGUAGE` | `"English"` | NAO's voice language (must be installed on the robot) |
| `TTS_VOLUME` | `0.85` | speech volume |
| `ALLOW_LEG_MOTION` | `False` | leg joints (Hip, Knee, Ankle) are refused |
| `MIN_MOVE_DURATION` | `0.3` s | shortest transition accepted for a `move` |
| `MOTION_LOCK_WAIT` | `1.0` s | a second motion waits this long, then gets "robot busy" |
| `DEFAULT_AUDIO_PATH` | `/home/nao/music/macarena.mp3` | only for old app versions (v2 `audio_play` without a path) |

On the PC side, the robot address is configurable without editing code:

```powershell
# one run
.\.venv\Scripts\python.exe main.py --choregraphe --ip 192.168.2.121 --bridge-port 8766 --ui hmi
```

or in the game window, *Settings > Robot connection* (saved in
`results\settings.json`, applied immediately), or permanently in `config.py`
(`NAO_IP`, `BRIDGE_PORT`).

---

## 3. Protocol

One TCP connection = one request line, one answer line (UTF-8 JSON):

```
-> {"cmd": "play", "names": ["LShoulderPitch"], "times": [[0.5, 1.0]], "keys": [[-1.0, 1.2]]}
<- {"ok": true, "result": "OK"}
<- {"ok": false, "error": "robot busy with another motion"}
```

| Command | Parameters | Takes the motion lock? |
|---|---|---|
| `ping` | – | no; answers `"pong-physique-v3"` |
| `status` | – | no; version, fallen, motion_busy, audio_playing, awake, posture, battery |
| `wake`, `rest` | – | yes |
| `posture` | `posture`, `speed` | yes |
| `move` | `names`, `angles`, `duration` | yes |
| `play` | `names`, `times`, `keys` (angleInterpolation, absolute) | yes; answers `"stopped"` if Stop arrived |
| `stop` | `names` (optional) | **no** – kills the motion tasks immediately |
| `emergency_stop` | – | **no** – motion, music and speech |
| `say` | `text` | no (blocking until spoken) |
| `stop_speech` | – | **no** |
| `leds` | `rgb`, `duration` | no |
| `audio_load` | `path` (file **on the robot**) | no; returns `id`, `duration` |
| `audio_play` | `id` or `path`, `volume`, `start` | no; stops any previous track first, plays in a worker thread |
| `audio_stop` | – | **no** |
| `audio_status` | – | no |

Why it matters: in v1/v2 a single lock serialised every command, so a Stop
sent during a 66 s dance waited for the dance to end. In v3 every connection
has its own thread and urgent commands never wait.

---

## 4. Security

- The bridge moves a physical robot: keep it on the trusted local network,
  never forward port 8766 to the Internet, keep `ALLOWED_CLIENTS` narrow.
- Rejected clients are logged: `Client refuse : <ip>`.
- After a fall (`robotHasFallen`), motion and music stop and every motion
  command is refused until a `wake`; the app shows "NAO fell! Put it back on
  its feet, then press Wake up or Rest". **Nothing stands the robot up
  automatically.**

---

## 5. Upgrading from v1 / v2

| | v1 (in the ZIP) | v2 (your Choregraphe project) | v3 (this package) |
|---|---|---|---|
| address | 127.0.0.1:8765 | 0.0.0.0:8766 | 0.0.0.0:8766 |
| ping | `pong` | `pong-physique-v2` | `pong-physique-v3` |
| Stop during a motion | waits | waits (single lock) | immediate |
| music | none | fixed file, from 0:00 | file chosen by the choreography, preloaded, stoppable, no overlap |
| client filter, leg refusal, fall lock | no | no | yes |

The app still talks to a v2 box (it logs a warning: music is the box's fixed
file and Stop may wait). With v2, the Macarena choreography is played against
the full song from 0:00 while the moves were written for the 0:48–1:54 excerpt:
upgrade to v3 for a synchronised dance.

---

## 6. Quick diagnosis

```powershell
ping 192.168.2.121
Test-NetConnection 192.168.2.121 -Port 8766
.\.venv\Scripts\python.exe -c "from robot.choregraphe_robot import ChoregrapheRobot as R; r=R(host='192.168.2.121', port=8766); r.connect(); print(r.bridge_version, r.latency_ms, r.status())"
```

The last command moves nothing; it prints the bridge version, the round-trip
time in ms and the robot status. More in docs/TROUBLESHOOTING.md.
