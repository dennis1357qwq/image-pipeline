from PIL import Image, ImageFilter, ImageOps

def create_thumbnail(image: Image.Image, size: tuple[int, int] = (300, 300)) -> Image.Image:
	result = image.copy()
	result.thumbnail(size)
	return result

def convert_to_grayscale(image: Image.Image) -> Image.Image:
	return ImageOps.grayscale(image).convert("RGB")

def apply_blur(image: Image.Image, radius: int = 4) -> Image.Image:
	return image.filter(ImageFilter.GaussianBlur(radius=radius))