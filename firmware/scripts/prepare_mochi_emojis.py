"""Preview and resize the user-provided Mochi GIFs for Freenove's 320x240 display.

Run with the bundled Pillow Python and the directory containing the original
"Emoji Dasai Mochi_*.gif" files. Generated GIFs are committed as board assets;
the original multi-megabyte files are not needed to build the firmware.
"""

from __future__ import annotations

import argparse
import bisect
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "main"
FACES = {
    "neutral": "Trunglap",
    "happy": "vuive",
    "laughing": "cuoilon",
    "sad": "buon",
    "crying": "khoc",
    "sleepy": "buonngu",
    "surprised": "batngo2",
    "thinking": "suynghi",
    "winking": "nhaymat",
    "loving": "yeuthuong",
    "angry": "giandu",
    "confident": "tutin",
}
FRAME_SIZE = (224, 136)
FRAME_DURATION_MS = 150


def source_file(source: Path, name: str) -> Path:
    return source / f"Emoji Dasai Mochi_{name}.gif"


def preview(source: Path) -> Path:
    paths = sorted(source.glob("Emoji Dasai Mochi_*.gif"))
    sheet = Image.new("RGB", (6 * 220, 6 * 170), "#101010")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        image = Image.open(path)
        image.seek(max(0, image.n_frames // 2))
        frame = image.convert("RGB")
        frame.thumbnail((216, 138), Image.Resampling.LANCZOS)
        x = (index % 6) * 220
        y = (index // 6) * 170
        sheet.paste(frame, (x + (220 - frame.width) // 2, y))
        draw.text((x + 6, y + 141), path.stem.split("_")[-1], fill="white")
    output = ROOT / "mochi_contact_sheet.png"
    sheet.save(output)
    return output


def resize_frame(frame: Image.Image) -> Image.Image:
    # Decode a smaller canvas and let LVGL center it. A 224x136 frame has 40%
    # fewer pixels than the previous 288x176 asset while remaining prominent
    # on the 320x240 panel. A calm 150 ms cadence also lowers sustained display load.
    return frame.convert("RGB").resize(FRAME_SIZE, Image.Resampling.LANCZOS).quantize(
        colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


def optimize(source: Path, face: str, original: str) -> tuple[Path, int]:
    image = Image.open(source_file(source, original))
    starts = []
    cursor = 0
    for index in range(image.n_frames):
        image.seek(index)
        starts.append(cursor)
        cursor += max(30, image.info.get("duration", 80))
    count = min(18, max(12, round(cursor / FRAME_DURATION_MS)))
    duration = FRAME_DURATION_MS
    frames = []
    for step in range(count):
        source_index = bisect.bisect_right(starts, round(step * cursor / count)) - 1
        image.seek(max(0, source_index))
        frames.append(resize_frame(image))
    brightness = [sum(frame.convert("L").resize((32, 24)).getdata()) for frame in frames]
    threshold = max(brightness) * 0.75
    first_visible = next((index for index, value in enumerate(brightness)
                          if value >= threshold), 0)
    frames = frames[first_visible:] + frames[:first_visible]
    output = OUTPUT / f"mochi_{face}.gif"
    frames[0].save(output, save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, disposal=1, optimize=True)
    return output, output.stat().st_size


def preview_result() -> Path:
    canvas = Image.new("RGB", (4 * 320, 3 * 268), "#101010")
    draw = ImageDraw.Draw(canvas)
    for index, face in enumerate(FACES):
        image = Image.open(OUTPUT / f"mochi_{face}.gif")
        image.seek(min(image.n_frames - 1, image.n_frames // 2))
        x = (index % 4) * 320
        y = (index // 4) * 268
        frame = image.convert("RGB")
        canvas.paste(frame, (x + (320 - frame.width) // 2, y + (240 - frame.height) // 2))
        draw.text((x + 8, y + 246), face, fill="white")
    output = ROOT / "mochi_faces_preview.png"
    canvas.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        total = 0
        for face, original in FACES.items():
            output, size = optimize(args.source, face, original)
            print(f"{output.name}: {size:,} bytes")
            total += size
        print(f"Total: {total:,} bytes")
        print(preview_result())
    else:
        print(preview(args.source))


if __name__ == "__main__":
    main()
