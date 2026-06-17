from pathlib import Path
from PIL import Image

from app.image_processor import process_image

input_path = Path("examples/test.png")  # oder .jpg, .jpeg, .webp ...
output_path = Path("output/result.png")

output_path.parent.mkdir(exist_ok=True)

with Image.open(input_path) as image:
    result = process_image(
        image=image,
        operation="blur",
    )

result.save(output_path)
print(f"Created {output_path}")