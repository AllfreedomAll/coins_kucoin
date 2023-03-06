import queue as Queue


class EntryQueue(Queue.Queue):

    def __init__(self):
        Queue.Queue.__init__(self)

    def write(self, content):
        self.put(content)

login_queue = EntryQueue()

domain_queue = EntryQueue()