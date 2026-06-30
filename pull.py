#!/usr/bin/env python3
"""
NotionPull — Docker-powered Notion page scraper with auto-cleanup.

Usage:
    python pull.py <notion-url> <destination> [options]
    python pull.py -i                            # interactive mode
    python pull.py --help

Examples:
    python pull.py https://user.notion.site/MyPage-abc123 ./backups/my-page
    python pull.py -d -t 30 https://user.notion.site/MyPage-abc123 .
    python pull.py -i
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Optional, List

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

PROJECT_ROOT = Path(__file__).parent.resolve()
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
SNAPSHOTS_DIR = PROJECT_ROOT / "snapshots"
CONTAINER_SERVICE = "main"
IMAGE_NAME = "notionpull-main"
CONTAINER_RUN_NAME = "notionpull-run"

console = Console() if HAS_RICH else None

# ── output helpers ──────────────────────────────────────────────────────────


def echo(msg: str = "", style: str = "", err: bool = False) -> None:
    out = sys.stderr if err else sys.stdout
    if HAS_RICH and console:
        (console.print(msg, style=style) if style else console.print(msg))
    else:
        print(msg, file=out)


def link(text: str, url: str) -> str:
    if HAS_RICH:
        return f"[link={url}]{text}[/link]"
    return f"{text} ({url})"


def panel(title: str, content: str, style: str = "cyan") -> None:
    if HAS_RICH and console:
        console.print(Panel(content, title=title, border_style=style))
    else:
        sep = "─" * 60
        print(f"\n{sep}\n{title}\n{content}\n{sep}")


def confirm(prompt_text: str, default_no: bool = False) -> bool:
    suffix = " [y/N]" if default_no else " [Y/n]"
    if HAS_RICH and console:
        raw = input(Text.assemble((prompt_text, "bold cyan"), (suffix, "dim")).plain)
    else:
        raw = input(f"{prompt_text}{suffix} ")
    raw = raw.strip().lower()
    if not raw:
        return not default_no
    return raw.startswith("y")


def ask(prompt_text: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    sep = " → " if not hint else f"{hint} → "
    try:
        if HAS_RICH and console:
            raw = input(Text.assemble((prompt_text, "bold cyan"), (sep, "dim white")).plain)
        else:
            raw = input(f"{prompt_text}{sep}")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(130)
    return raw.strip() or default


# ── docker helpers ──────────────────────────────────────────────────────────


def _docker_cmd(*args: str) -> List[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]


def docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def image_exists() -> bool:
    return subprocess.run(["docker", "image", "inspect", IMAGE_NAME], capture_output=True).returncode == 0


# ── build ───────────────────────────────────────────────────────────────────


def build_image(rebuild: bool = False, timeout: int = 300) -> None:
    if not rebuild and image_exists():
        echo("Docker image already built. Use --rebuild to force rebuild.", style="dim")
        return

    echo("Building Docker image (first build downloads Chrome + Python 3.11 — may take a few minutes)...",
         style="bold yellow")
    result = subprocess.run(
        _docker_cmd("build"), capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        echo("Build failed:", style="bold red")
        echo(result.stderr[-1500:] if len(result.stderr) > 1500 else result.stderr, style="red")
        sys.exit(1)
    echo("Image built successfully.", style="bold green")


# ── run ─────────────────────────────────────────────────────────────────────


def run_snapshot(
    url: str,
    dark_mode: bool = False,
    timeout_sec: int = 60,
    show_browser: bool = False,
    disable_caching: bool = False,
) -> int:
    ns_args = ["notionpull"]
    if dark_mode:
        ns_args.append("-d")
    if show_browser:
        ns_args.append("-b")
    if disable_caching:
        ns_args.append("-c")
    ns_args.extend(["-t", str(timeout_sec)])
    ns_args.append(url)

    cmd = _docker_cmd(
        "run", "--rm", "--name", CONTAINER_RUN_NAME,
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--env", "HOME=/tmp",
        CONTAINER_SERVICE, "python", *ns_args,
    )

    echo(f"Snapping {link(url, url)} ...", style="cyan")
    sys.stdout.flush()

    proc = subprocess.Popen(cmd)
    try:
        proc.wait()
    except KeyboardInterrupt:
        echo("\nInterrupted. Stopping container...", style="bold yellow")
        _kill_container()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return 130

    if proc.returncode != 0:
        echo(f"Snapshot failed (exit code {proc.returncode})", style="bold red")
        return proc.returncode

    echo("Snapshot completed.", style="bold green")
    return 0


# ── output management ───────────────────────────────────────────────────────


def find_latest_snapshot() -> Optional[Path]:
    if not SNAPSHOTS_DIR.exists():
        return None
    dirs = sorted(
        [d for d in SNAPSHOTS_DIR.iterdir() if d.is_dir()],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    return dirs[0] if dirs else None


def copy_output_to(src: Path, dest: Path) -> None:
    dest = dest.resolve()
    if dest.exists():
        (shutil.rmtree(dest) if dest.is_dir() else dest.unlink())
    shutil.copytree(src, dest)
    echo(f"Snapshot saved → {link(str(dest), f'file://{dest}')}", style="bold green")
    idx = dest / "index.html"
    if idx.exists():
        echo(f"  Open index → {link(str(idx), f'file://{idx}')}", style="dim")


def _kill_container(name: str = CONTAINER_RUN_NAME) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


# ── cleanup ─────────────────────────────────────────────────────────────────


def cleanup_container() -> None:
    _kill_container()


def cleanup_snapshots() -> None:
    if not SNAPSHOTS_DIR.exists():
        return
    try:
        shutil.rmtree(SNAPSHOTS_DIR)
    except PermissionError:
        echo("Snapshots dir has root-owned files (from previous run). Attempting sudo cleanup...", style="yellow")
        rc = subprocess.run(["sudo", "rm", "-rf", str(SNAPSHOTS_DIR)], capture_output=True)
        if rc.returncode != 0:
            echo(f"Could not clean snapshots. Manually remove: {SNAPSHOTS_DIR}", style="bold red")


def cleanup_image() -> None:
    subprocess.run(["docker", "rmi", "-f", IMAGE_NAME], capture_output=True)


def full_cleanup(keep_image: bool = True, verbose: bool = True) -> None:
    cleanup_container()
    cleanup_snapshots()
    if not keep_image:
        cleanup_image()
        if verbose:
            echo("Docker image removed.", style="dim")
    if verbose:
        echo("Cleanup done.", style="dim")


# ── interactive mode ────────────────────────────────────────────────────────


def interactive_mode() -> None:
    panel("NotionPull",
          "Paste your Notion page URL, choose a destination, and let the tool do the rest.")

    url = ask("Notion page URL")
    while not url or "notion" not in url:
        echo("A valid Notion URL is required (e.g. https://user.notion.site/MyPage-abc123).", style="red")
        url = ask("Notion page URL")

    dest_raw = ask("Destination folder", default=f"./snapshot-{int(time.time())}")
    dest = Path(dest_raw).expanduser().resolve()

    dark = confirm("Dark mode?")
    timeout_raw = ask("Timeout (seconds)", default="60")
    try:
        timeout_sec = max(10, int(timeout_raw))
    except ValueError:
        timeout_sec = 60
    no_cache = confirm("Disable caching?", default_no=True)

    _execute(
        url=url, dest=dest,
        dark_mode=dark, timeout_sec=timeout_sec,
        disable_caching=no_cache,
    )


# ── core execute ────────────────────────────────────────────────────────────


def _execute(
    url: str,
    dest: Path,
    dark_mode: bool = False,
    timeout_sec: int = 60,
    show_browser: bool = False,
    disable_caching: bool = False,
    rebuild: bool = False,
    no_cleanup: bool = False,
) -> None:
    if not docker_available():
        echo("Docker is not available. Install Docker Desktop or the Docker Engine and try again.",
             style="bold red")
        sys.exit(1)

    build_image(rebuild=rebuild)

    if SNAPSHOTS_DIR.exists() and not os.access(SNAPSHOTS_DIR, os.W_OK):
        echo("Snapshots directory is not writable (likely root-owned from a previous run). Cleaning up...", style="yellow")
        cleanup_snapshots()
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    rc = run_snapshot(
        url=url, dark_mode=dark_mode,
        timeout_sec=timeout_sec, show_browser=show_browser,
        disable_caching=disable_caching,
    )
    if rc != 0:
        if not no_cleanup:
            cleanup_container()
        sys.exit(rc)

    snap = find_latest_snapshot()
    if snap is None:
        echo("No snapshot output found. The page may have failed to load.", style="bold red")
        if not no_cleanup:
            full_cleanup()
        sys.exit(1)

    dest.mkdir(parents=True, exist_ok=True)
    copy_output_to(snap, dest)

    if not no_cleanup:
        cleanup_snapshots()
        cleanup_container()


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pull.py",
        description="NotionPull — Docker-powered Notion page scraper with auto-cleanup.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python pull.py https://user.notion.site/MyPage-abc123 ./backups
              python pull.py -d -t 30 https://user.notion.site/MyPage-abc123 .
              python pull.py -i
        """),
    )

    parser.add_argument("url", nargs="?", help="Notion page URL to snapshot")
    parser.add_argument("dest", nargs="?", help="Destination folder for the snapshot output")

    g = parser.add_argument_group("scraping options")
    g.add_argument("-d", "--dark-mode", action="store_true", help="Scrape in dark mode")
    g.add_argument("-t", "--timeout", type=int, default=60, metavar="SEC",
                   help="Page load timeout in seconds (default: 60)")
    g.add_argument("-b", "--show-browser", action="store_true",
                   help="Show browser window (not headless)")
    g.add_argument("-c", "--disable-caching", action="store_true",
                   help="Disable asset caching")

    g2 = parser.add_argument_group("docker options")
    g2.add_argument("--rebuild", action="store_true", help="Force rebuild the Docker image")
    g2.add_argument("--no-cleanup", action="store_true",
                    help="Keep container and temp files after run for inspection")
    g2.add_argument("--remove-image", action="store_true",
                    help="Also remove the Docker image on cleanup")

    g3 = parser.add_argument_group("mode")
    g3.add_argument("-i", "--interactive", action="store_true",
                    help="Interactive mode with prompts")

    args = parser.parse_args(argv)

    if args.interactive:
        return args

    if not args.url or not args.dest:
        parser.error("URL and destination are required in CLI mode. Use -i for interactive mode.")

    if not args.url.startswith("https://") or "notion" not in args.url:
        parser.error("URL must be a valid Notion page (https://*.notion.site/...)")

    args.dest = Path(args.dest).expanduser().resolve()
    return args


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    if args.interactive:
        try:
            interactive_mode()
        except KeyboardInterrupt:
            echo("\nInterrupted.", style="yellow")
            full_cleanup(keep_image=not args.remove_image)
            sys.exit(130)
        return

    try:
        _execute(
            url=args.url, dest=args.dest,
            dark_mode=args.dark_mode, timeout_sec=args.timeout,
            show_browser=args.show_browser, disable_caching=args.disable_caching,
            rebuild=args.rebuild, no_cleanup=args.no_cleanup,
        )
    except KeyboardInterrupt:
        echo("\nInterrupted. Cleaning up...", style="bold yellow")
        full_cleanup(keep_image=not args.remove_image)
        sys.exit(130)
    except Exception as e:
        echo(f"Error: {e}", style="bold red")
        full_cleanup(keep_image=not args.remove_image)
        sys.exit(1)

    if args.remove_image:
        cleanup_image()


if __name__ == "__main__":
    main()
