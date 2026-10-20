#!/usr/bin/env python3
"""
Pocket Universal Setup Wizard
--------------------------------
An interactive, OS-agnostic setup script for Pocket—a lightweight,
self-hosted personal cloud storage application with Tailscale Identity,
client-side file previews, and sqlite-vec semantic search.

Automates:
  1. Interactive configuration with intelligent defaults & Tailscale auto-detection.
  2. Storage directory provisioning and .env file generation.
  3. Docker Compose container build & startup.
  4. Tailscale Serve proxy registration for encrypted network-layer identity authentication.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


BANNER = r"""
╔══════════════════════════════════════════════════════════════════════╗
║                             Pocket                                   ║
║        Lightweight, Self-Hosted Personal Cloud Storage               ║
║      Tailscale Identity • sqlite-vec Search • Client Previews        ║
╚══════════════════════════════════════════════════════════════════════╝
"""


def print_step(step_num: int, title: str):
    print(f"\n\033[1;34m[Step {step_num}]\033[0m \033[1m{title}\033[0m")
    print("─" * 60)


def prompt_input(prompt: str, default: str) -> str:
    """Prompt user with a default value."""
    try:
        user_val = input(f"{prompt} [\033[36m{default}\033[0m]: ").strip()
        return user_val if user_val else default
    except (KeyboardInterrupt, EOFError):
        print("\n\nSetup aborted by user.")
        sys.exit(1)


def prompt_yes_no(prompt: str, default_yes: bool = True) -> bool:
    """Prompt user for a yes/no confirmation."""
    choices = "Y/n" if default_yes else "y/N"
    try:
        user_val = input(f"{prompt} [{choices}]: ").strip().lower()
        if not user_val:
            return default_yes
        return user_val in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print("\n\nSetup aborted by user.")
        sys.exit(1)


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Execute a shell command with real-time output or silent check."""
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def detect_tailscale_fqdn() -> str | None:
    """Attempt to detect Tailscale MagicDNS FQDN from the local tailscale daemon."""
    tailscale_bin = shutil.which("tailscale")
    if not tailscale_bin:
        return None

    try:
        res = subprocess.run(
            [tailscale_bin, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            self_node = data.get("Self", {})
            dns_name = self_node.get("DNSName")
            if dns_name:
                return dns_name.rstrip(".")
    except Exception:
        pass

    try:
        res = subprocess.run(
            [tailscale_bin, "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                parts = line.split()
                for part in parts:
                    if ".ts.net" in part:
                        return part.rstrip(".")
    except Exception:
        pass

    return None


def check_prerequisites():
    """Verify presence of Docker and Docker Compose."""
    print("Checking system dependencies...")
    docker_bin = shutil.which("docker")
    if not docker_bin:
        print("\033[1;31m[Error]\033[0m Docker is not installed or not in PATH.")
        print("Please install Docker first: https://docs.docker.com/get-docker/")
        sys.exit(1)

    # Check Docker daemon availability
    try:
        subprocess.run([docker_bin, "info"], capture_output=True, check=True)
        print("  \033[32m✔\033[0m Docker daemon is running.")
    except Exception:
        print("\033[1;33m[Warning]\033[0m Docker daemon does not appear to be running.")
        print("Please ensure Docker is started before container deployment.")

    # Check Docker Compose
    compose_available = False
    try:
        res = subprocess.run([docker_bin, "compose", "version"], capture_output=True)
        if res.returncode == 0:
            compose_available = True
            print("  \033[32m✔\033[0m Docker Compose v2 is available.")
    except Exception:
        pass

    if not compose_available and shutil.which("docker-compose"):
        compose_available = True
        print("  \033[32m✔\033[0m Legacy docker-compose is available.")

    if not compose_available:
        print("\033[1;31m[Error]\033[0m Docker Compose is not installed.")
        sys.exit(1)

    # Check Tailscale
    tailscale_bin = shutil.which("tailscale")
    if tailscale_bin:
        print("  \033[32m✔\033[0m Tailscale CLI is detected.")
    else:
        print("  \033[1;33m!\033[0m Tailscale CLI not found in PATH (optional for local dev).")


def main():
    parser = argparse.ArgumentParser(description="Pocket Interactive Setup Wizard")
    parser.add_argument("--non-interactive", "--defaults", action="store_true", help="Run with defaults without prompting")
    args = parser.parse_args()

    print(BANNER)
    print(f"Platform: {platform.system()} ({platform.machine()}) | Python: {platform.python_version()}")

    check_prerequisites()

    # Step 1: Configuration Options
    print_step(1, "Configure Storage & Network Parameters")

    # Storage Path Default
    nas_dir = Path("/mnt/nas-storage")
    default_storage = str(nas_dir) if nas_dir.exists() else "./data/storage"

    # Auto-detect Tailscale FQDN
    detected_fqdn = detect_tailscale_fqdn()
    default_base_url = f"https://{detected_fqdn}" if detected_fqdn else "http://localhost:8000"

    if args.non_interactive:
        storage_path = default_storage
        api_port = "8000"
        web_port = "80"
        share_port = "8080"
        public_base_url = default_base_url
        enable_tailscale = bool(detected_fqdn)
        print(f"Non-interactive mode selected.")
        print(f"  Storage: {storage_path}")
        print(f"  API Port: {api_port}")
        print(f"  Web Port: {web_port}")
        print(f"  Public Base URL: {public_base_url}")
    else:
        print("\nPlease specify your deployment preferences:")
        storage_path = prompt_input("1. Physical Storage Path (SSD/HDD or local folder)", default_storage)
        api_port = prompt_input("2. API Port (bound to 127.0.0.1)", "8000")
        web_port = prompt_input("3. Web Port (bound to 127.0.0.1)", "80")
        share_port = prompt_input("4. Public Funnel Share Port (bound to 127.0.0.1)", "8080")
        public_base_url = prompt_input("5. Public Base URL (for generated share links)", default_base_url)

    # Step 2: Environment Generation & Storage Provisioning
    print_step(2, "Storage Provisioning & .env Generation")

    storage_dir = Path(storage_path).resolve()
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        # Test write permissions
        test_file = storage_dir / ".pocket_write_test"
        test_file.touch()
        test_file.unlink()
        print(f"  \033[32m✔\033[0m Storage directory verified: {storage_dir}")
    except (PermissionError, OSError) as exc:
        print(f"\033[1;31m[Error]\033[0m Cannot write to {storage_dir}: {exc}")
        print("Your user doesn't have write access to this mount point yet.")
        print("\nIf this is an \033[1mext4 / internal drive\033[0m, run:")
        print(f"  \033[1;32msudo chown -R $USER:$USER {storage_dir}\033[0m")
        print(f"  \033[1;32msudo chmod -R 775 {storage_dir}\033[0m")
        print("\nIf this is an \033[1mexFAT / FAT32 / NTFS USB drive\033[0m, permissions must be set at mount:")
        print(f"  \033[1;32msudo umount {storage_dir}\033[0m")
        print(f"  \033[1;32msudo mount -o uid=1000,gid=1000,umask=0000 /dev/sda1 {storage_dir}\033[0m")
        print("Or add to /etc/fstab: \033[33mUUID=<uuid> /mnt/pocket-storage exfat defaults,uid=1000,gid=1000,umask=0000,nofail 0 0\033[0m\n")
        print("Then run `python3 setup.py` again.")
        sys.exit(1)

    # Format paths for .env
    # Convert backslashes for Windows Docker compatibility
    clean_storage_dir = str(storage_dir).replace("\\", "/")
    database_url = f"sqlite:///{clean_storage_dir}/database.db"

    env_content = f"""# Pocket Environment Configuration
# Automatically generated by setup.py

# Physical storage directory on host & container
STORAGE_DIR={clean_storage_dir}

# SQLite database path (embedded with sqlite-vec)
DATABASE_URL={database_url}

# Public URL used for generating external share links
PUBLIC_BASE_URL={public_base_url.rstrip('/')}

# Port configurations (bound strictly to 127.0.0.1 loopback)
API_PORT={api_port}
WEB_PORT={web_port}
SHARE_PORT={share_port}

# Tailscale Identity authentication settings
# DEV_MODE=true allows local access on http://127.0.0.1 while still respecting Tailscale headers when accessed via Tailnet
DEV_MODE=true
DEV_USER_LOGIN=admin@pocket.local
DEV_USER_NAME=Pocket Admin
"""

    root_dir = Path(__file__).resolve().parent
    env_file = root_dir / ".env"
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_content)
    print(f"  \033[32m✔\033[0m Successfully generated configuration at: {env_file}")

    # Step 3: Container Orchestration (Docker Compose)
    print_step(3, "Docker Compose Container Orchestration")

    start_containers = True if args.non_interactive else prompt_yes_no("Build and start Pocket Docker containers now?", True)

    if start_containers:
        print("\nStarting container build sequence (this may take a few minutes)...")
        docker_bin = shutil.which("docker") or "docker"
        compose_cmd = [docker_bin, "compose", "up", "--build", "-d"]

        try:
            res = subprocess.run(compose_cmd, cwd=root_dir)
            if res.returncode != 0:
                # Fallback to legacy docker-compose
                print("Falling back to legacy docker-compose...")
                res = subprocess.run(["docker-compose", "up", "--build", "-d"], cwd=root_dir)

            if res.returncode == 0:
                print("  \033[32m✔\033[0m Pocket containers successfully built and launched!")
            else:
                print(f"\033[1;33m[Warning]\033[0m Container launch exited with code {res.returncode}. You can manually retry with: docker compose up -d")
        except Exception as exc:
            print(f"\033[1;31m[Error]\033[0m Docker compose execution failed: {exc}")
    else:
        print("  Skipped container build. You can start Pocket later using: docker compose up --build -d")

    # Step 4: Tailscale Network Mapping
    print_step(4, "Tailscale Serve Proxy Registration")

    tailscale_bin = shutil.which("tailscale")
    if tailscale_bin:
        configure_ts = True if args.non_interactive else prompt_yes_no(
            f"Automatically register Pocket on Tailnet via 'tailscale serve --bg {web_port}'?",
            True
        )

        if configure_ts:
            print(f"Registering Tailscale Serve proxy on port {web_port}...")
            try:
                res = subprocess.run(
                    [tailscale_bin, "serve", "--bg", web_port],
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    print(f"  \033[32m✔\033[0m Tailscale Serve registered successfully on port {web_port}!")
                    print(f"  Tailscale Identity headers will now be securely injected into Pocket.")
                else:
                    print(f"\033[1;33m[Notice]\033[0m Tailscale serve command returned: {res.stderr.strip() or res.stdout.strip()}")
                    print(f"You can manually run: tailscale serve --bg {web_port}")
            except Exception as exc:
                print(f"Could not execute tailscale serve: {exc}")
    else:
        print("Tailscale CLI not found. To enable identity authentication when Tailscale is installed, run:")
        print(f"  tailscale serve --bg {web_port}")

    # Summary & Instructions
    print_step(5, "Setup Complete!")
    print("\n\033[1;32mPocket is ready!\033[0m")
    print("─" * 60)
    print("Architecture Summary:")
    print(f"  • Storage Directory:      {clean_storage_dir}")
    print(f"  • Relational DB & Vector: SQLite + sqlite-vec ({clean_storage_dir}/database.db)")
    print(f"  • API Port (Loopback):127.0.0.1:{api_port}")
    print(f"  • Web Port (Loopback):127.0.0.1:{web_port}")
    print(f"  • Identity Authentication:Tailscale Network-Layer Identity (JIT provisioning)")
    print(f"  • Client-Side Previews:   Markdown, CSV, PDF, Video, Audio, Images (Zero server conversion)")
    print(f"  • Semantic Search:        Local vector search strictly filtered by ownership & shares")
    print("─" * 60)
    print("\nNext Steps & Useful Commands:")
    print("  1. Access your Pocket Web Drive:")
    if detected_fqdn:
        print(f"     https://{detected_fqdn}")
    else:
        print(f"     http://localhost:{web_port}")
    print("\n  2. Expose public file sharing via Tailscale Funnel (Optional):")
    print(f"     tailscale funnel {share_port}")
    print("\n  3. Monitor container logs:")
    print("     docker compose logs -f\n")


if __name__ == "__main__":
    main()
