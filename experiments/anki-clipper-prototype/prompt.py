"""Prompt for optional focus hint."""
import platform
import subprocess


def ask_focus_hint() -> str | None:
    """Show a dialog asking for optional focus instructions."""
    if platform.system() == "Darwin":
        script = """
        display dialog "What should the flashcard focus on? (optional)" default answer "" buttons {"Cancel", "Create Card"} default button "Create Card" with title "Anki Clipper"
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return None

        if result.returncode != 0:
            return None

        output = result.stdout.strip()
        if "text returned:" in output:
            hint = output.split("text returned:")[-1].strip()
            return hint if hint else None
        return None

    try:
        import tkinter as tk
        from tkinter import simpledialog
    except Exception:
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        hint = simpledialog.askstring(
            title="Anki Clipper",
            prompt="What should the flashcard focus on? (optional)",
            parent=root,
        )
    except Exception:
        return None
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    if hint is None:
        return None
    hint = hint.strip()
    return hint if hint else None
