---
name: fe-harness
description: Playing and testing Falcon's Eye (FE v1.06) through sr-harness -- the two-level menus, joining (race, county), the monthly turn and its debt, State of the County, world-wide messages, the mail reader that wraps round, rankings that need SCORES, the ">>Unknown<<" sender, FE's idle emission cycle, and the open questions (inactive-county deletion, what carries scores). Use when driving FE as a player, writing an FE scenario, or explaining why FE did not send or show something. Contrasts with BRE throughout.
---

# Falcon's Eye under sr-harness

Read `driving-dos-doors` first. FE is BRE's sibling: same author, door file,
RESET walk, BBS.CFG, nodes file and line editor. Almost every *difference* is
a place where a BRE-shaped walk goes wrong, so the BRE contrast is spelled out
throughout. The walk is `sr_harness/fe.py`. This was mapped by hand on v1.06 on
2026-10-13, and everything below was observed unless it's marked **open**.

## The walk

```python
from sr_harness import Install, fe
p = fe.Player(Install(path, "FE.EXE"), county="County Two", user="PILOT TWO").start()
p.entry_text               # what was shown on the way in, including international mail
p.status()                 # State of the County, parsed
p.play_turns(2)            # two months, every expense paid, nothing else
p.send_world_message("hi") # international, every nation
p.rankings("players_by_score")    # needs SCORES; see below
p.read_messages()
p.quit()                   # county, then the outer menu; outbound runs
```

## Two levels of menu

```
──────[Falcon's Eye]──────            ──────────[Main Menu]──────────────────────
(1) Join Game  /  Enter Game          (-) Take Turn         (5) Commerce        (I) International Room
(2) See Scores                        (1) Labor             (6) Foreign Affairs (T) Technology
(3)/(4) Today's/Yesterday's News      (2) Defense           (7) Communications  (*) Private Chambers
(5) Game Bulletins  (G) Game Setup    (3) City Improvements (8) War Room        (0) Quit
(H) Help  (I) Instructions  (0) Quit  (4) Mystic Circle     (C) Council Room
```
- The outer menu isn't the game. (1) reads Join Game for a newcomer and
  Enter Game afterwards. Quitting the county lands on the outer menu, which
  has to be quit as well (`Player.quit` does both).
- **The prompt is pre-filled with the default:** `Choice> Labor`,
  `Choice> Join Game`, `Choice> Quit`. A prompt match can't tell which menu
  you're in, so FE answers are keyed on the menu title (`Driver.menu`).
- The bottom bar `PILOT TWO │ A │ County Two │` is furniture. It carries the
  county's letter once you've joined.
- **The first visit to any menu shows its help page and pauses.** That
  happens once per session, so the second visit is different from the first.
- (G) Game Setup shows the league's rules: months per year (turns per day),
  protection months, start-up resources, and the attack limit.

## Joining

Join Game → hints (`Continue? (Y/n)`) → **Race Selection** (20 races; the
default is **(0) Quit**, so a bare Enter abandons the join) → `Select this
race? (Y/n)` → `What will be the name of your County?` → `Name Your County
X? (Y/n)` → main menu. The manual suggests Humans for a first county, since
they have no adjustments.

## A turn is one key

Unlike BRE's phase-by-phase turn, FE's main menu is a hub. You manage things
from it, and `(-) Take Turn` plays one **month**. A day is a year of
`Months per Year` months (8 by default).

```
* You have unemployed people; you may wish to employ them first!
Take your next turn? (y/N)            <- the default is NO whenever there are warnings
You are playing month #1 out of 8 months in the year 0.
...Monthly County Report...
The basic 25% requirement of 63 silver and 3 bushels of food was paid.
Give how much silver? (189; 189)      <- the default pays it all
Give how much food? (12; 12)
```
- **Taking every default never plays a turn.** You must answer Y explicitly.
- **FE has debt and BRE doesn't.** 25% of each month's expenses is taken.
  Whatever you don't pay of the rest accrues interest, as a loan. Private
  Chambers has an auto-pay toggle.
- At numeric prompts, `>` means the maximum, and `k`/`m` add 3 or 6 zeros.
- `Player.month` is `(month played, months per year)`, parsed from the turn.
  **Open:** the screen shown when the year's months are used up.

## Status: (C) Council Room → (A) State of the County

```
State of the County of Harness County founded by Humans in month #0.
Housing Land:    100 Acres
Total People:    100              Unemployed:    100
Approval:         50%
Silver:          15,000           Food:              2000
Stone Blocks:       200           Weapon Stores:      400
Runes:               25
Quality Rating: 50%
Total Offense: 200 Swords       Total Defense: 200 Shields
The county has 20 months of protected status left.
There are 8 months per year.
```
The Council Room also has Budget, Agriculture, Labor, Improvements, Mystic,
Research and War reports. Score and net worth aren't on this screen. They're in
the `?` list under Write Messages, and in SCORES' bulletins.

## Mail

- `(7) Communications → (2) Write Messages` is local, to this board's
  counties (`(A-Y,Z=All,?=List) Send to:`).
- **International** mail is `(I) International Room → (8) Send Message`,
  then `(1) Single Nation`, `(2) Multiple Nations`, `(3) World-Wide` or
  `(4) National President`. It uses the same line editor as BRE (`1>`,
  `/S`).
- **Incoming international mail is shown on entry**, before the main menu,
  in a box ending `(Reply, Delete, Ignore, or Quit)`. In BRE it waits until
  you press Play Game.
- **The reader's two non-destructive answers are both traps:**
  - **Quit means "Quit Reading".** No later message is shown.
  - **Ignore leaves the message unread and moves on**, and after the last
    message the reader **wraps round to the first**. Everything is still
    unread, so it loops forever.

  `fe.reader()` answers I until a message comes round again, then Q, so each
  message is shown exactly once.
- Messages Ignored or Quit stay unread, and `(7) → (1) Read Messages` shows
  them again. That's another difference from BRE, where IP mail never appears
  there.

### `Message From: >>Unknown<< (Board One)`

A board only knows another board's county once traffic has told it.
Observed, and pinned by `test_fe_mail_from_a_county_the_other_board_has_not_heard_of`:

1. Board 1 founds County One, plays and sends world-wide mail **in one
   session**. Then it runs `RECON` and OUTBOUND.
2. Board 2 ingests both packets (mail first) in one FULL and shows
   `Message From: >>Unknown<< (Board One)`.
3. Board 1 sends more mail in a later session. Board 2 ingests it, and on
   that visit **both** messages show `Message From: County One (Board One)`,
   including the first, which is still stored.

So the sender's name is looked up when the message is **shown**, not when it
arrives, and the `>>Unknown<<` heals itself later. It hardly ever shows in
real play, because a brand-new county rarely sends world mail in its first
session. If you see one, the sender's county hadn't been announced yet. It
isn't corruption.
**Open:** which record taught board 2 the county. `RECON` + OUTBOUND in
step 1 wasn't enough for the first visit.

## Rankings need SCORES

`(I) → (1) View Rankings` has the same 1–8 menu as BRE's IPScores
("Nations" for "Planets"), and players appear only under 5–8. **But the
reports are built by `FE.EXE SCORES`** (it writes `BULLETIN/ply*.txt` and
`bbs*.txt`), not by ingesting packets. A board can have ingested another's
counties and still show empty rankings until SCORES runs there. On a hub
that's `scores_command = "FE.EXE SCORES"` in the league's config.

**Open: what carries a score between boards.** In one run, board 1's
day-one packet was still uncollected, so outbound rewrote it in place with
the session added. Board 2 then ranked County One (score 50) after SCORES.
With every packet carried promptly, County One was missing from board 2's
rankings in every later run (two in the live test, one in a separate
experiment), RECON or not. Nothing in eight
idle days of `/DETAILED` output was a score or player-list record.

## When FE emits

Measured on a two-board league stepped with REDATE (board 1 had two
counties on day 0, board 2 none; packets carried daily):

| game day | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| board 1 emits | yes | yes | – | – | yes | yes | – | – |
| board 2 emits | yes | yes | – | – | yes | yes | – | – |

- Idle traffic is only `Config Update`, `Recon Update`, `Recon Request`,
  `Routing List` and `Time Check`, on a **two-days-on, two-days-off** cycle.
  The emitting days of BRE's idle cycle (gitea #86) also shift with the dates
  chosen, so treat this as one sample, not a rule. As you've seen in
  production, FE sends little for player-list changes alone. It takes a real
  event (mail, an attack, a trade) to make a packet worth sending.
- **FE's first PLANETARY after RESET is game-day one**: `planet.fe`,
  `routes.dat` and the rest appear then, and it emits packets plus
  `fenodes.<league>`. `ids.dat` appears only once someone joins.
- **Outbound rewrites a pending packet in place.** If `.001` hasn't been
  collected, the next outbound adds to it under the same name, and otherwise
  it writes `.002`. FE's sequence numbers are sparse in production too, with
  steps of 1 to 45.
- `RECON` only queues a recon. The next outbound run packs it.

## Inactive counties (**open**)

`RESOURCE.DAT` has `DeletionDays` ("days before deleting an inactive
player", default 7). On the rig it **didn't fire on REDATE days**. An
unplayed county survived 8 faked days at the default, and 3 days with
`DeletionDays 1`. So whatever date FE uses for inactivity isn't the INT 21h
GetDate that REDATE fakes, or "inactive" means something else. Production
sysops see unplayed counties deleted aggressively in real time. Reproducing
that needs real elapsed days, or finding the date source.
