# ![yaatv](docs/docs-assets/yaatv.svg)

![License](https://img.shields.io/github/license/yaatv/yaatv)
![Release](https://img.shields.io/github/v/release/yaatv/yaatv)
![Python](https://img.shields.io/badge/python-3.11+-blue)

yaatv turns audio and cover art into an optimized video for YouTube and other
upload sites.

```sh
yaatv audio.flac cover.jpg
```

Give it audio. Give it artwork. Get a video you can upload.

Browser converter: <https://convert.yaatv.org>

## Downloads

Download a portable ZIP or a single-file executable for your computer from the latest release:

<https://github.com/yaatv/yaatv/releases/latest>

Use one of these release assets:

- Windows x64:
  [`yaatv-windows-x64.zip`](https://github.com/yaatv/yaatv/releases/latest/download/yaatv-windows-x64.zip)
- Linux x64:
  [`yaatv-linux-x64.zip`](https://github.com/yaatv/yaatv/releases/latest/download/yaatv-linux-x64.zip)
- macOS x64:
  [`yaatv-macos-x64.zip`](https://github.com/yaatv/yaatv/releases/latest/download/yaatv-macos-x64.zip)
- macOS arm64:
  [`yaatv-macos-arm64.zip`](https://github.com/yaatv/yaatv/releases/latest/download/yaatv-macos-arm64.zip)

The single-file executables run without extraction:

- Windows x64:
  [`yaatv-windows-x64.exe`](https://github.com/yaatv/yaatv/releases/latest/download/yaatv-windows-x64.exe)
- Linux x64:
  [`yaatv-linux-x64`](https://github.com/yaatv/yaatv/releases/latest/download/yaatv-linux-x64)
- macOS x64:
  [`yaatv-macos-x64`](https://github.com/yaatv/yaatv/releases/latest/download/yaatv-macos-x64)
- macOS arm64:
  [`yaatv-macos-arm64`](https://github.com/yaatv/yaatv/releases/latest/download/yaatv-macos-arm64)

The release also includes a `*-notices.zip` beside each single-file executable. It contains the license,
third-party notices, FFmpeg build details, and source-code notice for that executable. Check `SHA256SUMS`
to verify downloaded release assets.

You can ignore GitHub's "Source code (zip)" and "Source code (tar.gz)" files
unless you specifically want the code.

## Drag and drop

On Windows, drag one audio file and one cover image onto `yaatv.exe` for a
default video next to the audio file.

Use PowerShell when you want to choose the output file, canvas, background, or
padding.

## Quick start

Open PowerShell or a terminal in the extracted folder, install the local media
tools once, check setup, then create a video.

Windows:

```powershell
.\yaatv.exe --install-ffmpeg
.\yaatv.exe --scry
.\yaatv.exe audio.flac cover.jpg
```

Linux:

```sh
chmod +x ./yaatv-linux
./yaatv-linux --install-ffmpeg
./yaatv-linux --scry
./yaatv-linux audio.flac cover.jpg
```

macOS:

```sh
chmod +x ./yaatv-macos
./yaatv-macos --install-ffmpeg
./yaatv-macos --scry
./yaatv-macos audio.flac cover.jpg
```

Use `yaatv-macos-arm64` instead when you download the Apple Silicon ZIP.

### Install a single-file release as a command

The single-file executable can be installed for your user so you can run `yaatv` from any directory. This
does not install FFmpeg; use `--install-ffmpeg` for that.

Windows:

```powershell
.\yaatv-windows-x64.exe --install
```

Linux:

```sh
chmod +x ./yaatv-linux-x64
./yaatv-linux-x64 --install
```

macOS x64 or Apple Silicon:

```sh
chmod +x ./yaatv-macos-x64
./yaatv-macos-x64 --install
```

On Apple Silicon, replace `yaatv-macos-x64` with `yaatv-macos-arm64`.

The installer copies the single-file executable to a per-user location and adds that directory to your user
PATH when needed. Open a new terminal if yaatv reports that it changed PATH. The portable ZIP remains usable
from its extracted directory; `--install` is only supported by the single-file release. Python installations
already provide the `yaatv` command.

## Common uses

Choose an output file:

```sh
yaatv -a episode.wav -i cover.jpg -o output.mp4
```

Use embedded cover art:

```sh
yaatv -a track.flac
```

Open the output folder after a successful encode:

```sh
yaatv -a track.flac -i cover.jpg --open-folder
```

Create a square or vertical video:

```sh
yaatv -a track.flac -i cover.jpg --aspect square
yaatv -a short.wav -i cover.jpg --aspect 9:16
```

Use a larger canvas:

The default is 1080p. Larger presets include 1440p, 4k, and 8k.

```sh
yaatv -a mix.flac -i cover.jpg --resolution 1440p
yaatv -a mix.wav -i cover.png --resolution 8k
```

Choose a background:

```sh
yaatv -a track.flac -i cover.jpg --bg-color "#202020"
yaatv -a track.flac -i cover.jpg --bg-image background.jpg
yaatv -a track.flac -i cover.jpg --bg-blur
```

Create a solid-color video without cover art:

```sh
yaatv -a track.flac --bg-color "#202020"
```

Create a large MOV master:

```sh
yaatv -a track.flac -i cover.jpg -o master.mov
```

Add a short silence pad:

```sh
yaatv -a track.flac -i cover.jpg --pad 2
```

Compatible high-quality AAC-LC audio is copied when no padding is requested.
Adding silence with `--pad` requires AAC encoding so yaatv can apply the audio
filter.

## Output profiles and large MOV files

MP4 uses H.264 High Profile with `yuv420p` video and AAC-LC audio at 48 kHz.

MOV uses ProRes 422 HQ with `yuv422p10le` video and 24-bit PCM audio at 48 kHz.
Converting lossy input to PCM does not restore information lost in the source.

ProRes MOV files can be very large. When the audio duration is available, yaatv
prints an approximate size and the free space on the destination filesystem. It
warns at estimates of 2 GiB or more and stops before encoding when the estimated
output plus a safety reserve will not fit. On Windows, it also checks the FAT32
single-file limit when the filesystem can be identified. `--dry-run` reports
capacity problems but still prints the command. ProRes is variable-bitrate, so
the size estimate is approximate. yaatv also warns when the known output
duration exceeds YouTube's 12-hour limit or a ProRes estimate exceeds its 256 GB
upload limit. These upload-limit warnings do not stop rendering. See
[YouTube's upload limits](https://support.google.com/youtube/answer/71673).

## What to expect

- yaatv keeps cover art from stretching.
- Audio with embedded cover art can be used without `-i`.
- Square album art works well for square videos.
- WAV, FLAC, and high-bitrate AAC are good source choices.
- JPG, PNG, and static WebP are good cover choices.
- Animated images are rejected.
- Common source audio metadata (such as title, artist, album, and date) is preserved into video outputs where supported.
- The planned output file appears before encoding starts.
- yaatv shows simple progress while encoding and verifying.
- Post-encode FFprobe verification has a 30-second timeout. If verification
  fails or times out, the unverified output is removed and any existing
  output being replaced is preserved.
- Existing output files require confirmation before replacement.
- Warnings appear when source audio, image size, or file extensions may be
  less than ideal.
- After a successful encode, yaatv may show a notice when its cached status knows
  about a newer stable release. It does not download or install updates.

## Supported input formats

| Input type | Supported extensions |
| --- | --- |
| Audio | `.aac`, `.aiff`, `.alac`, `.flac`, `.m4a`, `.mp3`, `.ogg`, `.opus`, `.wav`, `.wma` |
| Images | `.bmp`, `.jpeg`, `.jpg`, `.png`, `.tif`, `.tiff`, `.webp` |
| Output | `.mov`, `.mp4` |

## Options

| Option | Purpose |
| --- | --- |
| Positional files | Use one audio file and one cover image. |
| `-a`, `--audio` | Choose the audio file. |
| `-i`, `--image` | Choose the cover image. |
| `-b`, `--bg-image` | Choose a background image. |
| `--bg-color` | Choose a background color. |
| `--bg-blur` | Use a blurred copy of the cover image as the background. |
| `-o`, `--output` | Choose an `.mp4` or `.mov` output file. A `.mov` path creates ProRes MOV output. |
| `--output-dir` | Choose the folder for the default output filename. |
| `--resolution` | Choose `1080p`, `1440p`, `4k`, or `8k`. |
| `--aspect` | Choose `16:9`, `square`, or `9:16`. |
| `--pad` | Add 0 through 10 seconds of silence at the end. |
| `--no-warn` | Hide source quality warnings. |
| `--dry-run` | Print the command and ProRes preflight information without creating a file. |
| `--verbose` | Show raw encoding output. |
| `--overwrite` | Replace an existing output file without asking first. |
| `--open-folder` | Open the output folder after a successful encode. |
| `--install` | Install the running single-file release for the current user. |
| `--install-ffmpeg` | Install local media tools for yaatv. |
| `--scry` | Check yaatv, media tools, and output folder setup. |

## Troubleshooting

Run `yaatv --scry` when setup looks wrong.

If macOS blocks the downloaded executable, allow it from System Settings, or
remove the quarantine flag:

```sh
xattr -d com.apple.quarantine ./yaatv-macos-x64
```

Use the downloaded executable's filename in that command, such as `yaatv-macos-arm64` on Apple Silicon.
For a ZIP release, use the extracted executable's name instead.

If an output file already exists, choose a different output path, confirm
replacement, or use `--overwrite` deliberately.

## Examples

Real videos generated by yaatv and uploaded to YouTube:

- [Square artwork (4K)](https://www.youtube.com/watch?v=T6CpHPz9WJ4): ProRes `.mov`, 4K (3840&times;2160), 2160&times;2160 square image padded onto 16:9 canvas, 32-bit `.wav` audio.
- [Full-frame 16:9 (4K)](https://www.youtube.com/watch?v=O-B-FxHvz5c): ProRes `.mov`, 4K (3840&times;2160), 3840&times;2160 full-frame image, 32-bit `.wav` audio.

## Python install

Most people should use the release ZIPs. If you prefer a Python install:

```sh
python -m pip install "git+https://github.com/yaatv/yaatv.git"
yaatv --version
```

Python 3.11 or newer is required.

Python installs still need the local media tools. Run:

```sh
yaatv --install-ffmpeg
yaatv --scry
```

## License

yaatv is licensed under the GNU General Public License v2 or later (GPL-2.0-or-later).
Standalone release ZIPs include `LICENSE`, `THIRD_PARTY_LICENSES.txt` (recording third-party
runtime dependencies and build components), `SOURCE.txt`, and `FFMPEG_BUILD_INFO.txt`.

### Third-party dependencies

| Package | License | Purpose | Source |
|---|---|---|---|
| [`mutagen`](https://github.com/quodlibet/mutagen) | GPL-2.0-or-later | Audio metadata and tag reading | [PyPI](https://pypi.org/project/mutagen/) |
| [`Pillow`](https://github.com/python-pillow/Pillow) | MIT-CMU / HPND | Cover art dimensions and validation | [PyPI](https://pypi.org/project/pillow/) |

## Development

Install the project with test and build tools:

```sh
python -m pip install -e ".[dev]"
```

Run the same checks used by CI:

```sh
yaatv --version
python -m yaatv --version
python -m ruff check .
python -m mypy
python -m bandit -c pyproject.toml -r yaatv
python -m piplicenses --packages mutagen pillow --with-urls
python -m pip_audit . --strict
python -m pytest
python -m build
python -m twine check dist/*
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup,
workflows, and guidelines.

- Look through [good first issues](https://github.com/yaatv/yaatv/labels/good%20first%20issue)
  to get started. Before starting on an issue, it is best to comment that you
  plan to work on it so others can avoid overlapping effort.
- Report bugs or suggest features on the [issue tracker](https://github.com/yaatv/yaatv/issues).
- Read the [AI Contribution Policy](.AI_POLICY/README.md).
- See [CONTRIBUTORS](CONTRIBUTORS) for recognition of everyone who has helped
  build and test yaatv.
- Read our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before participating.

## Publishing

Tagging a version that starts with `v` builds the portable ZIP and single-file
executable for Windows, Linux, macOS x64, and macOS arm64. The release includes
companion notices ZIPs for the single-file executables, SPDX Software Bills of
Materials (`.spdx.json`), and `SHA256SUMS`.

```sh
git tag v<version>
git push origin main --tags
```
