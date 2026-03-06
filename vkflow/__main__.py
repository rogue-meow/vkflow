import argparse
import importlib.metadata
import platform

import aiohttp

import vkflow


def show_version() -> None:
    meta_version = vkflow.__meta__.__version__

    try:
        pkg_version = importlib.metadata.version("vkflow")
    except importlib.metadata.PackageNotFoundError:
        pkg_version = "not installed"

    uname = platform.uname()

    lines = [
        f"- Python v{platform.python_version()}-{platform.python_revision() or 'final'}",
        f"- vkflow v{meta_version}",
        f"    - vkflow importlib.metadata: v{pkg_version}",
        f"    - VK API version: {vkflow.__meta__.__vk_api_version__}",
        f"- aiohttp v{aiohttp.__version__}",
        f"- System info: {uname.system} {uname.release} {uname.version} {uname.machine}",
    ]

    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(prog="vkflow")
    parser.add_argument("-v", "--version", action="store_true", help="show version info")
    args = parser.parse_args()

    if args.version:
        show_version()
    else:
        parser.print_help()


main()
