from typing import Any

from PIL import Image

from app.operations import (
    apply_blur,
    convert_to_grayscale,
    create_thumbnail,
    detect_edges,
    emboss_image,
    rotate_image,
    sharpen_image,
    adjust_contrast,
)
from image_pipeline_common.models import PipelineStep


OPERATION_REGISTRY = {
    "thumbnail": create_thumbnail,
    "grayscale": convert_to_grayscale,
    "blur": apply_blur,
    "rotate": rotate_image,
    "sharpen": sharpen_image,
    "contrast": adjust_contrast,
    "emboss": emboss_image,
    "edge_detect": detect_edges,
}


def process_image(image: Image.Image, pipeline: list[PipelineStep]) -> Image.Image:
    current_image = image.convert("RGB")
    for step in pipeline:
        current_image = apply_pipeline_step(current_image, step)
    return current_image


def apply_pipeline_step(image: Image.Image, step: PipelineStep) -> Image.Image:
    processing_function = OPERATION_REGISTRY.get(step.operation)

    if processing_function is None:
        raise ValueError(f"Unknown operation: {step.operation}")

    parameters = dict(step.parameters)
    repeat = int(parameters.pop("repeat", 1))
    region = parameters.pop("region", None)

    result = image

    for _ in range(repeat):
        if region is None:
            result = processing_function(result, **parameters)
        else:
            result = apply_to_region(
                image=result,
                processing_function=processing_function,
                parameters=parameters,
                region=region,
            )

    return result


def apply_to_region(image: Image.Image, processing_function, parameters: dict[str, Any], region: dict[str, int]) -> Image.Image:
    x = int(region["x"])
    y = int(region["y"])
    width = int(region["width"])
    height = int(region["height"])

    left = x
    upper = y
    right = x + width
    lower = y + height

    image_copy = image.copy()
    cropped_region = image_copy.crop((left, upper, right, lower))
    processed_region = processing_function(cropped_region, **parameters)
    image_copy.paste(processed_region, (left, upper))

    return image_copy