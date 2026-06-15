#!/usr/bin/env python3
import time
from datetime import datetime

from common.global_variable import GlobalVariable
from flights.vietjet.script.web_script import WebScript


def main() -> None:
    while True:
        try:
            script = WebScript(GlobalVariable.PROXY_INFO_DATA)
            script.z()
        except Exception as exc:
            print(f"{datetime.now():%Y-%m-%d %H:%M:%S} VJ device id cache update failed: {exc}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
