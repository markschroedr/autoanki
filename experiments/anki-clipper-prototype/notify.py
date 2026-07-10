"""Cross-platform user notifications."""
import platform
import subprocess


def notify(title: str, message: str):
    """Show a desktop notification (best effort)."""
    system = platform.system()

    if system == "Darwin":
        title_escaped = title.replace('"', '\\"')
        message_escaped = message.replace('"', '\\"')
        script = f'display notification "{message_escaped}" with title "{title_escaped}"'
        subprocess.run(["osascript", "-e", script], capture_output=True)
        return

    if system == "Windows":
        # WScript popup works on stock Windows and auto-closes after 4s.
        title_escaped = title.replace("'", "''")
        message_escaped = message.replace("'", "''")
        ps = (
            "$wshell = New-Object -ComObject Wscript.Shell; "
            f"$wshell.Popup('{message_escaped}', 4, '{title_escaped}', 64) | Out-Null"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
        return

    print(f"[{title}] {message}")
