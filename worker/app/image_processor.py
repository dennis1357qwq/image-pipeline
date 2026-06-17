from PIL import Image

from app.operations import (
    apply_blur,
    convert_to_grayscale,
    create_thumbnail,
)

OPERATION_REGISTRY = {
    "thumbnail": create_thumbnail,
    "grayscale": convert_to_grayscale,
    "blur": apply_blur,
}


def process_image(image: Image.Image, operation: str) -> Image.Image:
    normalized_image = image.convert("RGB")

    processing_function = OPERATION_REGISTRY.get(operation)

    if processing_function is None:
        raise ValueError(f"Unknown operation: {operation}")

    return processing_function(normalized_image)