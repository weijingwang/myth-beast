# Visual Novel Skeleton

```
pip install pygame
python main.py
```

You only ever edit **story.json** and the files in **assets/**. `main.py` stays untouched.

## The real game (story.json)

Search story.json for `TODO:` to find leftover notes. To swap art or audio, overwrite a file with the same name or point story.json at a new one.

## story.json reference

### Top level

| Key | Meaning |
|---|---|
| `title` | Window title and title-screen text |
| `about` | About-screen text (`\n` = new line) |
| `title_logo` | Optional. The title split into lines, each with a `size`; `"accent": true` makes a line the royal indigo of the big words. Without it, `title` is shown as one line. |
| `title_bg` | Title screen background image, from `assets/bg/` |
| `music_volume` | Optional per-track volume from 0 to 1, e.g. `{"2026092423_osdyspdup.mp3": 0.55}`. Tracks not listed play at full volume. |
| `stat_warning` | Optional. Shows a stat in red when it's at or below a level, e.g. `{"Time": 3}`. |
| `low_health_sprite` | Optional, currently unused. Swaps a sprite while a stat is low, e.g. `{"stat": "Time", "at_or_below": 3, "swap": {"excelsior_norm.png": "excelsior_hurt.png"}}`. |
| `chapter_bg` | Optional. Image behind every `chapter` card (from `assets/bg/`). The first line of a card's text is drawn as small gold capitals, the rest as the large chapter name. End screens are not affected. |
| `speaker_colours` | Optional name colours in the text box, e.g. `{"Claire": [244, 168, 190]}`. `Claire (thinking)` uses Claire's colour; `"default"` colours everyone not listed. |
| `sfx_volume` | Optional per-sound volume from 0 to 1, e.g. `{"goatsfx_beeeeeeh.ogg": 0.6}`. Sounds not listed play at full volume. |
| `secret_video` | Optional reward. `{"unlock": "Borrowed Time", "frames": "video/goat_vid", "audio": "video/goat_vid.ogg", "fps": 20, "button": "icon.png"}`: once the named ending is found, a small button appears bottom-right on the title screen and plays the video (a folder of numbered frames plus an audio file). To make frames from a new clip: `ffmpeg -i clip.mov -an -vf "fps=20,scale=-2:720" -q:v 5 assets/video/NAME/%03d.jpg` and `ffmpeg -i clip.mov -vn -c:a libvorbis assets/video/NAME.ogg`. |
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
| `sprites` | `{"left": "claire_angry.png", "middle": null}` | positions: `left`, `middle`, `right`; `null` removes; from `assets/sprites/` |
| `music` | `"calm.wav"` or `null` | loops; `null` stops; the same track as now keeps playing without restarting; from `assets/music/` |
| `sfx` | `"ding.wav"`, or several: `["goatsfx_beeeeeeh.ogg", ["box-crash.ogg", 0.9]]` | plays once; a `[file, seconds]` pair plays after a delay; from `assets/sfx/` |
| `note` | anything | ignored, use as a comment |

### Step types

```json
{"type": "text", "speaker": "Claire", "text": "Hello!"}
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
Plays by itself. `fade` is the crossfade in seconds. A click moves to the next slide (on the last slide it ends the cutscene); holding Tab or Ctrl skips it. Images come from `assets/cutscenes/`.

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
