![Hello.](.github/title.png)

# Cassette

**Shine vintage.**

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
* **CPU**: 4 - core processor
* **Clock speed**: 2.0 GHz or higher
* **Free disk space**: 500 MB+

**Requires installed FFMpeg:**
- **Windows**\
PowerShell: `winget install ffmpeg`

- **Linux**\
**Arch:** `sudo pacman -S ffmpeg`\
**Ubuntu:** `sudo apt install ffmpeg`\
**Fedora:** `sudo dnf install ffmpeg`\
**Debian:** `sudo apt install ffmpeg`

- [You can also check FFMpeg packages here.](https://ffmpeg.org/download.html)

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
- Make sure you are using **Python 3.10** - prebuilt wheels target that version.

### Phone not detected by Cassette

1. Try a different cable and port. Some cables are power - only.
2. Confirm Cassette Receiver is installed on the phone. But, you don't have to start it.
3. Ensure USB debugging is enabled and the phone has accepted the PC's connection.

## Roadmap

* Undo / Redo
* Glyph UI preview window
* Import from BNGC and Audacity Label File.
* MAYBE an auto ringtone creator.

## Contact
- Discord only: **chips047**