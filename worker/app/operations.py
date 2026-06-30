from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def create_thumbnail(
    image: Image.Image,
    width: int = 300,
    height: int = 300,
) -> Image.Image:
    result = image.copy()
    result.thumbnail((width, height))
    return result


def convert_to_grayscale(image: Image.Image) -> Image.Image:
    return ImageOps.grayscale(image).convert("RGB")


def apply_blur(image: Image.Image, radius: int = 4) -> Image.Image:
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def rotate_image(
    image: Image.Image,
    angle: int = 90,
    expand: bool = True,
) -> Image.Image:
    return image.rotate(angle, expand=expand)


def sharpen_image(
    image: Image.Image,
    factor: float = 2.0,
) -> Image.Image:
    enhancer = ImageEnhance.Sharpness(image)
    return enhancer.enhance(factor)


def adjust_contrast(
    image: Image.Image,
    factor: float = 1.5,
) -> Image.Image:
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def emboss_image(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.EMBOSS)


def detect_edges(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.FIND_EDGES)