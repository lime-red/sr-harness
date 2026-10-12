# sr-harness

Drive Solar Realms' BBS door games — **Barren Realms Elite** and **Falcon's
Eye** — under dosemu2 on Linux, either unattended (maintenance) or as a player
sitting at the keyboard.

It was extracted from the live test rig of [nova-hub](https://gitea-hl.taild204f.ts.net/lime/nova-hub),
where it plays real installs to generate inter-BBS traffic. Nothing in it knows
about nova-hub.

The comments in the code carry most of the value. Nearly every rule in them was
paid for by a walk that hung or wandered off, so read them before you change
how prompts are answered, and before you port it.

## Requirements

- Linux with **dosemu2** (`/usr/bin/dosemu`). It is tested on
  `2.0~pre9-10228`. The pty handling is POSIX-only, so it won't run on Windows
  as it stands.
- Python 3.12+ and `pyte`.
- A game install. The games aren't included.

```sh
pip install git+https://gitea-hl.taild204f.ts.net/lime/sr-harness.git@v0.1.0
```

## Use

```python
from pathlib import Path
from sr_harness import Install
from sr_harness import bre

game = Install(Path.home() / ".dosemu/drive_c/bbs/doors/b900n02", "BRE.EXE")

# unattended
game.run("PLANETARY /DETAILED", log="planetary.log")

# as a player
p = bre.Player(game, realm="Node Two", user="TEST PILOT 02").start()
before = p.status()                      # parsed (2) See Status
p.play_turns(1)                          # every default: the do-nothing turn
p.send_ip_message("hello from node two")
print(p.ip_scores("players_by_score"))
p.quit()                                 # quit properly; see below
```

### Exploring a game by hand

`hold` keeps a session alive between commands. That's how a game nobody has
scripted yet gets mapped: press a key, read what came back, and choose the next
one.

```sh
sr-harness hold fe --install ~/.dosemu/drive_c/bbs/doors/f900n02 --exe FE.EXE --user "TEST PILOT 02" FULL
sr-harness keys fe "Y"
sr-harness keys fe "2" --said     # --said: everything printed, not just the last screen
sr-harness release fe             # kills dosemu -- quit in-game first if outbound matters
```

`observe` prints the screen every few seconds instead, and `run` does an
unattended command.

## Layout

| module | what it is |
|---|---|
| `session.py` | `DosSession`: a pty with an explicit 80x25 size, and a `pyte` screen |
| `run.py` | headless run to a transcript; returns dosemu's own exit code |
| `install.py` | `Install`: batch files, `-K/-E` invocation, door file, `inuse.flg`, REDATE |
| `driver.py` | `Driver`: the prompt-answering loop both games share |
| `bre.py` | the BRE player: prompt table, status parser, turns, IP mail, IPScores |
| `dospath.py` | the 8.3 guard |
| `cli.py` | `sr-harness` |

## Things that will bite you

These are all in the code comments where they apply. They're listed here so
they're recognisable before you hit them.

- **Answer the live prompt, never the history.** The raw byte stream is
  append-only, so a prompt seen once matches forever and its answer re-fires
  into whatever comes next. That's how a walk once typed `Y` into the realm-name
  field. `Driver.prompt` is the last non-empty screen line that isn't
  furniture.
- **An answer may re-fire only once the whole screen has changed.** If you key
  that on the prompt line instead, the walk stalls on the second page of
  anything, because every page ends in the same `Continue? (Y/n)`.
- **Never press bare Enter to "settle" a screen.** At a menu it selects (1) Play
  Game.
- **Quit through the game's own menu.** FULL packs the day's outbound mail on
  the way out. A killed session also leaves `inuse.flg` behind, and every later
  run then exits 1 without printing why. `Install` clears it before and after
  each run.
- **dosemu swallows a lone ESC.** Press it repeatedly: `DosSession.mash`.
- **TERM=dumb kills dosemu**, and a pty with no window size breaks DOS's 25-line
  layout. `DosSession` pins both.
- **Use `dosemu -K <dir> -E <BATCH>`.** The bare-path form remaps C:, so the
  batch's `CD` fails, the game never starts, and dosemu exits 0 anyway.
- **8.3 or nothing.** A path component over 8.3 in `BBS.CFG` makes the games
  ingest nothing, silently. `Install` refuses such a `dos_path`.
- **Faking the date:** `libfaketime` deadlocks dosemu2. Use `REDATE.COM`
  (`Install(redate=...)`, then `run(..., date="YYYYMMDD")`).
- **BRE's player name must be unique across the league** when duplicate checking
  is on. Otherwise the join is refused and you never reach the main menu.
- **BRE interplanetary mail is only shown at the start of play**, never under (6)
  Read Messages. `Player.play_turns` keeps it in `turn_text`.

## Tests

```sh
uv run pytest
```

The unit tests need no dosemu and no game.

## License

MIT
