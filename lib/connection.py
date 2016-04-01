'''
Created on 24.2.2009

@author: Jaakko Lintula <jaakko.lintula@iki.fi>
'''

from threading import Thread
from select import select
import random, time, socket

class Connection(Thread):
    def __init__(self, server, port, message_callback=None,
                 status_callback=None):
        Thread.__init__(self)
        self.port = port
        self.server = server
        self.socket = None
        self.running = False
        self.message_callback = message_callback
        self.status_callback = status_callback
        self.out_queue = []
        self._since = time.time()
        self.__old_data = ""

    def __str__(self):
        return "%s!%s at %s:%s" % \
                (self.nickname, self.username, self.server, self.port)

    def run(self):
        self.connect()

    def send(self, line):
        """adds lines to the send queue"""

        if len(line) > 510:
            line = line[:510]
        if not line.endswith('\r\n'):
            line += '\r\n'

        if not self.out_queue:
            if self._since < time.time():
                self._since = time.time()

        if line.startswith('PONG') or line.startswith('PING') or line.startswith('QUIT'):
            # PING replies get to the front
            self.out_queue.insert(0, line)
        else:
            self.out_queue.append(line)

    def close(self):
        self.running = False
        self.status_callback(100, "disconnected")
        self.socket.close()

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.connect((self.server, self.port))
        except (IOError, socket.gaierror), (errno, msg):
            self.status_callback(103, msg)
        else:
            #self.socket.setblocking(False)
            self.status_callback(1, "connection open")
            self.running = True
            self.read_loop()


    def read_and_send(self, timeout):
        s = select([self.socket], [], [], timeout)[0]
        if s:
            s = s[0]
            try:
                new_data = s.recv(2048).replace('\r', '') # we care only about
                                                    # the \n, strip \r if any
                if not new_data:
                    self.status_callback(101, "Connection reset by peer")
                    self.running = False
                    self.socket.close()

                if not new_data.endswith('\n'): # last message wasn't complete
                    t = new_data.split('\n')
                    new_lines = t[:-1]
                    #print "incomplete: %s " %( t[-1])
                    if new_lines:
                        if self.__old_data: # append  the old incomplete message to first in new data
                            new_lines[0] = self.__old_data + new_lines[0]
                            self.__old_data = t[-1] # the last line in new data must be saved
                        else:
                            self.__old_data = t[-1]
                    else:
                        self.__old_data += t[0] # still received nothing complete; append to the old old_data
                else: # received completed messages
                    new_lines = new_data.split('\n')[:-1] # last one is always empty after .split()
                    new_lines[0] = self.__old_data + new_lines[0]
                    self.__old_data = ""

                for line in new_lines:
                    #print "outgoing:", line
                    self.message_callback(line)

            except socket.error, errno:
                # error with transmission for some reason

                self.status_callback(101, "Connection failure, errno %s" % errno)
                self.running = False
                self.socket.close()

        if self.out_queue:
            # try to send anything that's in out_queue unless magic
            # flood prevention numbers tell not to (TODO make this better)
            try:
                if (self._since < time.time() + 8):
                    line = self.out_queue.pop(0)
                    self.socket.sendall(line)
                    self._since += 2.1 + len(line) / 120
                #else:
                    #print 'flood prevention triggered', self._since-time.time(), len(self.out_queue)


            except socket.error, errno:
                if not errno[0] == 11:
                    self.status_callback(101, "Connection failure when sending")
                    self.running = False
                    self.socket.close()


    def read_loop(self):
        while self.running:
            self.read_and_send(0.2)
