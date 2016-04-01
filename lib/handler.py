# -*- coding: utf-8 -*-
'''
Created on 24.2.2009

@author: Jaakko Lintula <jaakko.lintula@iki.fi>
'''

import connection, events
import time, logging
Event = events.Event

LOG_FILENAME = "pyircfs.log"
#logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG, format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
#                    datefmt='%m-%d %H:%M:%S',)


CHANCHARS = '*#+!&'


def is_channel(target):
    return target[0] in CHANCHARS


class ConnectionError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


class Handler:

    def _find_handler_classes(self, key):
        """searches for a given key in classes in the events.py module
        @return a list of (command, handler class) tuples"""

        # there has to be a better way :O
        classes = []  # list of (command, handler class) tuples
        for i in events.__dict__.keys():
            if hasattr(events.__dict__[i], key):
                for j in getattr(events.__dict__[i], key):
                    classes.append((j, events.__dict__[i]))
        return classes

    def _get_handlers(self, htype, command):
        """returns a list of eventstore objects for given message, instantiates
        ones from the handler class if needed and adds all other commands the same
        class is able to receive to the object list

        @param htype either 'reply' or 'command'
        @param command the command/reply the store should be interested in
        @return list of objects to send an event to"""

        if htype == 'reply':
            hlist = self.reply_handler_classes
            slist = self.reply_stores
        elif htype == 'command':
            hlist = self.command_handler_classes
            slist = self.command_stores
        else:
            return []

        classes = []
        objects = []

        wildcard_added = False
        # search if there are suitable objects already somewhere and use them if possible:
        for i in slist:
            if i[0] == command:
                objects.append(i[1])
            if i[0] == '*':
                objects.append(i[1])
                wildcard_added = True

        if (len(objects) > 1 and wildcard_added) or (objects and not wildcard_added):
            return objects

        for i in hlist: # ok then, search for classes
            if i[0] == command: # search for corresponding store objects
                if not issubclass(i[1], events.PrivmsgStore):
                    # Privmsg/channel stores are created only on
                    # PRIVMSG/NOTICE, not in _handle_server_message
                    classes.append(i[1])

        # now, classes contains only those classes that don't have instantiated objects
        for i in classes:
            # print "we are here with ", i
            obj = self._create_new_store(i) # create a new store instance from the class

            # find out what other commands and replies the same class
            # supports and add them too:
            for j in self.reply_handler_classes:
                if j[1] == i:
                    self.reply_stores.append((j[0], obj))

            for j in self.command_handler_classes:
                if j[1] == i:
                    self.command_stores.append((j[0], obj))

            #slist.append((command, obj))
            objects.append(obj)
        return objects

    def _get_free_id(self):
        """returns a free unique id"""
        self._next_id += 1
        return self._next_id

    def _create_new_store(self, class_, *args, **kwargs):
        """creates a new eventstore object and assigns it an unique id.

           @param class_ the class to create an instance from
           @param *args, **kwargs are passed to the class
           @return the created object"""

        id = self._get_free_id()
        obj = class_(id=id, handler=self, *args, **kwargs)
        self.all_stores[id] = obj
        [x(obj) for x in self.new_store_callbacks]
        return obj

    def __init__(self):
        self.command_handler_classes = self._find_handler_classes('command_handlers')
        self.reply_handler_classes = self._find_handler_classes('reply_handlers')
        self.command_stores = []
        self.reply_stores = []
        self.privmsg_stores = []
        self.all_stores = {}
        self.joined_when_disconnected = []
        self.new_store_callbacks = []

        self._next_id = 0

        self.connection = None
        self.connection_status = (0, '')
        self.connection_status_timestamp = 0
        self.nicknames = []
        self.username = ""
        self.nickname = ""

    def connect(self, server, nicknames, username, realname, port=6667, password=""):
        """Tries to connect to the IRC server."""

        #self.nickname = nickname
        self.nicknames = nicknames
        self.username = username
        self.realname = realname
        self.server = server
        self.port = port

        #self.connection = connection.connect(self, server, port)
        self.connection = connection.Connection(server, port,
                                                self.receive_message,
                                                self.receive_status)
        self.connection.start()
        while not self.connection_status[0] == 1:
            time.sleep(0.2)
            if self.connection_status[0] == 103:
                raise ConnectionError(self.connection_status[1])

        if password:
            self.send_command('PASS', password)
        self.send_command('NICK', nicknames[0])
        self.send_command('USER', '%s 0 * :%s' % (username, realname))

    def __str__(self):
        ret = "i'm a handler"
        if self.connection:
            ret += ", connected as %s" % self.connection
        return ret

    def remove_store(self, id):
        """removes all references to a store"""
        try:
            store = self.all_stores[id]
        except KeyError:
            raise ValueError("unknown store")

        self.all_stores.pop(id)

        while store in self.privmsg_stores:
            self.privmsg_stores.remove(store)

        for storelist in [self.reply_stores, self.command_stores]:
            to_remove = []
            for i in storelist:
                if i[1] == store:
                    to_remove.append(i)
            for i in to_remove:
                storelist.remove(i)

        # and finally tell the store about it
        store.remove()

    def get_store_id(self, store):
        for id in self.all_stores:
            if self.all_stores[id] == store:
                return id
        return None

    def close(self):
        self.connection.close()

    def receive_message(self, message):
        """handles messages coming from the connection and hands them to
           _handle_privmsg or _handle_server_message depending on message type"""
        logging.debug("receive_message: received %s" % message)
        tmp = message.split(' ')
        # parses the received message to prefix/cmd/params:
        if message[0] == ":":
            prefix = tmp[0]
            cmd = tmp[1]
            params = ' '.join(tmp[2:])
        else:
            prefix = ""
            cmd = tmp[0]
            params = ' '.join(tmp[1:])
        ev = Event(prefix=prefix, command=cmd, params=params)

        #print "RECV: prefix %s cmd %s params %s " % (prefix, cmd, params)

        if cmd == 'JOIN':
            # JOINs are a special case
            # - we need to create a privmsg store for them if one doesn't
            #   exist
            self._get_privmsg_handlers(params[1:])
            # now a store is created for the channel if one didn't exist
            # already - we don't need the actual instance anywhere in here,
            # but now _handle_server_message has somewhere to send the JOIN too

        if cmd in ["PRIVMSG", "NOTICE"]:
            self._handle_privmsg(ev)
        else:
            self._handle_server_message(ev)

    def _handle_privmsg(self, event):
        logging.debug("_handle_privmsg: event %s" % event)
        #if event.params[0] in '*#+!&':
        if is_channel(event.params[0]):
            target = event.params.split()[0]
        else:
            try:
                target = event.prefix[1:event.prefix.index('!')]
            except ValueError:  # no nickname could be found
                logging.debug("hmm? couldn't extract nickname from event")
                return

        stores = self._get_privmsg_handlers(target)
        [store.add_event(event) for store in stores]

    def _get_privmsg_handlers(self, target):
        logging.debug("ENTER _get_privmsg_handlers, target: %s" % target)
        s = [x for x in self.privmsg_stores if x.target.lower() == target.lower()]
        if not s:
            logging.debug("_get_privmsg_handlers: no existing store found")
            if is_channel(target[0]):
                s.append(self._create_new_store(events.ChannelStore, target=target, name="_"+target))
                replies = events.ChannelStore.reply_handlers
            else:
                s.append(self._create_new_store(events.PrivmsgStore, target=target, name="_"+target))
                replies = events.PrivmsgStore.reply_handlers
            self.privmsg_stores.append(s[-1])
            for r in replies:
                self.reply_stores.append((r, s[-1])) # TODO ADD ID
        for i in self.reply_stores:
            if i[0] == '*':
                s.append(i[1])
        logging.debug("_get_privmsg_handlers: returning stores: %s" % [str(x) for x in s])
        return s

    def _handle_server_message(self, event):
        handlers = self._get_handlers('reply', event.command)
        for h in handlers:
            answer = h.add_event(event)
            if answer:
                [self.connection.send(msg) for msg in answer]


    def send_command(self, command, params):
        if self.connection_status[0] not in (1, 10) or  \
          (self.connection_status[0] == 1 and \
          command not in ['PASS', 'USER', 'NICK']):
            raise ConnectionError("not connected")
        command = command.upper()
        handlers = self._get_handlers('command', command)
        if not handlers:
            raise ValueError("unknown command")
        for h in handlers:
            to_send = h.generate_event(command, params)
            if to_send:
                for msg in to_send:
                    self.connection.send(msg)

    def send_message(self, target, message, type="PRIVMSG"):
        logging.debug("ENTER send_message: target %s message %s type %s" % (target, message, type))
        #if message.startswith('wait'):
        #    time.sleep(10)
        if not self.connection_status[0] == 10:
            raise ConnectionError("not connected")
        store = self._get_privmsg_handlers(target)[0]
        logging.debug("send_message: store resolved as %s" % store)
        to_send = store.generate_event(type, message)
        logging.debug("send_message: to_send: %s" % to_send)
        if to_send:
            for msg in to_send:
                self.connection.send(msg)

    def send_notice(self, target, message):
        self.send_message(target, message, type="NOTICE")

    def create_privmsg_store(self, target):
        self._get_privmsg_handlers(target)

    def create_command_store(self, target):
        if not self._get_handlers('command', target.upper()):
            raise ValueError('unknown command')

    def receive_status(self, statusno, statusdesc):
        """receives a tuple of status messages (number, description) from the connection object
           and (maybe) acts accordingly

            0: not connected
            1: connecting (socket opened)
            10: connection open and free to use

            100: disconnected by user request
            101: disconnected by server
            102: disconnected for some other reason (?)
            103: network error when connecting
            104: all nicknames in use
            105: bad server password

            messages can be sent only when status == 10
            (USER, PASS and NICK may be sent when status == 1)
        """

        #print "sain jotain statusta: %s %s" % (statusno, statusdesc)
        self.connection_status_timestamp = time.time()
        self.connection_status = (statusno, statusdesc)

        # when disconnected, save names of channels that were joined at the
        # time, and send an informational event to them
        if self.connection_status[0] in (100, 101, 102):
            for i in self.privmsg_stores:
                if isinstance(i, events.ChannelStore):
                    if i.joined:
                        self.joined_when_disconnected.append(i.target)
                        i.joined = False

            disconnect_event = Event(prefix="", command="", params=statusdesc,
                                     generated=True, informational=True)
            for i in self.all_stores:
                self.all_stores[i].add_event(disconnect_event)

    def reconnect(self):
        """if disconnected, reconnects to a server an rejoins channels
           """
        if self.connection_status[0] == 10:
            raise ValueError("already connected!")
        self.connect(self.server, self.nicknames, self.username, self.realname, self.port)
        for channel in self.joined_when_disconnected:
            self.send_command('JOIN', channel)
        self.joined_when_disconnected = []

    def list_reply_stores(self):
        """returns list of unique reply stores"""
        names = []
        stores = []
        for i in self.reply_stores:
            if not i[1] in stores:
                names.append(i[1].name)
                stores.append(i[1])
        return dict(zip(names, stores)) # I suppose names are unique

    def list_command_stores(self):
        """returns list of unique command stores"""
        names = []
        stores = []
        for i in self.command_stores:
            if not i[1] in stores and not (hasattr(i[1], 'internal') and i[1].internal):
                # do not list stores that are there already, and don't list those
                # that are "internal" either (particularly PingES)
                names.append(i[0])
                stores.append(i[1])
        return dict(zip([x.lower() for x in names], stores))

    def list_privmsg_stores(self, filter=None):
        """returns list of unique privmsg stores
            @param filter return only privmsg or channels if 'privmsg' or 'channel'"""
        d = {}
        for i in self.privmsg_stores:
            if filter == 'privmsg':
                if isinstance(i, events.PrivmsgStore):
                    d[i.target] = i
            elif filter == 'channel':
                if isinstance(i, events.ChannelStore):
                    d[i.target] = i
            else:
                d[i.target] = i
        return d


    def list_info_stores(self):
        """returns list of reply stores that don't take any commands,
           aka "informational" stores (errors, etc?)"""
        names = []
        stores = []
        for i in self.reply_stores:
            found = False
            for j in self.command_stores:
                if j[1] == i[1]:
                    found = True
            for j in self.privmsg_stores:
                if j == i[1]:
                     found = True
            if not found:
                names.append(i[1].name)
                stores.append(i[1])
        return dict(zip(names, stores))
