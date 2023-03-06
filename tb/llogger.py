# logger对象配置
# import logging
# okx_logger = logging.getLogger("okx")
# fh = logging.FileHandler('ku_coin.log',encoding='utf-8')
# formatter = logging.Formatter('%(asctime)s / %(name)s / %(levelname)s / %(message)s')
# fh.setLevel(logging.INFO)
# fh.setFormatter(formatter)
# okx_logger.addHandler(fh)

import logging
from logging import handlers
import os
import time

try:
    if os.path.exists("./ku_coin.log"):
        if os.path.getsize("./ku_coin.log") > 30 * 1024 * 1024:
            int(time.time())
            os.rename("./ku_coin.log", f"./ku_coin_{int(time.time())}.log")

except:
    pass


class PyLogger(object):
    level_relations = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'crit': logging.CRITICAL
    }

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    def __init__(self, filename, level='info', when='D', backCount=3,
                 fmt='%(asctime)s / %(name)s / %(levelname)s / %(message)s'):
        self.logger = logging.getLogger(filename)
        format_str = logging.Formatter(fmt)  # S et log format
        self.logger.setLevel(self.level_relations.get(level))  # Set log level
        if not self.logger.handlers:
            # sh = logging.StreamHandler()  # Output to the screen
            # sh.setFormatter(format_str)  # Set the format displayed on the screen

            # Write to file #The processor that automatically generates the file at the specified interval
            th = handlers.TimedRotatingFileHandler(filename=filename, when=when, backupCount=backCount,
                                                   encoding='utf-8')
            th.setFormatter(format_str)  # Set the format written in the file
            # self.logger.addHandler(sh)  # Add object to logger
            self.logger.addHandler(th)


log = PyLogger('ku_coin.log', level='debug')
