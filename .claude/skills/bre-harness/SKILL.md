---
name: bre-harness
description: Playing and testing Barren Realms Elite (BRE v0.988) through sr-harness -- the player walk, the main menu and daily-turn sequence, reading status, sending and reading interplanetary mail, IPScores, and the game behaviours that make inter-BBS tests fail mysteriously (mail only at start of play, idle leagues going quiet, new realms announced only by recon, checksummed GAME.DAT, MIT). Use when driving BRE as a player, writing a scenario that needs BRE traffic, or explaining why BRE did not send or show something.
---

# Barren Realms Elite under sr-harness

Read `driving-dos-doors` first for the walk rules shared with FE. Everything
here was observed on v0.988. The walk itself is `sr_harness/bre.py`, and its
comments carry the same facts at the line where they apply.

## The walk

```python
from sr_harness import Install, bre
p = bre.Player(Install(path, "BRE.EXE"), realm="Node Two", user="TEST PILOT 02").start()
p.status()                 # {'turns', 'score', 'gold', 'bank', 'food', ...}
p.play_turns(1)            # every default: the do-nothing turn
p.send_ip_message("hi")    # interplanetary, to all planets
p.letter                   # "A": this realm's letter on its board
p.send_message("B", "hi")  # local mail, to realm B on this board
p.read_messages()          # (6): local mail, through the reader
p.ip_scores("players_by_score")
p.quit()                   # always: outbound runs on the way out
```

**Getting in:** ANSI → IBM characters → (first time) `Name your Realm`, then
`Name Your Empire` → `Would you like Instructions` (N) → main menu. A name
already playing on another board is refused with `Duplicate User Found on BBS
#n` if the league checks duplicates. There's no way past that, so use a
different name.

**Main menu:**
```
(1) Play Game             (8) Game Bulletins
(2) See Status            (9) InterPlanetary Ops
(3) See Scores            (A) Game Instructions
(4) See Today's News      (B) Help Database
(5) See Yesterday's News  (P) Preferences
(6) Read Messages         (0) Quit
(7) Send Messages
Choice>
```
Anchor on `(2) See Status`, not `Choice>`. A bare Enter here is (1) Play Game.

## A turn is a sequence

(1) Play Game walks every phase in order: Diplomacy, Status, Payment/Food
Market, Covert Ops, Bank, Spending, Attacks, Trading, IP Ops and Messages.
Then it asks `Do you wish to continue?`. **Y plays the next turn and N ends
play.** That's the only turn counter, so a session is one trip through Play
Game, with the answer counting down. Taking every default is the do-nothing
turn: `0` out of each submenu, and Enter at each `How much will you give?
(40; 40)`. A do-nothing turn still moves the score.

Turns per day come from the league config (8 on the rig). If fewer turns were
played than asked for, `play_turns` raises. The realm has most likely run out
for the day, though the exact screen BRE shows then hasn't been captured.

## Status

`(2) See Status`:
```
-*Test Realm*-
Turns: 8
Score: 0
Gold: 1000
Bank: 251,272            <- only when non-zero
Population: 100 Million (Tax Rate: 15%)
Popular Support: 100%
Food: 1000
```
- **BRE leaves a line out instead of printing zero.** A missing `Gold:` or
  `Bank:` line means 0. Don't extend that to other fields, or a parse failure
  turns into a plausible number.
- **Gold and food are never negative.** The only debt is a bank loan, and
  repaying it is the player's choice. Gate decisions on affordability floors,
  not `< 0`.
- Parse the last occurrence of each field. VGA repaints leave earlier copies
  in the history.

## Mail: two kinds, shown in two places

- `(7) Send Messages` is **local**, to realms on this board:
  `(A-Y,Z=All,?=List) Send to:` takes the realm's **letter and Enter** (`?`
  lists realms with their letters; a realm's own letter is in the status bar,
  `NAME │ A │ Realm │`). Then the line editor, `/S`, and `Do you wish to send
  another message? (y/N)`. It never becomes a packet.
- **Local mail is read under (6) Read Messages, in the same reader as IP mail**
  (`[R] Reply, [D] Delete, [I] Ignore, or [Q] Quit>`). A walk that only pages
  and answers `Choice>` hangs on it. I leaves the message for next time,
  Q stops reading, and D deletes. `read_messages()` answers I until a message
  repeats, then Q, the same as FE's reader (FE's I wraps round forever; with
  one message BRE's returned to the menu, and more than one is untested).
- **Interplanetary** mail is `(9) InterPlanetary Ops → (7) Send Message →
  (3) All Planets`, then the line editor (`1>`, `/S` saves, `/A` aborts).
- **Incoming IP mail appears only at the start of play.** Press (1), and
  after any local messages each one opens in a reader:
  `[R] Reply, [D] Delete, [I] Ignore, or [Q] Quit>`. It's **never** under
  (6) Read Messages. A walk that only knows `Choice>` hangs on that reader.
  Answer Q, and assert on `Player.turn_text`. This is why a receiving board
  has to *play a turn* to prove that mail arrived.

## IPScores

`(9) → (1) View IPScores` opens a menu of reports, not a listing:
(1)–(4) Planets by score/worth/land/density and (5)–(8) Players by the same.
Realms appear only in the Players reports, because the Planets reports are
per-board totals.

## Why didn't it send anything?

- **An idle league emits on game days one to three, then goes quiet.**
  Maintenance still runs and completes. That silence isn't a fault, and a
  test needing day-four traffic needs a player.
- **Emission over faked days depends on which dates you pick** (gitea #86):
  [1,0,0,0,1,0] at +1..6, but [1,0,1,0,0,1] at +10..15. Don't hard-code
  "day N emits".
- **One packet per day isn't a limit.** A second PLANETARY the same day emits
  nothing, but `REQUEST` (a recon request to every board) or `RECON` queues
  traffic, and the next OUTBOUND packs it under the next sequence number.
  `RECON` alone writes no file.
- **A new realm is invisible to other boards until a recon carries it**
  (`RECON` then OUTBOUND, or the next scheduled recon).
- **IP-ops attacks unlock only after a realm has played a turn.**
- Idle BRE uses **two sequence numbers per day** and writes at the second
  (`.002`, `.004`). With players it numbers densely.

## Fixtures and game state

- **GAME.DAT is integrity-checked.** Patch gold or bank in it and BRE asks
  the player to `Name your Realm` again. Back it up before experimenting.
- **A fixture expires the day after capture.** A day-old fixture restores
  byte-identically, but its first packet is `.002` and `.001` assertions fail.
  The start date is inside GAME.DAT, and only REDATE moves what the game sees.
- **To make attacks testable:** run `BRE EDITOR` on the host board and set
  Turns of Protection 0, Individual Attacks/Day 10, and Days for Lost Attacks
  1. Deliver the host's Configupdate before anyone plays.
- **Max 10 terrorist ops per day.** Special ops and Gooies cost tens or
  hundreds of millions, so you can't afford them on a fresh rig realm. Decode
  those from real traffic instead.
- **MIT (Missing In Transit):** the attacker writes an attack off in its
  first run on the due date (its rollover). That run burns a sequence number
  before writing, and it imports inbound *before* "Checking for Any Lost
  Attacks", so a result already waiting is still accepted. Production boards
  roll over on their own schedule, not at midnight.

## Packets

Packets are zero-run RLE (`0xFD n` = n zeros) with a CRC-32 per record, not
encrypted. nova-hub's `backend/services/bre_packet.py` decodes them; sr-harness
deliberately doesn't. Message text is player mail, so tools should show its
route and never its body.
