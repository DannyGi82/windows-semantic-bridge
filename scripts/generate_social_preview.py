"""Produce a GitHub social-preview image from the project's ACTUAL Chrome capture.

The browser screenshot remains authentic. The left title and frame are
purely presentation; no application UI or fake screenshot is generated.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "assets" / "demo-browser-lane.png"
OUTPUT = ROOT / "assets" / "social-preview.png"

def font(size, bold=False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    path = Path("C:/Windows/Fonts") / name
    if path.is_file():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()

def main():
    if not INPUT.is_file():
        raise FileNotFoundError(INPUT)
    source = Image.open(INPUT).convert("RGB")
    board = Image.new("RGB", (1280, 640), "#07111e")
    draw = ImageDraw.Draw(board)
    draw.rectangle((0, 0, 1279, 639), outline="#1a4867", width=4)
    draw.rounded_rectangle((345, 33, 1250, 610), radius=13, fill="#122238", outline="#3db6d5", width=2)
    # Preserve the captured image pixel content apart from ordinary resizing.
    screenshot = source.resize((879, 543), Image.Resampling.LANCZOS)
    board.paste(screenshot, (358, 50))
    draw.rounded_rectangle((34, 44, 305, 86), radius=20, fill="#103042", outline="#23718a", width=1)
    draw.text((52, 55), "OPEN SOURCE · WINDOWS", fill="#53e3ef", font=font(17, True))
    for i, line in enumerate(("Windows", "Semantic", "Bridge")):
        draw.text((34, 166 + i * 67), line, fill="#e6f8ff" if i == 0 else "#49d6e5", font=font(48, True))
    draw.line((35, 396, 273, 396), fill="#1e7187", width=2)
    draw.text((35, 425), "Observe. Plan.", fill="#d4ebf2", font=font(22, True))
    draw.text((35, 460), "Keep your focus.", fill="#d4ebf2", font=font(22, True))
    draw.text((35, 558), "REAL CHROME DEMO", fill="#5bdbe7", font=font(15, True))
    draw.text((35, 582), "Agent-owned tabs only", fill="#85a7bb", font=font(14))
    board.save(OUTPUT, "PNG", optimize=True)
    print(str(OUTPUT), OUTPUT.stat().st_size)

if __name__ == "__main__":
    main()
