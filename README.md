![Hello.](.github/title.png)

# Cassette

**Create stunning Glyphtones — easier than ever.**

It’s an early release: it works well but can be temperamental. If you enjoy experimenting, welcome aboard.

## Table of contents

* [System requirements](#system-requirements)
* [Installation](#installation-and-running)
* [Real - time preview on your phone](#real---time-preview-on-your-phone)
* [FAQ & Troubleshooting](#faq--troubleshooting)
* [Roadmap](#roadmap)
* [Contact](#contact)

## System requirements

Recommended for a smooth experience:

* **Memory**: 8 GB RAM or more
* **CPU**: 4-core processor
* **Clock speed**: 2.0 GHz or higher
* **Free disk space**: 1 GB+

## Installation and running

1. Download the appropriate release from the Releases page.
- **Important:** The `nopython` package requires **Python 3.10** installed on your system. Cassette supports Python 3.10 only.

2. Unpack the archive.
3. Start Cassette:

* **Windows**: `Cassette.bat`
* **Windows-nopython**: `Cassette-nopython.bat`
* **Linux / macOS**: `Cassette.sh`

## Real - time preview on your phone

To enable live ringtone preview on a connected phone:

1. Enable **Developer Options → USB debugging** on your Phone:
* Settings → About phone → Press on Phone image → Tap Build number 7 times
* System → Developer options → Enable USB debugging.
2. Connect your Phone to the PC: **USB - C** or **USB - A** cable.
3. Accept the connection prompt on the phone. **Recommended to enable "Always allow" checkbox.
4. Install the **Cassette Receiver** app on your Nothing Phone. Cassette will ask you if you want to install it automatically

**Note:** Live preview has been tested on Nothing Phone 3a and 1. Other devices may not work, if so, please text me in discord.

## FAQ & Troubleshooting

### Error: `Failed to build Aubio==0.4.9`

Possible causes and steps:

1. Make sure you are using **Python 3.10** — many prebuilt wheels target that version.
2. Consider installing aubio via your OS package manager or use Conda for prebuilt binaries.

### Phone not detected by Cassette

1. Try a different cable and port. Some cables are power - only.
2. Confirm Cassette Receiver is installed on the phone.
3. Ensure USB debugging is enabled and the phone has accepted the PC's connection.

### Can we get more effects?

New effects are in development. In the meantime, you can layer effects by placing one glyph, applying effect A, then placing another glyph on top with effect B.

## Roadmap

* Undo / Redo
* Glyph UI preview window

## Contact
- Discord only: **chips047**