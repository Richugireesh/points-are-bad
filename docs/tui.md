# TUI Guide

The `points-are-bad` command launches a Textual-based TUI with a sidebar for navigation and a main content area.

## Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Header: "Points are Bad"                                   │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│  Sidebar     │  Main content area                           │
│              │  (changes based on selected view)            │
│  1 Dashboard │                                              │
│  2 Standings │                                              │
│  3 Race Pts  │                                              │
│  4 Predict   │                                              │
│  ────────    │                                              │
│  5 Admin     │                                              │
│              │                                              │
├──────────────┴──────────────────────────────────────────────┤
│  Footer: key hints                                          │
└─────────────────────────────────────────────────────────────┘
```

## Global keybindings

| Key | Action |
|---|---|
| `1` | Go to Dashboard |
| `2` | Go to Standings |
| `3` | Go to Race Points |
| `4` | Go to Predictions |
| `5` | Go to Admin |
| `q` | Quit (auto-saves data) |

---

## Dashboard

Season overview at a glance.

- **Next race**: name and date of the next upcoming race without results.
- **Standings**: all players ranked by score, with gap-to-lead and medal emojis (🥇🥈🥉).

Refreshes automatically when you switch to this view.

---

## Standings

Full season standings table.

| Column | Description |
|---|---|
| `#` | Rank (medal for top 3) |
| Player | Player name |
| Points | Total season points |
| Gap to lead | Points behind the leader (`─` for leader) |

The subtitle shows how many races have been counted.

---

## Race Points

View per-player scores and position breakdowns for any completed race.

1. Click **Select Race** → pick from the list of races with results.
2. The view shows:
   - **Score summary**: each player's total points, with a mini `█` progress bar.
   - **Per-player breakdown**: each position with a green ✓ (correct) or red ✗ (wrong) and what was predicted vs. what actually happened.

---

## Predictions

Enter or update a player's prediction for an upcoming race.

1. Click **Select Race** → pick an upcoming race without results.
2. Click **Select Player** → pick a player.
3. Click **Pick Drivers →** to open the [Driver Picker](#driver-picker).

If the player already has a prediction, a confirmation dialog appears before overwriting. The existing prediction is shown below the buttons.

### Driver Picker

Full-screen interactive picker for selecting up to 10 drivers.

```
┌──────────────────────────────────┬────────────────────────┐
│  Drivers                         │  Your Picks            │
│                                  │                        │
│  ── McLaren                      │  P 1  NOR  Lando Norris│
│  [ 1]  NOR  Lando Norris         │  P 2  VER  Max Verst.. │
│  [ 2]  PIA  Oscar Piastri        │  P 3  ─ ─ ─            │
│  ── Ferrari                      │  ...                   │
│  [ 3]  LEC  Charles Leclerc      │                        │
│  ...                             │  2/10 picked           │
│                                  │  ────────────          │
│                                  │  [Save F10]            │
│                                  │  [Cancel Esc]          │
└──────────────────────────────────┴────────────────────────┘
```

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate driver list |
| `Enter` | Toggle driver in/out of picks |
| `Del` / `Backspace` | Remove last pick |
| `F10` | Save picks |
| `Esc` | Cancel without saving |

- Selecting a driver who is already in your picks **removes** them.
- Driver abbreviations are coloured in their team's F1 livery colour.
- You can save with fewer than 10 picks (missing positions score +1 each at race time).

---

## Admin

Manage all game data from one panel.

### Players

| Button | What it does |
|---|---|
| Add Player | Prompt for a name; appended to the player list |
| Remove Player | Select a player from a list; confirm before deleting |

### Race Results

| Button | What it does |
|---|---|
| Auto-Fetch Results | Select a race → fetches from FastF1/OpenF1 in the background |
| Manual Entry | Select a race → opens the manual entry screen |

**Auto-Fetch** runs on a background thread so the TUI stays responsive. A notification appears when the fetch completes (or fails). The status widget shows the result inline.

**Manual Entry screen:**

Type one driver name per line and press Enter. The P1–P10 grid fills in live. Press **Save** when done, or **Clear** to start over. Esc to go back without saving.

### Schedule

| Button | What it does |
|---|---|
| Sync from FastF1 | Fetch current-season schedule; add new races and update dates |
| Add Race | Prompt for name and date; appends a blank race |
| Remove Race | Select from list; confirm before deleting |

Schedule sync also runs on a background thread.

---

## Colour scheme

| Element | Colour |
|---|---|
| Header / accents | `#e10600` (F1 red) |
| Section headers | `#00d2be` (Mercedes teal) |
| Background | `#0d0d1a` (dark navy) |
| Sidebar / panels | `#13131f` |
| Cards | `#1a1a2e` |
| Correct prediction | `#27ae60` (green) |
| Wrong prediction | `#e74c3c` (red) |

Driver abbreviations are rendered in each team's official livery colour.
