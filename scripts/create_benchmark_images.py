from pathlib import Path

from PIL import Image


INPUT_IMAGE = Path("worker/examples/image-medium.jpg")

OUTPUTS = {
    "image-small.jpg": (768, 768),
    "image-medium.jpg": (3024, 3024),   # Originalgröße
    "image-large.jpg": (4096, 4096),
}

JPEG_QUALITY = 90


def main():
    img = Image.open(INPUT_IMAGE).convert("RGB")

    output_dir = INPUT_IMAGE.parent

    for filename, size in OUTPUTS.items():
        out = img.resize(size, Image.Resampling.LANCZOS)

        output_path = output_dir / filename

        out.save(
            output_path,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
        )

        print(
            f"{filename:18} "
            f"{size[0]}x{size[1]}"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()