
import datetime
import logging
import pathlib
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def logger(level: int) -> None:
    logginglevel: int = level
    path: Path = pathlib.Path(__file__).parent.joinpath('logs')

    dircheck: bool = pathlib.Path.exists(self=path)
    if dircheck is not True:
        print('Making Log Directory...')
        pathlib.Path.mkdir(self=path)

    logging.basicConfig(level=logginglevel, format='%(asctime)s [%(threadName)s] [%(levelname)s]  %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p',
                        handlers=[logging.StreamHandler(stream=sys.stdout),
                                  TimedRotatingFileHandler(filename=pathlib.Path.as_posix(self=path) + '/log', when='midnight', atTime=datetime.datetime.min.time(), backupCount=4, encoding='utf-8', utc=True)])
