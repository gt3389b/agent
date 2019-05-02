import logging

class Log(object):
    def __init__(self):
        logging.basicConfig(level=logging.DEBUG)
        self._log = logging.getLogger("usp-logger")

    def send(self, m):
        self._log.info("SEND "+str(m))
        return True
