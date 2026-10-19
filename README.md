# sportsticker

Live sports scores on a 64x32 RGB LED matrix. It polls ESPN scoreboards for the
leagues you enable, favors your teams, and cycles through one slide per game on
a Raspberry Pi with an Adafruit RGB Matrix Bonnet. On a laptop it runs against an
emulator in the browser, so you can develop without any hardware.

Preview of what the ticker shows: https://cev64.github.io/sportsticker/

## Quick start (Mac, emulator)

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,emulator]'
make dev                 # live ESPN data
open http://localhost:8888
```

No games on right now, or it is 3 AM? Use recorded games with simulated scoring:

```sh
make dev-replay          # --replay --fake-live on the emulator
```

## What it shows

- One slide per game, in league order from `config.yaml`. Your favorite teams
  go first within each group (live, upcoming, final), and a live favorite stays
  on screen longer.
- A small ball glyph shows the sport instead of the league name: a football,
  basketball, soccer ball, baseball, or hockey stick and puck. College leagues
  add a "C" to the left of the ball.
- Scores flash in the scoring team's color for a few seconds.
- Down and distance or possession are shown when ESPN provides them.
- Brightness follows a day and night schedule.
- With no games today, a clock screen is shown.

## Snapshots

`make snapshot` renders every slide type with the current data and writes the
results to `snapshots/` (gitignored). Each run produces:

- 10x PNGs that show round LEDs, like the real panel.
- Pixel-grid PNGs with rulers, for reading exact pixel positions.
- Exact 64x32 PNGs, the pixels as the panel receives them.
- An animated GIF of the rotation.
- With `--site`, an `index.html` gallery with a pixel inspector.

`make site` builds the same kind of gallery into `site/` without team logos. CI
publishes `site/` to GitHub Pages. The `/live/` page is the ticker as it would be
right now, and `/demo/` uses recorded games with simulated scoring.

## Layouts

Set `display.layout` in `config.yaml`, or pass `--layout`.

- **a**: Team rows, each with a small logo, abbreviation and score. The
  status line sits below (for example `Q3 4:12` with down and distance).
- **b**: Big logos on the left and right, score below each logo, and the clock
  and period in the middle.
- **c**: Logos with large scores beside them, and the clock and period in a
  right-hand column.
- **text**: No logos, text only. Use it when you do not want logos or the
  network is slow.

For pictures, see the Pages preview linked above.

## Team logos

Logos are downloaded from ESPN's JSON the first time a team is seen. They are
pre-scaled and cached in `~/.cache/sportsticker/logos` (`logos.cache_dir`) and
refreshed after 30 days (`logos.max_age_days`). `make logos` pre-fetches them for
the enabled leagues (`make logos LEAGUES=nfl,nba` for a subset).

Logos are team trademarks and are for personal display only. They are never
committed to the repo, never written inside it, and never published. The public
Pages build uses `--no-logos`. If a logo is missing, the ticker shows the team
abbreviation instead. Set `display.logos: false` to always use abbreviations.

## Raspberry Pi setup

Hardware: Raspberry Pi 4 (1 GB), Adafruit RGB Matrix Bonnet, one 64x32 HUB75
panel. The steps below assume user `charlie` and hostname `ticker`.

1. **Flash the SD card.** In Raspberry Pi Imager, open "Raspberry Pi OS
   (other)" and choose **Raspberry Pi OS (Legacy, 64-bit) Lite**. That is
   Bookworm, the release these steps are written for. The plain "Raspberry Pi
   OS Lite (64-bit)" entry is now Trixie, which this project has not been
   tested on. In the settings, set hostname `ticker`, username `charlie`,
   Wi-Fi, and enable SSH with your public key.

2. **Connect.** `ssh charlie@ticker.local`

3. **Update and install prerequisites.**

   ```sh
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y git python3-venv python3-dev python-dev-is-python3 \
       python3-pil cython3 build-essential
   ```

4. **Disable onboard audio.** The sound chip uses the same hardware the matrix
   needs. Edit `/boot/firmware/config.txt` and set `dtparam=audio=off` (add the line if
   it is missing). For extra safety, also blacklist the module:

   ```sh
   sudo sed -i 's/^dtparam=audio=on/dtparam=audio=off/' /boot/firmware/config.txt
   echo 'blacklist snd_bcm2835' | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf
   sudo update-initramfs -u
   sudo reboot
   ```

   After the reboot, `lsmod | grep snd_bcm2835` should print nothing.

5. **Optional: reduce flicker.** Reserve CPU core 3 for the display by appending
   `isolcpus=3` to the single line in `/boot/firmware/cmdline.txt`. Keep it on
   the same line as the existing arguments, then reboot. Upstream
   rpi-rgb-led-matrix recommends a fuller form,
   `isolcpus=domain,managed_irq,3 nohz_full=3 rcu_nocbs=3 irqaffinity=0,1,2`,
   if you still see flicker.

6. **Clone the repo and create the virtualenv.**

   ```sh
   git clone https://github.com/cev64/sportsticker.git /home/charlie/sportsticker
   python3 -m venv /home/charlie/ticker-venv
   ```

   The virtualenv does not need `--system-site-packages`.

7. **Install the rpi-rgb-led-matrix Python bindings into the venv.** These
   build the driver from upstream (hzeller/rpi-rgb-led-matrix) and install it
   as the `rgbmatrix` module.

   ```sh
   /home/charlie/ticker-venv/bin/pip install git+https://github.com/hzeller/rpi-rgb-led-matrix
   /home/charlie/ticker-venv/bin/python -c "import rgbmatrix; print('rgbmatrix ok')"
   ```

   The build needs the `python3-dev`, `cython3` and `build-essential` packages
   from step 3. See the upstream README if the build fails.

8. **Install sportsticker.**

   ```sh
   /home/charlie/ticker-venv/bin/pip install -e /home/charlie/sportsticker
   ```

9. **Test run.** Run it in the foreground as root, because the driver needs
   direct hardware access. Stop it with Ctrl-C.

   ```sh
   cd /home/charlie/sportsticker
   sudo /home/charlie/ticker-venv/bin/python -m sportsticker run --backend hardware
   ```

   If the panel stays dark, set `matrix.panel_type: "FM6126A"` in `config.yaml`.
   Many 64x32 panels use this driver chip.

   If the image is garbled or ghosted, raise `matrix.gpio_slowdown` (the default
   is 4 for Pi 4). Upstream says a Pi 4 may need higher values. Lower it only if
   you need more refresh rate and the image stays clean.

10. **Install the service.** The script validates `config.yaml`, installs the
    unit file, enables it at boot and restarts it.

    ```sh
    cd /home/charlie/sportsticker
    sudo ./deploy/install.sh
    ```

    Logs: `journalctl -u ticker -f`. Overrides for non-default paths:
    `TICKER_HOME` and `TICKER_VENV`.

11. **Deploy from the Mac.** Once SSH key login works for `charlie@ticker.local`:

    ```sh
    make deploy              # git pull, pip install, restart, status
    make logs                # follow the journal
    ```

    `make deploy` runs `sudo` over SSH without a terminal, so `charlie` needs
    passwordless sudo on the Pi for these commands. Otherwise run the steps by
    hand on the Pi, or override `PI=` for a different host.

## Configuration

Every key lives in `config.yaml`, and every key is documented there. CLI flags
override it. Run `python -m sportsticker run --check-config` (or `make check-config`) to
validate the file without starting. Defaults below are the values shipped in
`config.yaml`.

| Key | Default | Meaning |
| --- | --- | --- |
| `timezone` | `America/New_York` | Time zone for "today", overnight windows and the brightness schedule. |
| `leagues.<league>` | see file | `true` shows the league, `false` skips it. Order in the file is display order. Known: `nfl`, `ncaaf`, `nba`, `ncaab`, `wnba`, `mlb`, `nhl`, `epl`, `mls`. |
| `favorites.<league>` | `nfl: [KC]`, `ncaab: [CREI]`, `nba: [OKC, CHA]`, `nhl: [STL]`, `epl: [TOT]` | ESPN abbreviations of favorite teams. Favorites sort first, and their live games stay longer. |
| `display.layout` | `a` | Slide layout: `a`, `b`, `c` or `text`. |
| `display.logo_variant` | `auto` | Logo colors: `auto` picks what reads best on black, or force `logo` or `dark`. |
| `display.logos` | `true` | `false` shows abbreviations only. |
| `display.slide_seconds` | `6` | Seconds each slide stays on screen. |
| `display.favorite_live_seconds` | `10` | Seconds for a live game with a favorite team. |
| `display.score_flash_seconds` | `4` | How long the scoring team is highlighted after a score. |
| `display.show_situation` | `true` | Show possession and down and distance when ESPN has them. |
| `display.transitions` | `false` | Horizontal push between slides. Costs some CPU. |
| `display.transition_ms` | `400` | Duration of a transition. |
| `display.animation_fps` | `30` | Frame rate for flashes and transitions only. |
| `brightness.day` | `60` | Brightness 0-100 during the day. Wins over `matrix.brightness` at runtime. |
| `brightness.night` | `15` | Brightness 0-100 at night. |
| `brightness.night_start` | `"22:30"` | Local time the night brightness starts. |
| `brightness.night_end` | `"07:00"` | Local time the day brightness resumes. |
| `polling.live_seconds` | `30` | Poll interval while a shown game is in progress. Never below 30. |
| `polling.idle_seconds` | `300` | Poll interval when no game is live. |
| `polling.overnight_seconds` | `3600` | Poll interval during the overnight window. |
| `polling.overnight_start` | `"01:00"` | Local time the overnight window starts. |
| `polling.overnight_end` | `"08:00"` | Local time the overnight window ends. |
| `polling.timeout_seconds` | `10` | HTTP timeout for each request. |
| `polling.max_backoff_seconds` | `900` | Cap for exponential backoff after errors. |
| `logos.cache_dir` | `~/.cache/sportsticker/logos` | Where logos are cached. Never inside the repo. |
| `logos.max_age_days` | `30` | Re-download logos older than this. |
| `matrix.rows` | `32` | Rows per panel. |
| `matrix.cols` | `64` | Columns per panel. |
| `matrix.chain_length` | `1` | Number of panels daisy-chained. |
| `matrix.parallel` | `1` | Number of chains driven in parallel. |
| `matrix.hardware_mapping` | `adafruit-hat` | Wiring mapping. `adafruit-hat` matches the Bonnet. |
| `matrix.gpio_slowdown` | `4` | GPIO timing slowdown. Raise it if the image is garbled. Pi 4 usually needs 4 or more. |
| `matrix.brightness` | `60` | Driver-level brightness. The day value `brightness.day` wins at runtime. |
| `matrix.panel_type` | `""` | Panel driver chip, for example `FM6126A`. Empty uses the default. |
| `matrix.pwm_bits` | `11` | Color depth in PWM bits. Lower is faster and less colorful. |
| `matrix.pwm_lsb_nanoseconds` | `130` | Base time of the least significant PWM bit. |
| `matrix.pwm_dither_bits` | `0` | Dithering to hide lower color depth. Non-zero saves time per frame. |
| `matrix.scan_mode` | `0` | `0` progressive, `1` interlaced. |
| `matrix.multiplexing` | `0` | Panel multiplexing layout. `0` is the standard layout. |
| `matrix.row_address_type` | `0` | Row addressing type. `0` is the standard for most panels. |
| `matrix.led_rgb_sequence` | `RGB` | Color order. Change it (for example to `RBG`) if colors are swapped. |
| `matrix.pixel_mapper_config` | `""` | Pixel mapper for rotated or unusually wired panels. Empty means none. |
| `matrix.limit_refresh_rate_hz` | `0` | Cap the refresh rate. `0` means no cap. |
| `matrix.show_refresh_rate` | `false` | Print the refresh rate to the console. |
| `matrix.disable_hardware_pulsing` | `false` | Use software pulsing instead of the Pi's hardware pulse. Only for systems where the hardware path fails. |
| `matrix.drop_privileges` | `false` | Drop root after setup. Left off so the logo cache stays writable under the service. |

The `matrix` section is passed straight to `rgbmatrix.RGBMatrixOptions`, and the
emulator accepts the same options.

## Command line

`run` is the default when no command is given.

```text
python -m sportsticker run [--config config.yaml]
    [--backend auto|hardware|emulator|headless]
    [--layout a|b|c|text] [--brightness N] [--slide-seconds N]
    [--leagues nfl,nba] [--replay [DIR]] [--fake-live] [--no-logos]
    [--transitions | --no-transitions] [--profile]
    [--log-level debug|info|warning] [--logo-cache DIR] [--check-config]

python -m sportsticker snapshot [--out snapshots]
    [--source replay|live|fake-live] [--replay DIR]
    [--layouts a,b,c,text] [--no-logos] [--site]

python -m sportsticker logos [--leagues ...]
python -m sportsticker fixtures --out DIR
```

- `--backend auto` (default) uses the real `rgbmatrix` driver if it imports, as
  on a Pi, and otherwise the RGBMatrixEmulator, served at http://localhost:8888.
  `hardware` forces the driver, `emulator` forces the browser emulator, and
  `headless` renders with no output.
- `--replay` with no directory uses the bundled fixtures in
  `tests/fixtures/2026-10-11-sun`.
- `--fake-live` simulates games in progress and score changes. It works with
  `--replay` or with live data.
- `--check-config` validates the config and exits.
- `--logo-cache DIR` overrides `logos.cache_dir`.
- `fixtures --out DIR` saves the current ESPN scoreboard responses as replay
  fixtures.

## Performance

- The render loop redraws only when the picture changes, so a static slide costs
  almost nothing.
- Logos are pre-scaled into the cache, and text is pre-rendered from BDF fonts.
  The render loop does lookups only and never touches the network.
- `--profile` records render timings. `make profile` runs the replay with
  `--fake-live` headless for 60 seconds. On macOS, install `coreutils` and use
  `make profile TIMEOUT=gtimeout`.
- Keep `display.transitions: false` on a Pi 4 unless you need the effect.

## Data source

Scores come from ESPN's unofficial public scoreboard endpoints. This project is
not affiliated with ESPN, and the endpoints can change without notice.

- Polling: every 30 seconds while a shown game is live (never faster), every 5
  minutes when nothing is live, and hourly from 01:00 to 08:00 local time.
- Each request times out after 10 seconds. Errors back off exponentially, up to
  15 minutes.
- A failed poll never clears the screen. The last good data stays up until the
  next successful poll.

## Development

```sh
make install     # pip install -e '.[dev,emulator]'
make test        # pytest -q
make lint        # ruff check and ruff format --check
make format      # ruff fixes and formatting
make check-config
```

CI (`.github/workflows/ci.yml`) runs lint and tests on every push and pull request.
The Pages preview (`.github/workflows/preview.yml`) rebuilds every 30 minutes.

Project layout:

```text
src/sportsticker/
  cli.py        command-line parsing and the run, snapshot, logos and fixtures commands
  app.py        main loop: wires the poller, slides and backend together
  config.py     loads and validates config.yaml, applies CLI overrides
  models.py     Game, Team and Competitor data types
  espn.py       parses ESPN scoreboard JSON into models
  poller.py     polling schedule, backoff and the thread-safe score state
  sources.py    live ESPN, recorded fixtures and the fake-live simulator
  logos.py      logo download, pre-scaling and cache
  colors.py     team and league colors
  bdf.py        loader for the BDF bitmap fonts
  status.py     game status text (live clock, FINAL, start time)
  slides.py     builds the slide sequence, including the clock screen
  backend.py    rgbmatrix or emulator output
  preview.py    turns LED frames into round-pixel and grid views
  snapshot.py   renders snapshot PNGs, the GIF and the site
  site.py       HTML gallery with the pixel inspector
  profile.py    render-loop timing for --profile
  layouts/      slide layouts a, b, c and text, plus the clock screen
  fonts/        BDF fonts and their license
tests/          pytest suite, including tests/fixtures/ replay data
deploy/         ticker.service and install.sh for the Pi
enclosure/      3D-printed case: OpenSCAD model, STLs, renders, print and assembly guide
```

## Licenses

The bundled BDF fonts are in the public domain, except `tom-thumb.bdf`, which is
MIT-licensed. See `src/sportsticker/fonts/FONTS_LICENSE.md`.
