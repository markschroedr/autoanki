"""Cross-platform clipboard reading."""
import base64
import platform
import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageGrab


def _image_to_b64(img: Image.Image) -> str:
    """Encode a PIL image as base64 PNG."""
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _get_image_from_pillow() -> str | None:
    """Read image data from clipboard using Pillow."""
    try:
        clip = ImageGrab.grabclipboard()
    except Exception:
        return None

    if isinstance(clip, Image.Image):
        return _image_to_b64(clip)

    # Windows can return a list of file paths copied from Explorer.
    if isinstance(clip, list):
        for item in clip:
            path = Path(item)
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"} and path.exists():
                try:
                    with Image.open(path) as img:
                        return _image_to_b64(img)
                except Exception:
                    continue

    return None


def _get_image_from_macos_pasteboard() -> str | None:
    """Read image data from macOS NSPasteboard if pyobjc is available."""
    try:
        from AppKit import NSPasteboard, NSPasteboardTypePNG, NSPasteboardTypeTIFF
    except Exception:
        return None

    try:
        pb = NSPasteboard.generalPasteboard()
        for img_type in [NSPasteboardTypePNG, NSPasteboardTypeTIFF]:
            data = pb.dataForType_(img_type)
            if data:
                img = Image.open(BytesIO(data.bytes()))
                return _image_to_b64(img)
    except Exception:
        return None

    return None


def _run_capture(cmd: list[str], timeout: int = 5) -> str | None:
    """Run a command and return stdout when successful and non-empty."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None

    if result.returncode != 0:
        return None

    out = result.stdout
    if not out:
        return None
    return out.rstrip("\r\n")


def _get_text_tk() -> str | None:
    """Use tkinter as a fallback for clipboard text."""
    try:
        import tkinter as tk
    except Exception:
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        return text if text else None
    except Exception:
        return None
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def _get_text() -> str | None:
    """Read text from clipboard on the current platform."""
    system = platform.system()
    if system == "Windows":
        text = _run_capture(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"])
        return text if text else _get_text_tk()

    if system == "Darwin":
        text = _run_capture(["pbpaste"])
        return text if text else _get_text_tk()

    return _get_text_tk()


def get_clipboard() -> tuple[str | None, str | None]:
    """Get clipboard content. Returns (text, image_base64) tuple."""
    system = platform.system()

    # Prefer image when both are present, matching existing behavior.
    image_b64 = None
    if system == "Darwin":
        image_b64 = _get_image_from_macos_pasteboard() or _get_image_from_pillow()
    else:
        image_b64 = _get_image_from_pillow()

    if image_b64:
        return None, image_b64

    text = _get_text()
    if text:
        return text, None

    return None, None
