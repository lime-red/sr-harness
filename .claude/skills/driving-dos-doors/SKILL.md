---
name: driving-dos-doors
description: How to drive a Solar Realms door game (Barren Realms Elite, Falcon's Eye) under dosemu2 with sr-harness -- unattended maintenance, an interactive player walk, mapping an unfamiliar screen one key at a time with `sr-harness hold/keys`, building a virgin game, faking the date, and carrying packets between boards with no hub. Use before writing or debugging any walk, when a walk hangs or types into the wrong prompt, or when a dosemu run "succeeds" but nothing happened.
---

# Driving DOS doors with sr-harness

The game-specific skills are `bre-harness` and `fe-harness`. This one covers
what both share. dosemu failures where the game never runs at all (tiny logs,
TERM, exit codes) are covered at length in nova-hub's
`.claude/skills/dosemu-troubleshooting`.

## The pieces

| want | use |
|---|---|
| run a command with nothing to answer (PLANETARY, SCORES, RECON) | `Install(path, exe).run("PLANETARY /DETAILED", log)` |
| play as a person would | `bre.Player` / `fe.Player` |
| poke at a screen nobody has scripted | `sr-harness hold` / `keys` / `screen` / `release` |
| a virgin game from the media zip | `provision.write_bbs_cfg`, `write_nodes`, `gamedata`, `reset` |
| pretend it is another day | `Install(..., redate=REDATE.COM)`, then `run(..., date="YYYYMMDD")` |
| two boards talking with no hub | `mail.carry({1: board1, 2: board2})` |

`tests/test_live.py` builds every one of these from a zip, so read it for the
working sequence.

## Mapping a screen by hand

A walk can't be scripted until someone has done it once, so do that first:

```sh
G=~/.dosemu/drive_c/bbs/doors/srh/f900n01
sr-harness hold fe --install $G --exe FE.EXE --user "TEST PILOT 01" --transcript /tmp/fe.log -- FULL
sr-harness keys fe Y               # prints the screen after the key
sr-harness keys fe "Bob<CR>"
sr-harness keys fe 2 --said        # everything printed, not just the final screen
sr-harness release fe              # kills dosemu: quit in-game first
```

- Prefer the **screen** over `--said`. The games position the cursor, so
  stripped output runs words together and loses layout.
- A held server exits 30 seconds after its game does. If `hold` says the name
  is taken, the old server is still up. Kill it and remove its socket in
  `$XDG_RUNTIME_DIR`.
- Write down every prompt, its default, and what a bare Enter does there. The
  defaults are where walks go wrong.

## Rules for a walk that doesn't wander off

Every one of these came from a walk that hung or did damage.

1. **Answer the live prompt, never the history.** The raw byte stream is
   append-only, so a prompt seen once matches forever and its answer re-fires
   into whatever is up later. That once typed `Y` into a realm-name field.
   `Driver.prompt` is the last non-empty screen line that isn't furniture
   (BRE's `F2=Extra Information`, FE's `NAME │ A │ County │` bar).
2. **An answer may re-fire only once the *whole screen* has changed.** If you
   key that on the prompt line instead, the walk stalls on page two of
   anything, because every page ends in the same `Continue? (Y/n)`.
3. **Order the prompt table specific-first.** `Continue\?` also matches
   `Do you wish to continue?`, and a generic `(Y/n)` fallback eats everything
   placed after it.
4. **Know where you are by the menu title, not the prompt.** `Choice>` is
   every menu's prompt. `Driver.menu` is the last `──[Title]──` line on
   screen, and a prompt entry can require it: `(r"Choice>", "1", r"^Race Selection$")`.
5. **"Done" means the menu was redrawn after your key.** Right after a key
   press, the old menu is still on screen under its title. FE's walks check
   that `[Main Menu]` appears in `text_since(mark)`.
6. **Never press bare Enter to "settle" a screen.** At a menu it picks the
   default, which in BRE is (1) Play Game, so the walk vanishes into a turn.
7. **Clear a pause before sending a menu key.** While `»>Paused<«` is up, the
   key is swallowed.
8. **Answers that must change go in a callable.** A turn countdown, or
   "choose report 5 once, then 0", would loop forever as a fixed answer.
   `answer_until` evaluates a callable when it fires.
9. **dosemu swallows a lone ESC.** Use `session.mash("\x1b", until_gone=...)`.
10. **Keep what the game said with `mark()` / `text_since()`.** The screen
    holds only 25 lines, and the mail you wanted to assert on has scrolled off
    by the time the walk finishes.

## Running the games

- **Use `dosemu -f conf -K <install> -E BATCH.BAT`.** The bare-path form
  remaps C:, so the batch's `CD` fails, the game never starts, and dosemu
  exits 0. `Install.command()` does it right.
- **Pin TERM and set an explicit 80x25 pty.** `TERM=dumb` stops dosemu
  booting, and a pty with no size breaks DOS's 25-line screen.
  `DosSession` and `run()` handle both.
- **The exit code is dosemu's, and it says little.** Judge a run by the
  transcript: the FDPP banner, `Planetary Maintenance Complete`, and for
  inbound, `DeCompress:` lines.
- **`inuse.flg` is the game's mutex.** A killed run leaves it behind, and
  every later run exits 1 without printing why. `Install` clears it before and
  after each run.
- **Quit through the game's menus.** FULL's outbound half runs on the way
  out, and it's what packs the session's mail into a packet.
- **FULL can't run headless.** It's the player path, and it waits on
  `Do you want ANSI Graphics?`. `Install.run` refuses it.
- **`/DETAILED`** works only with INBOUND, OUTBOUND and PLANETARY. It adds a
  `Type: <record> <src>-> <dst>` line per item, which is the only cheap way
  to see what a packet carried.

## Paths: 8.3 or nothing

These are 16-bit Turbo Pascal programs. If any component of the absolute
inbound path in `BBS.CFG` line 4 breaks 8.3, the game silently ingests
nothing: exit 0, every phase marker printed, `PROBLEMS.LOG` empty.
`b900n02` works where `bre_900_n02` didn't. `Install` and `write_bbs_cfg`
refuse such paths. To confirm a suspected case, point line 4 at `C:\IN2` and
rerun.

## Building a game

- `BREDATA -Y` / `FEDATA -Y` rebuild `GAME/` only. Game state comes from
  `<EXE> RESET`, which is interactive. `provision.reset` walks it: confirm,
  ESC-mash out of the Configuration Editor, then answer the league-wide reset
  question, which appears only on the HOST board.
- **RESET deletes stray `.BAT` files.** Write run batches after it.
- **Routing comes from the nodes file's `1 HOST 2 3 4` line.** The media's
  `route.cfg` (`ROUTE * 2`) sends a leaf's mail to itself. Delete it, as
  `write_nodes` does.
- **A door file with COM port 0 is local play.** Without it the game waits
  for a modem. `Install.write_doorfile(user)`.
- **Use a unique player name per board.** With duplicate checking on (a league
  setting), a name already playing elsewhere is refused outright, and the
  session never reaches the menu.
- **Strip the donor tree's state** before RESET: `inuse.flg`, `*.LOC`,
  `DUPES.TXT`, `route.cfg`, and anything in INBOUND/OUTBOUND/BACKUP. FE also
  needs `routes.*`, `BBSINFO.LST`, `PROBLEMS.LOG` and `BULLETIN/*` removed.
- **Linux sees case and DOS doesn't.** FE writes `DATA/` in lower case
  (`game.dat`), BRE in upper (`GAME.DAT`), and the media ships `BBS.CFG` where
  hand-made configs say `bbs.cfg`. Look files up with `install.find_ci`.

## Faking the date

- **Don't use `libfaketime`.** It isn't async-signal-safe, and it deadlocks
  dosemu2's timer handler even at `+0d`.
- **`REDATE.COM`** hooks INT 21h AH=2Ah (GetDate) only, and that's all
  Turbo Pascal asks. `run(..., date=...)` wraps the command in
  `REDATE /iYYYYMMDD` … `REDATE /r`. The dates are absolute.
- **Not everything follows it.** FE's inactive-county deletion doesn't
  trigger on REDATE days (see `fe-harness`). Anything that dates by file
  timestamps or the clock is out of its reach.
- Check with a control: run the same faked day twice. Daily maintenance should
  fire once and be skipped the second time.

## Two boards, no hub

```python
boards = {1: board_one, 2: board_two}       # Install objects
mail.carry(boards)    # each OUTBOUND packet -> its destination's INBOUND
```

Packet names are `<league><game><src><dst>.<seq>` with hex board numbers
(`900f0102.001`). `carry` doesn't check sequences or relay through a HOST.
Sequence numbers aren't dense: a re-run outbound rewrites a still-pending
packet in place under the same number, and idle BRE consumes two numbers a
day. Assert on routes, not on `.001`.
