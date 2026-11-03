# Old versions (reference only, not used by the app)

| File | What it is |
|---|---|
| `choregraphe_bridge_v1.py` | bridge v1 from the team ZIP: 127.0.0.1:8765, `ping` -> `pong`, no audio, single lock |
| `choregraphe_robot_v1.py.txt` | PC client that matched v1 (was `robot/choregraphe_robot.py.bak`) |
| `choregraphe_robot_v2_audio.py.txt` | PC client that sent `audio_play` without parameters (was `robot/choregraphe_robot.py.bak_audio`) |
| `choreographies_v1/` | the dances before the 2026-11-02 rebuild (first composer) |
| `choreographies_v4/macarena`, `nao_party` | dances of the v4 rebuild: **refused** by the balance check since v5 (dynamic part 19 mm) |
| `choreographies_v4/echauffement_tombe` | v4 warm-up, **made NAO fall**: refused by the balance check (also kept in `tests/fixtures/echauffement_v4_fell`) |
| `choreographies_v4/echauffement_lent` | Med's cautious warm-up (no fall, but too slow); passes every check, can be restored by copying its two files into `choreography/library/echauffement/` |

The bridge v2 (`pong-physique-v2`, 0.0.0.0:8766) that ran on the robot was
not in the ZIP: it only exists in the team's Choregraphe project. Keep a copy
of it before pasting the v3 (docs/CHOREGRAPHE.md, step 2).
