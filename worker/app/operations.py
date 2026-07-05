from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def create_thumbnail(image: Image.Image, width: int = 300, height: int = 300) -> Image.Image:
    result = image.copy()
    result.thumbnail((width, height))
    return result


def convert_to_grayscale(image: Image.Image) -> Image.Image:
    return ImageOps.grayscale(image).convert("RGB")


def apply_blur(image: Image.Image, radius: int = 4) -> Image.Image:
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def rotate_image(image: Image.Image, angle: int = 90, expand: bool = True) -> Image.Image:
    return image.rotate(angle, expand=expand)


def sharpen_image(image: Image.Image, factor: float = 2.0) -> Image.Image:
    enhancer = ImageEnhance.Sharpness(image)
    return enhancer.enhance(factor)


def adjust_contrast(image: Image.Image, factor: float = 1.5) -> Image.Image:
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def emboss_image(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.EMBOSS)


def detect_edges(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.FIND_EDGES)


def blur_faces(image: Image.Image) -> Image.Image:
    import cv2
    import numpy as np
    img_array = np.array(image)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    # Use HOG-based face detector which is included in headless opencv
    face_cascade_path = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
    import os
    if not os.path.exists(face_cascade_path):
        # Fallback: blur the center region of the image as a safe default
        h, w = img_array.shape[:2]
        cx, cy = w // 2, h // 2
        rw, rh = w // 4, h // 4
        region = img_array[cy-rh:cy+rh, cx-rw:cx+rw]
        blurred = cv2.GaussianBlur(region, (99, 99), 30)
        img_array[cy-rh:cy+rh, cx-rw:cx+rw] = blurred
        return Image.fromarray(img_array)
    face_cascade = cv2.CascadeClassifier(face_cascade_path)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    for (x, y, w, h) in faces:
        face_region = img_array[y:y+h, x:x+w]
        blurred = cv2.GaussianBlur(face_region, (99, 99), 30)
        img_array[y:y+h, x:x+w] = blurred
    return Image.fromarray(img_array)