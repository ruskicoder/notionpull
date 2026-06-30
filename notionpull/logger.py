import logging
import inspect

import traceback
import functools
from rich.logging import RichHandler
import os
from bs4 import BeautifulSoup
import cssutils

from argparser import ARGS


BANNER_ASCII = """
                __  _                         ____
   ____  ____  / /_(_)___  ____  ____  __  __/ / /
  / __ \/ __ \/ __/ / __ \/ __ \/ __ \/ / / / / /
 / / / / /_/ / /_/ / /_/ / / / / /_/ / /_/ / / /
/_/ /_/\____/\__/_/\____/_/ /_/ .___/\__,_/_/_/
                             /_/
"""
HIGHLIGHTED_WORDS = ["pages left to scrape:"]
IGNORED_STACK_FRAMES = 8


class LogWrapper(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        tab_char = " " * 3
        indentation_level = len(traceback.extract_stack()) - IGNORED_STACK_FRAMES
        return f"{tab_char * indentation_level}{msg}", kwargs


class LogInitializer:
    @staticmethod
    def get_log() -> logging.LoggerAdapter:
        rich_handler = RichHandler(rich_tracebacks=True, show_time=False, show_path=False, keywords=HIGHLIGHTED_WORDS)
        logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[rich_handler])
        cssutils.log.setLevel(logging.CRITICAL)  # type: ignore

        os.system("cls" if os.name == "nt" else "clear")
        print(BANNER_ASCII)
        return LogWrapper(logging.getLogger("scrape-logger"), {})


LOG_SINGLETON = LogInitializer.get_log()


def trace(print_args: bool = True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            input_string = "⮕ "
            input_string += func.__name__ + "("
            if print_args:
                not_html = [arg for arg in args if not isinstance(arg, BeautifulSoup)]
                input_string += ", ".join([str(arg) for arg in not_html])
            input_string += ")"
            LOG_SINGLETON.info(input_string)

            result = func(*args, **kwargs)

            output_string = result if result is not None else ""
            LOG_SINGLETON.info(f"⬅ {output_string if print_args else ''}")
            return result

        return wrapper

    return decorator
