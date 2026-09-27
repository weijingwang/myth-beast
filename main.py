"""Minimal visual novel engine. All story content lives in story.json - see README.md."""
import json
import math
import os
import random
import sys

import pygame

W, H = 1280, 720
FPS = 60
BOX_H = 200                     # height of the dialogue box at the bottom
SPRITE_SIZE = (400, 600)        # only used for missing-sprite placeholders
SPRITE_X = {"left": 0.2, "middle": 0.5, "right": 0.8}
STEP_TYPES = {"text", "chapter", "choice", "cutscene", "branch", "end"}
WHITE, BLACK, GOLD = (255, 255, 255), (0, 0, 0), (255, 220, 120)
GREEN, RED = (120, 255, 120), (255, 110, 110)
FROZEN = getattr(sys, "frozen", False)   # True inside the packaged Mac app / Windows exe
HERE = sys._MEIPASS if FROZEN else os.path.dirname(os.path.abspath(__file__))


def save_dir():
    """Where endings_found_*.json is kept: next to main.py, or a user folder in the packaged app."""
    if not FROZEN:
        return HERE
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, "MythicalBeast")
    os.makedirs(path, exist_ok=True)
    return path
ASSETS = os.path.join(HERE, "assets")

# ---- game feel. Tweak freely.
TEXT_SPEED = 50                  # typewriter letters per second
FAST_FORWARD_KEYS = (pygame.K_TAB, pygame.K_LCTRL, pygame.K_RCTRL)   # hold to skip text
DIM = (140, 140, 140)            # colour multiplier for sprites that aren't speaking
SHAKE_PIXELS = 4                 # how far the screen shakes
SHAKE_TIME = 0.2                 # seconds; the shake fades out over this time
# comic timing: extra pause (seconds) after these characters while text types out. {} = off
PUNCTUATION_PAUSE = {".": 0.28, "!": 0.28, "?": 0.28, "…": 0.35, ",": 0.08}

# ---- title screen look
TEXT_FONT = "helveticaneue,helvetica,arial,dejavusans"   # dialogue text: plain and easy to read
MENU_FONT = "georgia,baskerville,palatino,timesnewroman,dejavuserif"   # first one installed is used
TITLE_TOP = 40                   # y of the title's first line
TITLE_ACCENT = (34, 50, 112)     # royal indigo for the big words of a "title_logo"
MENU_Y = H - 46                  # the row of title-screen buttons sits on the grass
TITLE_COLOUR = (82, 102, 152)    # softer indigo for the small title words
TITLE_HALO = (232, 242, 255)     # faint pale-blue edge that lifts the title off the clouds
TITLE_HALO_ALPHA = 55            # 0 = no edge, 255 = solid
END_VEIL = 150                   # how dark the ending CG gets behind the end screen (0-255)
CHAPTER_LABEL = (196, 168, 120)  # "CHAPTER 1" line on chapter cards (muted gold)
CHAPTER_TEXT = (236, 224, 200)   # chapter name on chapter cards (parchment)
MENU_PANEL = (22, 30, 52)        # tint behind the About text
DISSOLVE_TIME = 1.2              # seconds for a mid-scene background dissolve
FADE_TIME = 0.8                  # seconds for a fade to black and back (chapters, new backgrounds, endings)
# Sound effects that also shake or flash the screen. A step can also say
# "shake": true or "flash": [r, g, b] itself.
SHAKE_SFX = {"charge.wav", "box-crash.ogg", "door_burst.ogg", "sword.ogg"}
FLASH_SFX = {"fire.ogg": (255, 140, 30)}


# ---------------------------------------------------------------- story file
def load_story(path):
    try:
        with open(path, encoding="utf-8") as f:
            story = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"story.json error at line {e.lineno}, column {e.colno}: {e.msg}")
    validate(story)
    return story


def validate(story):
    """Catch typos at startup instead of mid-game."""
    scenes = story["scenes"]
    targets = [story["start"]] + list(story.get("lose", {}).values())
    for name, steps in scenes.items():
        last = steps[-1] if steps else {}
        jumps_away = last.get("type") == "choice" and all("goto" in o for o in last["options"])
        if last.get("type") not in ("end", "branch") and not jumps_away:
            sys.exit(f"story.json: scene '{name}' must finish with 'end', 'branch', "
                     "or a choice where every option has a 'goto'")
        for i, step in enumerate(steps, 1):
            if step.get("type") not in STEP_TYPES:
                sys.exit(f"story.json: scene '{name}' step {i} has unknown type {step.get('type')!r}")
            if step["type"] == "branch":
                if "else" not in step:
                    sys.exit(f"story.json: scene '{name}' step {i} (branch) needs an 'else'")
                targets += [r["goto"] for r in step.get("rules", [])] + [step["else"]]
            if step["type"] == "choice":
                targets += [o["goto"] for o in step["options"] if "goto" in o]
            if step["type"] == "cutscene" and not step.get("slides"):
                sys.exit(f"story.json: scene '{name}' step {i} (cutscene) has no slides")
    for t in targets:
        if t not in scenes:
            sys.exit(f"story.json: scene '{t}' is used but never defined")
    for stat in story.get("lose", {}):
        if stat not in story["stats"]:
            sys.exit(f"story.json: 'lose' uses stat '{stat}' which is not in 'stats'")


# ---------------------------------------------------------------- assets
class Assets:
    """Loads and caches files. Missing files warn instead of crashing."""

    def __init__(self, font):
        self.font = font
        self.images, self.sounds = {}, {}
        self.music = None
        self.volumes = {}   # per-track music volume (0..1), from "music_volume" in story.json
        self.sfx_volumes = {}   # per-sound volume (0..1), from "sfx_volume" in story.json
        try:
            pygame.mixer.init()
            self.audio = True
        except pygame.error:
            print("WARNING: no audio device, sound disabled")
            self.audio = False

    def image(self, folder, name, size, fit=False):
        key = (folder, name)
        if key not in self.images:
            try:
                img = pygame.image.load(os.path.join(ASSETS, folder, name)).convert_alpha()
                if fit and img.get_size() != size:
                    img = pygame.transform.smoothscale(img, size)
            except (pygame.error, FileNotFoundError):
                print(f"WARNING: missing image assets/{folder}/{name}")
                img = pygame.Surface(size)
                img.fill((90, 90, 90))
                label = self.font.render(f"{folder}/{name}", True, WHITE)
                img.blit(label, label.get_rect(center=(size[0] // 2, size[1] // 2)))
            self.images[key] = img
        return self.images[key]

    def sfx(self, name):
        if not self.audio:
            return
        if name not in self.sounds:
            try:
                self.sounds[name] = pygame.mixer.Sound(os.path.join(ASSETS, "sfx", name))
                self.sounds[name].set_volume(self.sfx_volumes.get(name, 1.0))
            except (pygame.error, FileNotFoundError):
                print(f"WARNING: missing sound assets/sfx/{name}")
                self.sounds[name] = None
        if self.sounds[name]:
            self.sounds[name].play()

    def play_music(self, name):
        """name=None stops the music. Same track as now keeps playing."""
        if not self.audio or name == self.music:
            return
        self.music = name
        pygame.mixer.music.stop()
        if name:
            try:
                pygame.mixer.music.load(os.path.join(ASSETS, "music", name))
                pygame.mixer.music.set_volume(self.volumes.get(name, 1.0))
                pygame.mixer.music.play(-1)
            except (pygame.error, FileNotFoundError):
                print(f"WARNING: missing music assets/music/{name}")


# ---------------------------------------------------------------- UI helpers
def wrap(font, text, width):
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            test = f"{line} {word}".strip()
            if font.size(test)[0] <= width or not line:
                line = test
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def render_spaced(font, text, colour, spacing):
    """Text with extra space between letters (for small-caps menu labels)."""
    chars = [font.render(c, True, colour) for c in text]
    surf = pygame.Surface((sum(c.get_width() for c in chars) + spacing * (len(chars) - 1),
                           font.get_height()), pygame.SRCALPHA)
    x = 0
    for c in chars:
        surf.blit(c, (x, 0))
        x += c.get_width() + spacing
    return surf


def ending_name(step):
    """An end screen's name is the last line of its text ("GAME OVER\nExiled" -> "Exiled")."""
    lines = [l for l in step.get("text", "").split("\n") if l.strip()]
    return lines[-1] if lines else "Ending"


class Button:
    def __init__(self, text, center, width=600, height=60):
        self.text = text
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = center

    def draw(self, surf, font, menu=False):
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
        if menu:   # title screen: text only, like a visual novel menu; gold + underline on hover
            label = render_spaced(font, self.text.upper(), GOLD if hover else (238, 236, 228), 3)
            shadow = render_spaced(font, self.text.upper(), BLACK, 3)
            shadow.set_alpha(170)
            spot = label.get_rect(center=self.rect.center)
            surf.blit(shadow, spot.move(2, 2))
            surf.blit(label, spot)
            if hover:
                pygame.draw.line(surf, GOLD, (spot.left, spot.bottom + 2), (spot.right, spot.bottom + 2), 2)
            return
        panel = pygame.Surface(self.rect.size, pygame.SRCALPHA)   # choices: see-through rounded panel
        pygame.draw.rect(panel, MENU_PANEL + ((225,) if hover else (175,)), panel.get_rect(), border_radius=12)
        if hover:
            pygame.draw.rect(panel, GOLD, panel.get_rect(), width=2, border_radius=12)
        surf.blit(panel, self.rect)
        label = font.render(self.text, True, GOLD if hover else WHITE)
        surf.blit(label, label.get_rect(center=self.rect.center))

    def clicked(self, event):
        return (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.rect.collidepoint(event.pos))


# ---------------------------------------------------------------- game
class Game:
    def __init__(self):
        pygame.init()
        story_file = sys.argv[1] if len(sys.argv) > 1 else "story.json"   # python main.py tutorial.json
        self.story = load_story(os.path.join(HERE, story_file))
        if self.story.get("icon"):   # window / dock icon, e.g. "icon.png" in assets/
            try:
                pygame.display.set_icon(pygame.image.load(os.path.join(ASSETS, self.story["icon"])))
            except (pygame.error, FileNotFoundError):
                print(f"WARNING: missing icon assets/{self.story['icon']}")
        self.screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)  # maximise button; scales and letterboxes, mouse coords stay 1280x720
        # endings the player has seen, remembered between sessions (one file per story file)
        self.endings_file = os.path.join(save_dir(), "endings_found_" + os.path.splitext(story_file)[0] + ".json")
        self.all_endings = [ending_name(st) for steps in self.story["scenes"].values()
                            for st in steps if st["type"] == "end"]
        try:
            with open(self.endings_file) as f:
                self.endings_found = set(json.load(f))
        except (OSError, ValueError):
            self.endings_found = set()
        self.hovered = None
        pygame.display.set_caption(self.story.get("title", "Visual Novel"))
        self.font = pygame.font.SysFont(TEXT_FONT, 32)                 # dialogue (clean, easy to read)
        self.stats_font = pygame.font.SysFont(MENU_FONT, 30)           # Time / Reputation corner
        self.choice_font = pygame.font.SysFont(MENU_FONT, 30)          # choice buttons (serif, like the menus)
        self.name_font = pygame.font.SysFont(MENU_FONT, 30, bold=True)  # speaker names
        self.big = pygame.font.SysFont(MENU_FONT, 64)                  # end screens
        self.popup_font = pygame.font.SysFont(MENU_FONT, 44, bold=True)  # "+1 Time" popups
        self.assets = Assets(self.font)
        self.assets.volumes = self.story.get("music_volume", {})
        self.assets.sfx_volumes = self.story.get("sfx_volume", {})
        self.clock = pygame.time.Clock()
        self.menu_font = pygame.font.SysFont(MENU_FONT, 30)
        self.chapter_font = pygame.font.SysFont(MENU_FONT, 62)
        # Title logo: "title_logo" in story.json lists lines with their own size, so the key
        # words can be big and the joining words small. Without it, "title" is used as one line.
        self.title_logo = [(pygame.font.SysFont(MENU_FONT, line.get("size", 60), bold=True),
                            line["text"], TITLE_ACCENT if line.get("accent") else TITLE_COLOUR)
                           for line in self.story.get("title_logo", [])]
        if not self.title_logo:
            self.title_logo = [(pygame.font.SysFont(MENU_FONT, 96, bold=True), self.story.get("title", ""), TITLE_ACCENT)]
        # one row of text buttons along the bottom of the title art, evenly spaced and centred
        labels = ("Start", "About", "Quit")
        widths = [render_spaced(self.menu_font, t.upper(), WHITE, 3).get_width() + 24 for t in labels]
        gap, x = 70, (W - sum(widths) - 70 * (len(labels) - 1)) // 2
        self.title_buttons = []
        for t, w in zip(labels, widths):
            self.title_buttons.append(Button(t, (x + w // 2, MENU_Y), w, 44))
            x += w + gap
        w = render_spaced(self.menu_font, "BACK", WHITE, 3).get_width() + 24
        self.back_button = Button("Back", (W // 2, MENU_Y), w, 44)
        self.dim_cache = {}
        self.checkpoint, self.buttons, self.step, self.pending_sfx = None, [], {"type": "none"}, []
        self.video = None   # the secret video while it plays
        self.secret = self.story.get("secret_video")   # unlocked by an ending, see story.json
        self.secret_button = Button("", (W - 64, H - 58), 76, 76)
        self.fade, self.fade_from, self.fade_dissolve, self.prev_kind = 0.0, None, False, None
        self.go_title()

    # ---- flow
    def start_fade(self, dissolve=False):
        """Black fade: old frame to black, then the new one in.
        Dissolve: the old frame melts straight into the new one (mid-scene background changes)."""
        held = pygame.key.get_pressed()
        if not self.fade and not any(held[k] for k in FAST_FORWARD_KEYS):
            self.fade_from, self.fade_dissolve = self.screen.copy(), dissolve
            self.fade = DISSOLVE_TIME if dissolve else FADE_TIME

    def go_title(self):
        self.start_fade()
        self.mode = "title"
        self.assets.play_music(self.story.get("title_music"))

    def new_game(self):
        self.stats = dict(self.story["stats"])
        self.flags = set()
        self.bg, self.sprites = None, {}
        self.shake, self.flash, self.talking = 0.0, None, None
        self.popups, self.ff_timer = [], 0.0      # popups: [stat, delta, age]
        self.prev_kind, self.checkpoint, self.pending_sfx = None, None, []
        self.mode = "story"
        self.goto(self.story["start"])

    def retry_chapter(self):
        scene, stats, flags, _ = self.checkpoint
        self.stats, self.flags = dict(stats), set(flags)
        self.bg, self.sprites, self.popups, self.prev_kind = None, {}, [], None
        self.goto(scene)

    def goto(self, scene):
        self.scene, self.index = scene, -1
        self.next_step()

    def next_step(self):
        self.index += 1
        step = self.step = self.story["scenes"][self.scene][self.index]
        kind = step["type"]
        if kind != "branch":   # fade on chapters, cutscenes, endings, new locations, or "fade": true
            black = kind in ("chapter", "cutscene", "end") or self.prev_kind in (None, "chapter", "cutscene")
            new_bg = "bg" in step and step["bg"] != self.bg
            wanted = step.get("fade")   # true = black fade, "dissolve", false = none, missing = automatic
            if wanted == "dissolve":
                self.start_fade(dissolve=True)
            elif wanted or (wanted is None and (black or new_bg)):
                self.start_fade()
            self.prev_kind = kind
        # Fields any step may carry. They persist until changed.
        if "bg" in step:
            self.bg = step["bg"]
        self.sprites.update(step.get("sprites", {}))   # null removes a sprite
        if "music" in step:
            self.assets.play_music(step["music"])
        # "sfx" is one file, or a list of files / [file, delay-in-seconds] pairs, e.g.
        # ["goatsfx_beeeeeeh.ogg", ["box-crash.ogg", 0.9]]
        sounds = step.get("sfx", [])
        sounds = [sounds] if isinstance(sounds, str) else sounds
        for snd in sounds:
            name, delay = (snd, 0) if isinstance(snd, str) else snd
            if delay:
                self.pending_sfx.append([delay, name])
            else:
                self.play_sfx(name)
        # game feel: typewriter restart, shake, flash, who is speaking
        self.typed, self.type_pause = 0.0, 0.0
        if kind == "chapter":   # "Retry chapter" returns here with these stats
            self.checkpoint = (self.scene, dict(self.stats), set(self.flags), step.get("text", "").split("\n")[0])
        if step.get("shake"):
            self.shake = SHAKE_TIME
        flash = step.get("flash")
        if flash:
            self.flash = [tuple(flash), 0.5]
        self.talking = self.speaker_position(step)

        if kind == "branch":
            self.goto(self.lost_scene() or self.pick_branch(step))
        elif kind == "cutscene":
            self.timer = 0.0
        elif kind == "choice":
            n = len(step["options"])
            self.buttons = [Button(o["text"], (W // 2, 280 + i * 80 - (n - 1) * 40))
                            for i, o in enumerate(step["options"])]
        elif kind == "end":
            name = ending_name(step)
            if name not in self.endings_found:
                self.endings_found.add(name)
                try:
                    with open(self.endings_file, "w") as f:
                        json.dump(sorted(self.endings_found), f)
                except OSError:
                    pass
            self.buttons = [Button("Return to title", (W // 2, H // 2 + 150), 400)]
            retry_on = self.story.get("retry_on", "deaths")   # "deaths", "all" or "none"
            is_death = self.scene in self.story.get("lose", {}).values()
            if self.checkpoint and (retry_on == "all" or (retry_on == "deaths" and is_death)):   # replay this chapter
                self.buttons[0].rect.centerx = W // 2 + 220
                self.buttons.append(Button("Retry " + self.checkpoint[3], (W // 2 - 220, H // 2 + 150), 400))

    def speaker_position(self, step):
        """Sprite slot of the speaker. Sprite files start with the speaker's name
        ("Friend 1" -> friend1.png, "Knight 2" -> knight.png, "Claire (thinking)" -> claire_*.png)."""
        name = step.get("speaker", "").split("(")[0].lower().replace(" ", "")
        if not name:
            return None
        for key in (name, name.rstrip("0123456789")):
            for pos, sprite in self.sprites.items():
                if sprite and sprite.lower().startswith(key):
                    return pos
        return None

    def pick_branch(self, step):
        for rule in step.get("rules", []):
            ok = all(f in self.flags for f in rule.get("flags", []))
            if "stat" in rule:
                v = self.stats[rule["stat"]]
                ok = ok and rule.get("min", v) <= v <= rule.get("max", v)
            if ok:
                return rule["goto"]
        return step["else"]

    def choose(self, option):
        for stat, delta in option.get("stats", {}).items():
            self.stats[stat] += delta
            if delta:
                self.popups.append([stat, delta, 0.0])
        if "flag" in option:
            self.flags.add(option["flag"])
        if "goto" in option:   # stats get checked at that scene's closing branch
            return self.goto(option["goto"])
        lost = self.lost_scene()
        if lost:
            return self.goto(lost)
        self.next_step()

    def lost_scene(self):
        """Scene to jump to once a stat reaches 0, else None."""
        lose = self.story.get("lose", {})
        if self.scene in lose.values():
            return None
        for stat, scene in lose.items():
            if self.stats[stat] <= 0:
                return scene
        return None

    # ---- input / update
    def handle(self, event):
        advance = ((event.type == pygame.MOUSEBUTTONDOWN and event.button == 1)
                   or (event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN)))
        if self.fade:   # ignore clicks mid-fade so nobody skips a line by accident
            return
        if any(b.clicked(event) for b in self.visible_buttons()):
            self.ui_sound("click")
        if self.mode == "video":   # any click or key skips the video
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.end_video()
            return
        if self.mode == "title":
            start, about, quit_ = self.title_buttons
            if self.secret_unlocked() and self.secret_button.clicked(event):
                self.start_video()
            elif start.clicked(event):
                self.new_game()
            elif about.clicked(event):
                self.mode = "about"
            elif quit_.clicked(event):
                self.running = False
        elif self.mode == "about":
            if self.back_button.clicked(event):
                self.mode = "title"
        else:
            kind = self.step["type"]
            if kind == "text" and advance and self.typed < len(self.step["text"]):
                self.typed = len(self.step["text"])                    # first click finishes the line
            elif kind == "cutscene" and advance:   # click moves to the next slide; on the last slide, ends it
                self.next_slide()
            elif kind in ("text", "chapter") and advance:
                self.next_step()
            elif kind == "choice":
                for button, option in zip(self.buttons, self.step["options"]):
                    if button.clicked(event):
                        self.choose(option)
                        break
            elif kind == "end":
                if self.buttons[0].clicked(event):
                    self.go_title()
                elif len(self.buttons) > 1 and self.buttons[1].clicked(event):
                    self.start_fade()
                    self.retry_chapter()

    def next_slide(self):
        """Jump to the crossfade into the next slide (or straight to it if already fading)."""
        slides, fade = self.step["slides"], self.step.get("fade", 1.0)
        start = 0.0
        for i, slide in enumerate(slides):
            end = start + slide["duration"]
            if self.timer < end:
                break
            start = end
        if i == len(slides) - 1:
            self.next_step()
        else:
            cross = end - fade
            self.timer = cross if self.timer < cross else end

    def secret_unlocked(self):
        return bool(self.secret) and self.secret.get("unlock") in self.endings_found

    def start_video(self):
        """Secret video: a folder of numbered frames played in sync with an audio file."""
        folder = os.path.join(ASSETS, self.secret["frames"])
        frames = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".png")))
        sound = None
        if self.assets.audio and self.secret.get("audio"):
            try:
                sound = pygame.mixer.Sound(os.path.join(ASSETS, self.secret["audio"]))
            except (pygame.error, FileNotFoundError):
                print("WARNING: missing video audio")
        self.assets.play_music(None)   # silence the title music while it plays
        self.video = {"frames": [os.path.join(folder, f) for f in frames], "cache": {},
                      "fps": self.secret.get("fps", 20), "t": 0.0, "sound": sound}
        if sound:
            sound.play()
        self.start_fade()
        self.mode = "video"

    def end_video(self):
        if self.video and self.video["sound"]:
            self.video["sound"].stop()
        self.video = None
        self.go_title()   # fades back and restarts the title music

    def draw_video(self):
        v = self.video
        i = min(int(v["t"] * v["fps"]), len(v["frames"]) - 1)
        if i not in v["cache"]:   # load frames as they're needed so starting is instant
            v["cache"][i] = pygame.image.load(v["frames"][i]).convert()
        img = v["cache"][i]
        if img.get_height() != H:
            img = pygame.transform.smoothscale(img, (img.get_width() * H // img.get_height(), H))
        self.screen.blit(img, img.get_rect(center=(W // 2, H // 2)))

    def visible_buttons(self):
        if self.mode == "title":
            return self.title_buttons + ([self.secret_button] if self.secret_unlocked() else [])
        if self.mode == "video":
            return []
        if self.mode == "about":
            return [self.back_button]
        return self.buttons if self.step["type"] in ("choice", "end") else []

    def ui_sound(self, which):
        name = self.story.get("ui_sounds", {}).get(which)   # e.g. {"hover": "ui_hover.wav", "click": "ui_click.wav"}
        if name:
            self.assets.sfx(name)

    def play_sfx(self, name):
        """Play a sound effect; some also shake the screen or flash a colour."""
        self.assets.sfx(name)
        if name in SHAKE_SFX:
            self.shake = SHAKE_TIME
        if name in FLASH_SFX:
            self.flash = [tuple(FLASH_SFX[name]), 0.5]

    def update(self, dt):
        self.fade = max(0.0, self.fade - dt)
        for pending in self.pending_sfx:   # delayed sound effects
            pending[0] -= dt
            if pending[0] <= 0:
                self.play_sfx(pending[1])
        self.pending_sfx = [p for p in self.pending_sfx if p[0] > 0]
        if self.mode == "video":
            self.video["t"] += dt
            if self.video["t"] >= len(self.video["frames"]) / self.video["fps"] + 0.3:
                self.end_video()
            return
        mouse = pygame.mouse.get_pos()
        over = next((b for b in self.visible_buttons() if b.rect.collidepoint(mouse)), None)
        if over is not self.hovered and over is not None and not self.fade:
            self.ui_sound("hover")
        self.hovered = over
        if self.mode != "story":
            return
        if not self.fade and self.step["type"] == "text":   # text starts typing once the fade is done
            if self.type_pause > 0:
                self.type_pause -= dt
            else:
                text, before = self.step["text"], int(self.typed)
                self.typed += dt * TEXT_SPEED
                for i in range(before, min(int(self.typed), len(text) - 1)):   # pause after "...", "!", ","
                    if text[i] in PUNCTUATION_PAUSE and text[i + 1] not in PUNCTUATION_PAUSE:
                        self.typed, self.type_pause = i + 1, PUNCTUATION_PAUSE[text[i]]
                        break
        self.shake = max(0.0, self.shake - dt)
        if self.flash:
            self.flash[1] -= dt
            self.flash = self.flash if self.flash[1] > 0 else None
        for p in self.popups:
            p[2] += dt
        self.popups = [p for p in self.popups if p[2] < 2.0]
        kind = self.step["type"]
        keys = pygame.key.get_pressed()
        if kind in ("text", "chapter", "cutscene") and any(keys[k] for k in FAST_FORWARD_KEYS):
            self.ff_timer += dt
            if self.ff_timer > 0.05:
                self.ff_timer = 0.0
                return self.next_step()
        if kind == "cutscene":
            self.timer += dt
            if self.timer >= sum(s["duration"] for s in self.step["slides"]):
                self.next_step()

    # ---- drawing
    def text_center(self, text, font, y, colour=WHITE):
        lines = wrap(font, text, W - 200)
        y -= len(lines) * font.get_linesize() // 2
        for line in lines:
            img = font.render(line, True, colour)
            self.screen.blit(img, img.get_rect(midtop=(W // 2, y)))
            y += font.get_linesize()

    def draw_title_text(self, pos):
        """Title logo: each line in its own size/colour, with a faint halo over the sky."""
        x, y = pos
        for font, text, colour in self.title_logo:
            halo = font.render(text, True, TITLE_HALO)
            halo.set_alpha(TITLE_HALO_ALPHA)
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                self.screen.blit(halo, (x + dx, y + dy))
            self.screen.blit(font.render(text, True, colour), (x, y))
            y += int(font.get_linesize() * 0.92)

    def draw_endings_found(self):
        """Top-right of the title screen: "Endings found 2 / 4" and each ending's name, or ??? if not found yet."""
        found = len(self.endings_found & set(self.all_endings))
        header = ("All endings found. Thank you for playing!" if found == len(self.all_endings)
                  else f"Endings found  {found} / {len(self.all_endings)}")
        rows = [(header, TITLE_ACCENT)]
        rows += [(n if n in self.endings_found else "???", TITLE_COLOUR) for n in self.all_endings]
        y = TITLE_TOP + 6
        for text, colour in rows:
            img = self.menu_font.render(text, True, colour)
            halo = self.menu_font.render(text, True, TITLE_HALO)
            halo.set_alpha(TITLE_HALO_ALPHA)
            x = W - 50 - img.get_width()
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                self.screen.blit(halo, (x + dx, y + dy))
            self.screen.blit(img, (x, y))
            y += img.get_height() + 4

    def draw_chapter_card(self, text):
        """Chapter card on the "chapter_bg" image: first line small gold capitals, rest large serif."""
        self.screen.blit(self.assets.image("bg", self.story["chapter_bg"], (W, H), True), (0, 0))
        lines = [l for l in text.split("\n") if l.strip()]
        label, heading = (lines[0], lines[1:]) if len(lines) > 1 else (None, lines)
        rows = []
        if label:
            rows.append(render_spaced(self.menu_font, label.upper(), CHAPTER_LABEL, 4))
            rows.append(None)   # gap
        for line in heading:
            rows.append(self.chapter_font.render(line, True, CHAPTER_TEXT))
        height = sum(r.get_height() if r else 18 for r in rows)
        y = H // 2 - height // 2
        for r in rows:
            if r:
                self.screen.blit(r, r.get_rect(midtop=(W // 2, y)))
                y += r.get_height()
            else:
                pygame.draw.line(self.screen, CHAPTER_LABEL, (W // 2 - 60, y + 8), (W // 2 + 60, y + 8), 1)
                y += 18

    def draw_box(self, speaker, text, shown=10**9):
        box = pygame.Surface((W, BOX_H), pygame.SRCALPHA)
        box.fill((0, 0, 0, 190))
        self.screen.blit(box, (0, H - BOX_H))
        pygame.draw.line(self.screen, CHAPTER_LABEL, (0, H - BOX_H), (W, H - BOX_H), 1)   # thin gold edge
        y = H - BOX_H + 18
        if speaker:   # name colour from "speaker_colours" in story.json ("Claire (thinking)" uses Claire's)
            colours = self.story.get("speaker_colours", {})
            colour = colours.get(speaker) or colours.get(speaker.split(" (")[0]) or colours.get("default") or GOLD
            self.screen.blit(self.name_font.render(speaker, True, colour), (40, y))
            y += self.name_font.get_linesize() + 4
        full = shown >= len(text)
        for line in wrap(self.font, text, W - 80):   # typewriter: only `shown` letters
            if shown <= 0:
                break
            self.screen.blit(self.font.render(line[:shown], True, WHITE), (40, y))
            shown -= len(line) + 1
            y += self.font.get_linesize()
        if full and self.mode == "story" and self.step.get("type") == "text" and not self.fade:
            bob = int(4 * math.sin(pygame.time.get_ticks() / 180))   # "click to continue" arrow
            x, y = W - 48, H - 34 + bob
            pygame.draw.polygon(self.screen, CHAPTER_LABEL, [(x - 9, y - 6), (x + 9, y - 6), (x, y + 6)])

    def draw_cutscene(self):
        slides, fade, t = self.step["slides"], self.step.get("fade", 1.0), self.timer
        i = 0
        while i < len(slides) - 1 and t >= slides[i]["duration"]:
            t -= slides[i]["duration"]
            i += 1
        self.screen.blit(self.assets.image("cutscenes", slides[i]["image"], (W, H), True), (0, 0))
        time_left = slides[i]["duration"] - t
        if i + 1 < len(slides) and time_left < fade:            # crossfade into next slide
            nxt = self.assets.image("cutscenes", slides[i + 1]["image"], (W, H), True)
            nxt.set_alpha(int(255 * (1 - time_left / fade)))
            self.screen.blit(nxt, (0, 0))
            nxt.set_alpha(255)

    def draw_stats(self):
        imgs = []
        for k, v in self.stats.items():   # a stat that just changed turns green/red
            changed = [d for s, d, _ in self.popups if s == k]
            warn = self.story.get("stat_warning", {}).get(k)   # e.g. {"Time": 3}: red at 3 or less
            colour = (GREEN if changed[-1] > 0 else RED) if changed else (RED if warn is not None and v <= warn else WHITE)
            imgs.append(self.stats_font.render(f"{k}: {v}", True, colour))
        width = sum(i.get_width() for i in imgs) + 30 * (len(imgs) - 1)
        pygame.draw.rect(self.screen, BLACK, pygame.Rect(20, 20, width, imgs[0].get_height()).inflate(20, 12))
        x = 20
        for img in imgs:
            self.screen.blit(img, (x, 20))
            x += img.get_width() + 30
        for i, (stat, delta, age) in enumerate(self.popups):   # "+1 Reputation" floating up
            img = self.popup_font.render(f"{delta:+d} {stat}", True, GREEN if delta > 0 else RED)
            img.set_alpha(max(0, 255 - int(age * 127)))
            self.screen.blit(img, (30, 60 + i * 60 - int(age * 25)))

    def shown_sprite(self, pos):
        """The sprite file actually drawn. "low_health_sprite" in story.json can swap it
        when a stat is low (e.g. a hurt goat when Time is 3 or less)."""
        name = self.sprites[pos]
        rule = self.story.get("low_health_sprite")
        if rule and self.stats.get(rule["stat"], 10**9) <= rule["at_or_below"]:
            name = rule["swap"].get(name, name)
        return name

    def sprite_image(self, pos):
        name = self.shown_sprite(pos)
        img = self.assets.image("sprites", name, SPRITE_SIZE)
        if self.talking and pos != self.talking:   # dim whoever isn't speaking
            if name not in self.dim_cache:
                self.dim_cache[name] = img.copy()
                self.dim_cache[name].fill(DIM + (255,), special_flags=pygame.BLEND_RGBA_MULT)
            img = self.dim_cache[name]
        return img

    def draw(self):
        self.screen.fill(BLACK)
        if self.mode in ("title", "about") and self.story.get("title_bg"):
            self.screen.blit(self.assets.image("bg", self.story["title_bg"], (W, H), True), (0, 0))
        if self.mode == "video":
            self.draw_video()
        elif self.mode == "title":
            self.draw_title_text((70, TITLE_TOP))
            self.draw_endings_found()
            if self.secret_unlocked():   # the reward for the true ending: a little goat in the corner
                hover = self.secret_button.rect.collidepoint(pygame.mouse.get_pos())
                size = 76 if hover else 64
                img = pygame.transform.smoothscale(
                    self.assets.image("", self.secret.get("button", "icon.png"), (64, 64)), (size, size))
                self.screen.blit(img, img.get_rect(center=self.secret_button.rect.center))
            for b in self.title_buttons:
                b.draw(self.screen, self.menu_font, menu=True)
        elif self.mode == "about":
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill(MENU_PANEL + (185,))
            self.screen.blit(veil, (0, 0))
            self.text_center(self.story.get("about", ""), self.menu_font, H // 2 - 60)
            self.back_button.draw(self.screen, self.menu_font, menu=True)
        else:
            kind = self.step["type"]
            if kind == "cutscene":
                self.draw_cutscene()
            elif kind == "chapter" and self.story.get("chapter_bg"):
                self.draw_chapter_card(self.step.get("text", ""))
            elif kind in ("chapter", "end"):
                if kind == "end" and self.bg:   # keep the ending's CG on screen, darkened so the text reads
                    self.screen.blit(self.assets.image("bg", self.bg, (W, H), True), (0, 0))
                    veil = pygame.Surface((W, H), pygame.SRCALPHA)
                    veil.fill((0, 0, 0, END_VEIL))
                    self.screen.blit(veil, (0, 0))
                self.text_center(self.step.get("text", ""), self.big, H // 2 - (90 if kind == "end" else 0), CHAPTER_TEXT)
                if kind == "end" and self.step.get("hint"):   # small hint line under GAME OVER
                    self.text_center(self.step["hint"], self.menu_font, H // 2 + 45, GOLD)
            else:   # text / choice
                if self.bg:
                    self.screen.blit(self.assets.image("bg", self.bg, (W, H), True), (0, 0))
                for pos, x in SPRITE_X.items():
                    if self.sprites.get(pos):
                        img = self.sprite_image(pos)
                        self.screen.blit(img, img.get_rect(midbottom=(int(W * x), H)))
                if kind == "text":
                    self.draw_box(self.step.get("speaker"), self.step["text"], int(self.typed))
                elif self.step.get("text"):
                    self.draw_box(None, self.step["text"])
                ending = any(st["type"] == "end" for st in self.story["scenes"][self.scene])
                if self.story.get("show_stats") and not ending:   # no stats over the ending art
                    self.draw_stats()
            if kind in ("choice", "end"):
                for b in self.buttons:
                    b.draw(self.screen, self.menu_font if kind == "end" else self.choice_font, menu=(kind == "end"))
            if self.flash:
                overlay = pygame.Surface((W, H))
                overlay.fill(self.flash[0])
                overlay.set_alpha(int(180 * self.flash[1] / 0.5))
                self.screen.blit(overlay, (0, 0))
            if self.shake:
                frame = self.screen.copy()
                self.screen.fill(BLACK)
                px = max(1, round(SHAKE_PIXELS * self.shake / SHAKE_TIME))   # fades out
                self.screen.blit(frame, (random.randint(-px, px), random.randint(-px, px)))
        if self.fade and self.fade_dissolve:   # old frame melts away over the new one
            self.fade_from.set_alpha(int(255 * self.fade / DISSOLVE_TIME))
            self.screen.blit(self.fade_from, (0, 0))
            self.fade_from.set_alpha(None)
        elif self.fade:   # first half: old frame darkens, second half: new frame appears
            t = 1 - self.fade / FADE_TIME
            if t < 0.5:
                self.screen.blit(self.fade_from, (0, 0))
            black = pygame.Surface((W, H))
            black.set_alpha(int(255 * (t * 2 if t < 0.5 else (1 - t) * 2)))
            self.screen.blit(black, (0, 0))

    def run(self):
        self.running = True
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 0.1)   # 60 FPS cap; a hitch never jumps animations ahead
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.handle(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
