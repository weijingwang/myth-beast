# Visual Novel Skeleton

```
pip install pygame
python main.py                  # the real game (story.json)
python main.py tutorial.json    # the feature demo
```

You only ever edit **story.json** and the files in **assets/**. `main.py` stays untouched.

## The real game (story.json)

Search story.json for `ART:`, `MUSIC:`, `SFX:` and `TODO:` to find every placeholder. To swap in real art or music, overwrite the placeholder file with the same name. Each placeholder image has its description printed on it.

| File | Status | Used for |
|---|---|---|
| `cutscenes/opening1-3.png` | placeholder | Intro slideshow |
| `bg/hall.png` | **yours** | Intro and prologue (stand-in for their CGs), hallway in chapter 3 |
| `bg/garden.png` | **yours** | Chapter 1 tea party |
| `bg/courtyard.png` | placeholder | Chapter 2 courtyard with a stone pillar |
| `bg/spa.png` | **yours** | Chapter 3 sauna |
| `bg/palace.png` | **yours** | Chapter 4 ballroom |
| `bg/festival.png` | placeholder | Chapter 4 ballroom once the bonfire is lit |
| `bg/ending_normal.png`, `bg/ending_true.png`, `bg/game_over_goat.png`, `bg/game_over_rep.png` | placeholder | Endings and deaths |
| `sprites/claire_neutral / happy / laugh / wtf / frustrated / car_crash.png` | **yours** | Claire (left) |
| `sprites/excelsior_norm / slant / front / front_fire.png` | **yours** | Goat (right): norm = default, slant = about to do something dumb, front = the payoff (reveal stare, prince headbutt, spa door), front_fire = on fire |
| `music/20260924 - gtr.mp3` | **yours** | Title and all chapters for now (search `MUSIC: TODO`) |
| `sfx/*.wav` | placeholder | door_burst, bonk, crash, fire, knock, charge, applause, scream, whoosh, splash |

The other characters (knights, doctor, friends, servant, maid, prince, nobles) are name-only, with no sprite. Stats start at Time 4 and Reputation 4. A stat reaching 0 ends the game, and 6 of the 16 paths survive. Change `"stats"` to rebalance.

**True ending:** a placeholder in the `finale` scene. Every choice already sets a flag (`p1_trust`, `p1_yeet`, `p2_block`, `p2_yank`, `p3_maids`, `p3_save`, `p4_dive`, `p4_let`). List the ones required, and that's the only edit.

## Game feel

- **Typewriter text.** The first click shows the whole line, the next click advances. Speed: `TEXT_SPEED` at the top of main.py.
- **Fast-forward:** hold Tab or Ctrl to zip through text (stops at choices).
- **Speaker focus:** sprites of characters who are not talking dim. This works by name: a sprite file must start with the speaker's name without spaces ("Friend 1" → `friend1.png`, "Knight 2" → `knight.png`, "Claire (thinking)" → `claire_*.png`).
- **Stat popups:** after a choice, "+1 Time / −1 Reputation" floats up and the changed stats turn green or red.
- **Fades:** the screen fades through black on chapter cards, cutscenes, endings, any background change, starting a game and returning to the title. Clicks are ignored mid-fade. Put `"fade": true` on a step to force one (for example the script's `[FADE OUT.]`), or `"fade": false` to turn one off. Length: `FADE_TIME` at the top of main.py.
- **Shake and flash:** a step that plays a sound in `SHAKE_SFX` gives a small shake (`SHAKE_PIXELS`, `SHAKE_TIME`), and `fire.wav` flashes orange (both lists are at the top of main.py). Any step can also say `"shake": true` or `"flash": [255, 255, 255]` itself.

## Tutorial: learn it by playing (tutorial.json)

1. Run `python main.py tutorial.json` and click **About** (text from story.json), then **Back**, then **Start**.
2. Play through. The Guide character explains each feature as it happens.
3. Open `tutorial.json` next to the game. Every feature has a `"note"` on the step that uses it, so you can match what you saw to the JSON that caused it.
4. Replay to see every ending (letters = option picked in phases 1–4, A = top button):

| Path | Ending |
|---|---|
| A A A A, A A B B, B B A A | True ending (plays the ending cutscene) |
| B B B B | Secret ending (flags `rose_bush` + `goat_fire`) |
| A B … | Goat death in phase 2 (Time hits 0) |
| B A … | Reputation death in phase 2 (Rep hits 0) |
| A A A B, B B A B | Goat death in phase 4 |
| A A B A, B B B A | Reputation death in phase 4 |

5. Try breaking things: delete a comma in tutorial.json, or rename a scene. The game refuses to start and tells you the line or the scene name.

## story.json reference

### Top level

| Key | Meaning |
|---|---|
| `title` | Window title and title-screen text |
| `about` | About-screen text (`\n` = new line) |
| `title_music` | Music on the title screen (optional) |
| `show_stats` | `true` shows stats top-left, `false` hides them |
| `stats` | Stat names and starting values. The names are shown exactly as written. |
| `lose` | Which scene to jump to when each stat reaches 0 |
| `start` | First scene when you press Start |
| `scenes` | Named lists of steps. Every scene must finish with `end`, `branch`, or a choice where every option has a `goto`. |

### Fields any step can have
All of these **stay until changed**.

| Field | Example | Notes |
|---|---|---|
| `bg` | `"garden.png"` | from `assets/bg/` |
| `sprites` | `{"left": "alice_angry.png", "middle": null}` | positions: `left`, `middle`, `right`; `null` removes; from `assets/sprites/` |
| `music` | `"calm.wav"` or `null` | loops; `null` stops; the same track as now keeps playing without restarting; from `assets/music/` |
| `sfx` | `"ding.wav"` | plays once; from `assets/sfx/` |
| `note` | anything | ignored, use as a comment |

### Step types

```json
{"type": "text", "speaker": "Alice", "text": "Hello!"}
```
Leave out `speaker` for narration. Advance with click, Space or Enter.

```json
{"type": "chapter", "text": "Year 7"}
```
Black title card. Advance with click, Space or Enter.

```json
{"type": "choice", "text": "Optional prompt", "options": [
  {"text": "Button label", "stats": {"Time": -2, "Rep": 2}, "flag": "optional_flag", "goto": "optional_scene"}
]}
```
After a click, the stats change and the flag is remembered.
- **No `goto`:** the story continues with the next step. If a stat has reached 0, the game immediately jumps to its `lose` scene.
- **With `"goto": "scene_name"`:** the game jumps to that scene, which is where the reaction dialogue for that pick goes. Stats are checked at that scene's closing `branch`, so the player sees what happened before dying.

(Stats are checked at every `branch` step.)

```json
{"type": "cutscene", "music": "intro.wav", "fade": 1.0, "slides": [
  {"image": "intro1.png", "duration": 3}
]}
```
Plays by itself. `fade` is the crossfade in seconds. A click skips the whole cutscene. Images come from `assets/cutscenes/`.

```json
{"type": "branch", "rules": [
  {"flags": ["rose_bush", "goat_fire"], "goto": "secret_end"},
  {"stat": "Time", "min": 3, "max": 10, "goto": "other_end"}
], "else": "true_end"}
```
Rules are checked top to bottom and the first match wins. A rule can use `flags` (all must be set), `stat` with `min` and/or `max`, or both. `{"type": "branch", "else": "scene"}` is a plain jump.

```json
{"type": "end", "text": "TRUE ENDING", "hint": "optional small line under the title"}
```
Shows the text and a **Return to title** button.

## Asset sizes

| Folder | Size | Format |
|---|---|---|
| `bg/` | 1280×720 (other sizes get stretched) | PNG/JPG |
| `cutscenes/` | 1280×720 (other sizes get stretched) | PNG/JPG |
| `sprites/` | about 400×600, transparent background, character standing at the bottom edge | PNG |
| `music/`, `sfx/` | any length | OGG or WAV (MP3 works for music) |

Sprites are drawn at their real size, bottom-aligned, centred at 20% / 50% / 80% of the screen width. The dialogue box covers the bottom 200 px.

To swap in your own art, overwrite the placeholder file with the same name, or add a new file and point story.json at it. A missing file shows a grey box and prints a warning instead of crashing.

The placeholder sounds are tones generated for testing, so replace them freely.
