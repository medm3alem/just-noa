# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `[ERROR] No answer from the Choregraphe bridge 192.168.2.121:8766 ... refused` at start-up | the bridge box is not playing, or another port | Play the box in Choregraphe, check the log line `Just Nao bridge v3 pret : 0.0.0.0:8766`, check `--bridge-port` / Settings |
| `... timed out` | wrong IP, PC on another network, firewall | `ping 192.168.2.121`; press NAO's chest button to hear its IP; same Wi-Fi/subnet; `Test-NetConnection 192.168.2.121 -Port 8766` |
| `client not allowed: 10.x.x.x` | PC IP not in `ALLOWED_CLIENTS` | add your PC's prefix or exact IP in `choregraphe_bridge.py`, paste again, Play |
| Choregraphe log `Serveur : [Errno 98] Address already in use` | an old bridge box (v2) still runs on 8766 | stop every behaviour (Stop button), keep a single bridge box, Play again |
| Log `[ATTENTION] Passerelle ancienne (pong-physique-v2)` | the robot still runs the v2 box | paste the v3 `choregraphe_bridge.py` (docs/CHOREGRAPHE.md §1) |
| Music does not match the moves (starts in the middle of the song) | v2 bridge plays its fixed full MP3 | install v3 and copy `macarena_extrait.wav` (docs/AUDIO_MACARENA.md) |
| `audio file not found on NAO: /home/nao/music/...` | file not copied | `scp` commands in docs/AUDIO_MACARENA.md §1 |
| Music a bit early/late compared with the arms | constant start-up delay | measure with *Sync calibration*, set `sync_offset` |
| No sound but dance runs | NAO volume low or muted | press the chest button / head buttons, or `ssh nao@192.168.2.121 "qicli call ALAudioDevice.setOutputVolume 70"` |
| NAO does not speak English | English voice not installed or language not set | check Choregraphe log `Voix : reglage impossible`; install the English language pack (robot settings page) |
| `robot busy with another motion` | a second motion command while one runs | wait for the end, or press Stop; normal protection |
| `leg motion disabled on the bridge` | choreography moves Hip/Knee/Ankle | upper-body choreographies only (or set `ALLOW_LEG_MOTION = True` knowingly) |
| "NAO fell! Put it back on its feet..." | fall detected | put NAO back on its feet or lay it down safely, then Wake up or Rest (no automatic stand-up) |
| Choreography "refused for safety" | joint limit or speed above the safe ratio | `.\.venv\Scripts\python.exe main.py --fake --valider` lists the faulty keyframes; fix them in Choregraphe |
| Camera "unavailable" | used by another app (Teams, browser), wrong number, Windows privacy | close the other app; try `--video 1`; *Settings > Privacy > Camera > allow desktop apps* |
| "Pose model missing" | `models\pose_landmarker_full.task` absent | `.\.venv\Scripts\python.exe tools\download_model.py` |
| `ModuleNotFoundError: mediapipe` / `cv2` | dependencies installed in another Python | always use `.\.venv\Scripts\python.exe`; reinstall `-r requirements.txt` |
| `ImportError: DLL load failed` with cv2 | both opencv-python and opencv-contrib-python installed | `.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python opencv-contrib-python` then reinstall requirements |
| MediaPipe does not install | Python 3.14 or 32-bit Python | use 64-bit Python 3.12 (`py -3.12 -m venv .venv`) |
| `py -3.12` not found | Python 3.12 not installed / not registered | install from python.org (64-bit), or call its full path |
| "Step back so I can see your whole upper body!" all the time | too close to the camera | 2–3 m away, shoulders, elbows and wrists visible |
| Score always low although the moves are right | wrong side matching or depth noise | Settings: Matching = Automatic; untick 3D scoring |
| NAO keeps talking after I left | — | Skip comment (main menu or Results), or Rest (waits for the sentence) |
| Window tests skipped | no display (remote shell) | run the tests from a normal desktop session |

Logs: the operator log (main menu, French) records every robot command
error; the Choregraphe *Log viewer* shows the bridge side. Session reports
are in `results\sessions\` (JSON, one file per game).
