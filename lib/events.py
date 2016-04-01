# -*- coding: utf-8 -*-
'''
Created on 25.2.2009

@author: Jaakko Lintula <jaakko.lintula@iki.fi>

Contains combined handlers and "event stores" for incoming and outgoing IRC
messages.

Stores both keep and store everything sent and received by them, as well as
act on IRC commands / server responses they know of.
'''

import time

# helper functions

def timeformat(mtime):
    return time.strftime("[%H:%M:%S]", time.localtime(mtime))

def prefix2nick(prefix):
    try:
        return prefix[1:prefix.index('!')]
    except ValueError:  # no nick in prefix
        return ""

def prefix2hostmask(prefix):
    try:
        return prefix[prefix.index('!')+1:]
    except ValueError:
        return ""

def extract_modes(modestr):

    modestr = modestr.split()

    paramflags = {'+': 'abehIkLloqv', # MODE + flags that need a parameter
                  '-': 'abehIoqv',    # MODE - flags that need a parameter
                  '': ''}

    flags = modestr[1]
    params = modestr[2:]

    modes = []

    curr_flag = ''
    param_index = 0
    for i in flags:
        if i in '+-':
            curr_flag = i
        else:
            if i in paramflags[curr_flag]:
                try:
                    modes.append((curr_flag+i, params[param_index]))
                except IndexError: # couldn't make sense of the mode string,
                    break          # quit parsing
                param_index += 1
            else:
                modes.append((curr_flag+i,))

    return modes


def splitparams(param):
    p = param.split(' ')
    firstpart = p[0]
    if len(p) == 1:
        return firstpart, ""
    else:
        return firstpart, ' '.join(p[1:])



class Event:
    """Event contains all the information that a single message can
       contain.

       @param command the IRC command, e.g. in part message 'PART'
       @param params list of parameters, e.g. '#channel :I'm leaving'
       @param params_endpart if specified, will contain everything
              after the first colon (':') in params
              will be automatically created if not specified
       @param generated True if the event didn't come from a server
       @param informational True if the event doesn't represent any
              exchange between the client and server (e.g. for
              "disconnected!" messages from the Handler)
    """

    def __init__(self, prefix, command, params="", params_endpart="",
                 generated=False, informational=False):
        #         raw_format=""):
        self.timestamp = time.time()
        self.command = command
        self.params = params
        self.generated = generated
        self.informational = informational
        self.prefix=prefix
       # self.raw_format=""
        if params and not params_endpart:
            try:
                self.params_endpart = params[params.index(':')+1:]
            except ValueError:
                self.params_endpart = ""
        else:
            self.params = params
            self.params_endpart = params_endpart


    def __str__(self):
        """a crude way of transforming an Event to str if the EventStore doesn't implement anything else"""
        reply = timeformat(self.timestamp)
        if self.prefix:
            reply += " %s" % self.prefix
        reply += " %s %s" % (self.command, self.params)

        if self.generated:
            reply = " -> %s" % reply

        return reply

    def irc_format(self):
        """formats generated events as sendable (to IRC server) string
        @return the event as a string """

        if not self.generated:
            raise ValueError("this makes no sense")
        params = self.params.split(' ')
        #if self.params_endpart:
        #    return "%s %s :%s\r\n" % (self.command, self.params, self.params_endpart)
        return "%s %s\r\n" % (self.command, self.params)



class EventStore:
    def __init__(self, id, handler=None, name="", maxsize=0):
        """Initializes the EventStore object

           @param id an unique id number for the store
           @param handler a reference to the handler, if needed
           @name a name for the store, _should_ be unique
        """
        self.id = id
        self.handler = handler
        self.name = name
        self._eventlist = []

        self._maxsize = 0
        self._cached_contents = []
        self._lastlen = 0
        self._cached_size = 0

        self.update_callbacks = []
        self.remove_callbacks = []


    def _add(self, event):
        self._eventlist.append(event)
        [x(self) for x in self.update_callbacks]

    def get_ctime(self):
        if self._eventlist:
            return self._eventlist[0].timestamp
        else:
            return time.time()

    def get_size(self):
        if len(self._eventlist) == self._lastlen:
            return self._cached_size
        contents = [self.msg_formatter(event) for event in self._eventlist]
        self._cached_size = sum([len(x)+1 for x in contents])
        self._cached_contents = contents
        return self._cached_size


    def add_event(self, event):
        """
        Adds an event object to the store's event list

        @return None or a string to be sent back to the server (as a reply)
        """
        self._add(event)

    def generate_event(self, cmd, params):
        """Generic message sender, only works with simple commands"""
        e = Event(prefix="", command=cmd, params=params, generated=True)
        self._add(e)
        return [e.irc_format()]

    def msg_formatter(event):
        return str(event)
    msg_formatter = staticmethod(msg_formatter)

    def remove(self):
        """called when the store is removed"""
        [x(self) for x in self.remove_callbacks]

    def get_contents(self, offset=0):
        if len(self._eventlist) == self._lastlen:
            return self._cached_contents[offset:]
        contents = [self.msg_formatter(x) for x in self._eventlist]
        self._lastlen = len(self._eventlist)
        self._cached_contents = contents
        self._cached_size = sum([len(x)+1 for x in contents])
        return contents[offset:]

    def __str__(self):
        return "id: %s, name: %s, %d events" % (self.id, self.name, len(self._eventlist))

class PingES(EventStore):
    reply_handlers = ["PING"]
    command_handlers = ["PONG"]
    internal = True # not necessary to show this to end user

    def __init__(self, id, handler, name='ping'):
        EventStore.__init__(self, id, handler, name)

    def add_event(self, event):
        EventStore.add_event(self, event)
        if event.command == 'PING':
            #reply = Event(prefix="", command="PONG", params=event.params[1:], generated=True)
            #self._eventlist.append(reply)
            #return [reply.irc_format()]
            self.handler.send_command('PONG', event.params[1:])
    def generate_event(self, cmd, params):
        e = Event(prefix="", command=cmd, params=params, generated=True)
        self._eventlist.append(e)
        return [e.irc_format()]

class QuitES(EventStore):
    reply_handlers = ["QUIT"]
    command_handlers = ["QUIT"]

    def __init__(self, id, handler, name='quit'):
        EventStore.__init__(self, id, handler, name)
        self.name = name

    def generate_event(self, cmd, params):
        e = Event(prefix="", command=cmd, params=":%s" % params, generated=True)
        self._add(e)
        return [e.irc_format()]


class PartES(EventStore):
    reply_handlers = ["PART"]
    command_handlers = ["PART"]

    def __init__(self, id, handler, name='part'):
        EventStore.__init__(self, id, handler, name)

    def generate_event(self, cmd, params):
        first, last = splitparams(params)
        e = Event(prefix="", command=cmd, params="%s :%s" % (first, last), generated=True)
        self._add(e)
        return [e.irc_format()]

class JoinES(EventStore):
    reply_handlers = ["JOIN"]
    command_handlers = ["JOIN"]

    def __init__(self, id, handler, name='join'):
        EventStore.__init__(self, id, handler, name)


    def generate_event(self, cmd, params):
        params = params[:50] # TODO implement server CHANNELLEN support
        e = Event(prefix="", command=cmd, params=params, generated=True)
        self._eventlist.append(e)
        return [e.irc_format()]

class UserES(EventStore):
    reply_handlers = []
    command_handlers = ['USER']
    internal = True

    def __init__(self, id, handler, name='user'):
        EventStore.__init__(self, id, handler, name)

class PassES(EventStore):
    reply_handlers = []
    command_handlers = ['PASS']
    internal = True

    def __init__(self, id, handler, name='pass'):
        EventStore.__init__(self, id, handler, name)

class ModeES(EventStore):
    reply_handlers = ['MODE', '352']
    command_handlers = ['MODE']

    def __init__(self, id, handler, name='mode'):
        EventStore.__init__(self, id, handler, name)


class ErrorES(EventStore):
    # the RFC says messages from 400 to 599 are error messages
    # not everything is in use, but we just get all of them

    reply_handlers = ['ERROR'] + [str(x) for x in range(400, 600)]
    command_handlers = []

    def __init__(self, id, handler, name='errors'):
        EventStore.__init__(self, id, handler, name)

    def add_event(self, event):
        self._add(event)
        if event.command == 'ERROR' and ":Closing Link:" in event.params:
            if self.handler.connection_status[0] in (1, 10):
                self.handler.connection.close()


class WhoisES(EventStore):
    reply_handlers = ["311", # RPL_WHOISUSER
                      "312", # RPL_WHOISSERVER
                      "313", # RPL_WHOISOPERATOR
                      "317", # RPL_WHOISIDLE
                      "318", # RPL_ENDOFWHOIS
                      "319", # RPL_WHOISCHANNELS
                      "314", # RPL_WHOWASUSER
                      "369"] # RPL_ENDOFWHOWAS
                      #"461", # ERR_NOTENOUGH
    command_handlers = ["WHOIS", "WHOWAS"]

    def __init__(self, id, handler, name='whois'):
        EventStore.__init__(self, id, handler, name)

    def msg_formatter(event):
        p = event.params.split()
        ep = event.params_endpart
        ts = timeformat(event.timestamp)
        if event.command == "311":
            ret = "%s %s: (%s@%s): %s" % (ts, p[1], p[2], p[3], ep)
        elif event.command == "312":
            ret = "%s %s: %s (%s)" % (ts, p[1], p[2], ep)
        elif event.command == "319":
            ret = "%s %s: %s" % (ts, p[1], ep)
        elif event.command == "317":
            idle = p[2]
            signon = time.ctime(int(p[3]))
            ret = "%s %s: idle %s s, signon time %s" % (ts, p[1], idle, signon)
        elif event.command == "318":
            ret = "%s %s: %s" % (ts, p[1], ep)
        else:
            ret = str(event)
        return ret
    msg_formatter = staticmethod(msg_formatter)

class MotdES(EventStore):
    # RPL_MOTDSTART, RPL_MOTD, RPL_ENDOFMOTD, ERR_NOMOTD
    reply_handlers = ["375", "372", "376", "422"]
    command_handlers = ["MOTD"]

    def __init__(self, id, handler, name='motd'):
        EventStore.__init__(self, id, handler, name)

    def msg_formatter(event):

        #    if i.command in MotdES.reply_handlers:
        return "%s MOTD: %s" % (timeformat(event.timestamp), event.params_endpart)
    msg_formatter = staticmethod(msg_formatter)

class NickES(EventStore):
    reply_handlers = ["NICK", "433", "437", "001", "438"] # 433 = nick already in use
    # 437 = temporarily unavailable
                                      # 001 = welcome, tells the nick
    command_handlers = ["NICK"]

    def __init__(self, id, handler, name='nick'):
        EventStore.__init__(self, id, handler, name)

    def add_event(self, event):
        self._add(event)
        if event.command in ['433', '437']: # handle nick in use scenario
            triednick = event.params.split()[1]
            if not self.handler.nicknames.index(triednick) + 1 == len(self.handler.nicknames):
                nextnick = self.handler.nicknames[self.handler.nicknames.index(triednick) + 1]
                self.handler.send_command('NICK', nextnick)
            else:
                self.handler.receive_status(104, 'all nicknames in use')
        elif event.command == '001':
            self.handler.nickname = event.params.split()[0]
            self.handler.receive_status(10, 'connected normally')
        elif event.command == 'NICK':
            if prefix2nick(event.prefix) == self.handler.nickname:
                newnick = event.params[1:]
                self.handler.nickname = newnick

class WhoES(EventStore):
    reply_handlers = ['352', '315'] # RPL_WHOREPLY, RPL_ENDOFWHO
    command_handlers = ['WHO']

    def __init__(self, id, handler, name='who'):
        EventStore.__init__(self, id, handler, name)

class RawES(EventStore):
    """A special class that sends parameters to the server as is"""
    reply_handlers = []
    command_handlers = ['RAW']

    def __init__(self, id, handler, name='raw'):
        EventStore.__init__(self, id, handler, name)

    def generate_event(self, cmd, params):
        params = params.split(' ')
        command = params[0]
        params = ' '.join(params[1:])
        e = Event(prefix="", command=command, params=params, generated=True)
        self._eventlist.append(e)
        return [e.irc_format()]


class PrivmsgStore(EventStore):
    """A store for private messages. Target is specified when creating the object"""
    reply_handlers = ["NICK"]
    command_handlers = []

    def __init__(self, id, handler, target, name=""):
        EventStore.__init__(self, id, handler, name)
        self.target = target

    def __str__(self):
        return "target: %s, id: %s, name: %s, %d events" % (self.target, \
                self.id, self.name, len(self._eventlist))


    def _ctcphandler(self, event):
        """preliminary CTCP support. Currently returns a reasonable VERSION reply,
        nothing else"""

        if event.params_endpart == '\001VERSION\001':
            from pyircfs import VERSION
            import os
            return "\001VERSION %s %s running on %s\001" % \
                   ("pyircfs", '.'.join([str(x) for x in VERSION]),
                    os.uname()[0])



    def add_event(self, event):
        # only add messages that are targeted to us
        if event.command in ['PRIVMSG', 'NOTICE'] and \
        prefix2nick(event.prefix).lower() == self.target.lower():
            self._add(event)

            if event.params_endpart and event.params_endpart[0] == '\001' \
            and event.params_endpart[-1] == '\001':  # a CTCP message
                msg = self._ctcphandler(event)
                if msg:
                    # return a reply if we got one from the ctcp handler
                    self.handler.send_notice(self.target, msg)


        elif event.command == 'NICK' and prefix2nick(event.prefix) == \
        self.target:
            self.target = event.params[1:]
            self._add(event)

    def msg_formatter(event):
        ts = timeformat(event.timestamp)
        nick = prefix2nick(event.prefix)
        hostmask = prefix2hostmask(event.prefix)

        if event.command == 'PRIVMSG':
            if event.params_endpart and event.params_endpart[0] == '\001' \
            and event.params_endpart[-1] == '\001':      # a CTCP query
                query = event.params_endpart[1:-1]
                if query.startswith('ACTION'): # /me something
                    return '%s * %s %s' % (ts, nick, ' '.join(query.split(' ')[1:]))
                return '%s CTCP %s query received from %s' % \
                           (ts, query, nick)
            else:
                return '%s <%s> %s' % (ts, nick, event.params_endpart)
        elif event.command == 'JOIN':
            if event.generated:
                return " -> JOIN"

            return "%s %s (%s) has joined %s" % \
                   (ts, nick, hostmask, event.params_endpart)
        elif event.command == 'PART':
            return "%s %s (%s) has left %s (%s)" % \
                   (ts, nick, hostmask, event.params.split()[0], event.params_endpart)
        elif event.command == 'KICK':
            return "%s %s (%s) was kicked from %s (%s)" % \
                   (ts, nick, hostmask, event.params.split()[0], event.params_endpart)

        elif event.command == 'QUIT':
            return "%s %s (%s) quit (%s)" % \
                   (ts, nick, hostmask, event.params_endpart)

        elif event.command in ['353', '366', '352']:
            # don't write NAMES or WHO list, they'll be in the nicklist
            return ''
        else:
            return EventStore.msg_formatter(event)

    msg_formatter = staticmethod(msg_formatter)

    def generate_event(self, type, message):
        own_hostmask = ":%s!%s@unknown" % (self.handler.nickname,
                                           self.handler.username)
        e = Event(prefix=own_hostmask, command=type, params="%s :%s" %
                  (self.target, message), generated=True)
        self._add(e)
        return ["%s %s :%s" % (type, self.target, message)]


class ChannelStore(PrivmsgStore):
    """A store for messages in an IRC channel. Keeps list of people
    in channel, their flags, etc"""
    reply_handlers = ["NICK", "JOIN", "PART", "QUIT", "KICK", "MODE",
                      "353", "332","404", '352', '324', '332', '367',
                      "471", "473", "474", "475"] # names

    def __init__(self, id, handler, target, name="", joined=False):
        PrivmsgStore.__init__(self, id, handler, target, name)
        self.joined = joined
        self.send_queue = []
        self.join_sent = False
        self.nicknames = {}

        # these are channel flags etc.
        self.channelmode = []
        self.topic = ""
        self.bans = []
        self.invites = []
        self.exceptions = []

    def remove(self):
        self.handler.send_command('PART', self.target)
        EventStore.remove(self)

    def add_event(self, event):

        # where's the target channel in the message?
        if event.command in ['JOIN', 'NICK', 'QUIT']:
            target = event.params.split()[0][1:]
        elif event.command in ['PRIVMSG', 'NOTICE', 'PART', 'MODE', 'KICK']:
            target = event.params.split()[0]
        elif event.command in ['353']:
            target = event.params.split()[2]
        elif event.command in ['366', '404', '475', '473', '474', '471', '352', '324',
                               '332', '367']:
            target = event.params.split()[1]
        else:
            target = ""
        #print "we got the part msg! %s", event

        clear_send_queue = False
        add = True

        if target.lower() == self.target.lower():

            if event.command == 'JOIN':
                if not self.joined: # and prefix2nick(event.prefix) == self.handler.nickname:
                    # when joined, mark the send queue to be cleared
                    self.joined = True
                    self.join_sent = False
                    clear_send_queue = True

                # add the nick to the list
                self.nicknames[prefix2nick(event.prefix)] = \
                    {'hostmask': event.prefix[event.prefix.index('!')+1:]}


            elif event.command in ['471', '473', '474', '475']: #
                # in case of "Cannot join channel" errors,
                # stop waiting for a JOIN, empty the send queue
                self.join_sent = False
                self.send_queue = []

            elif event.command == '353': # RPL_NAMREPLY
                add = False
                for nick in event.params_endpart.split():
                    if not nick.strip('+@') in self.nicknames:
                        self.nicknames[nick.strip('+@')] = {}

                    self.nicknames[nick.strip('+@')]['op'] = '@' in nick
                    self.nicknames[nick.strip('+@')]['voice'] = '+' in nick

            elif event.command == '352': # RPL_WHOREPLY
                add = False
                params = event.params.split()
                nick = params[5]
                if not nick in self.nicknames:
                    self.nicknames[nick] = {}

                self.nicknames[nick]['username'] = params[2]
                self.nicknames[nick]['hostname'] = params[3]
                self.nicknames[nick]['server'] = params[4]
                self.nicknames[nick]['op'] = '@' in params[6]
                self.nicknames[nick]['voice'] = '+' in params[6]
                self.nicknames[nick]['away'] = 'G' in params[6]
                self.nicknames[nick]['hopcount'] = params[7].strip(':')
                self.nicknames[nick]['realname'] = ' '.join(params[9:])


            elif event.command == "PART":
                if prefix2nick(event.prefix) == self.handler.nickname:
                    self.joined = False  # we parted
                    self.nicknames = {}
                else:
                    self.nicknames.pop(prefix2nick(event.prefix))

            elif event.command == "MODE":
                modes = extract_modes(event.params)
                for mode in modes:
                    if len(mode) > 1: # has a parameter in addition to flag
                        # sometimes (after netsplits) MODEs come before JOINs;
                        if not mode[1] in self.nicknames:
                            self.nicknames[mode[1]] = {}
                        if mode[0][1] == 'o':
                            self.nicknames[mode[1]]['op'] = '+' in mode[0]
                        elif mode[0][1] == 'v':
                            self.nicknames[mode[1]]['voice'] = '+' in mode[0]
                        elif mode[0] == '+b':
                            if not mode[1] in self.bans:
                                self.bans.append(mode[1])
                        elif mode[0] == '-b':
                            if mode[1] in self.bans:
                                self.bans.remove(mode[1])

            elif event.command == "KICK":
                if event.params.split()[1] == self.handler.nickname:
                    self.joined = False
                    self.nicknames = {}
                else:
                    self.nicknames.pop(event.params.split()[1])

            elif event.command == "324": # RPL_CHANNELMODEIS
                self.channelmode = extract_modes(' '.join(event.params.split()[1:]))
                add = False

            elif event.command == "332": #RPL_TOPIC
                self.topic = event.params_endpart
                add = False

            elif event.command == "367": #RPL_BANMASK
                ban = event.params.split()[2]
                if ban not in self.bans:
                    self.bans.append(ban)
                add = False

            if add:
                self._add(event)

        elif event.command == 'QUIT' and prefix2nick(event.prefix) in self.nicknames:
            # update nicklist and add event to current queue if the nick is in channel
            self.nicknames.pop(prefix2nick(event.prefix))
            self._add(event)

        elif event.informational:
            self._add(event)

        if clear_send_queue:
            [self.handler.send_message(self.target, msg) for msg in self.send_queue]
            self.send_queue = []
            # send a who query too to add some info to the channel list
            # and channel mode query too
            self.handler.send_command('WHO', self.target)
            self.handler.send_command('MODE', self.target)
            self.handler.send_command('MODE', self.target + ' b')


    def generate_event(self, type, message):
        ret = []
        own_hostmask = ":%s!%s@unknown" % (self.handler.nickname,
                                           self.handler.username)
        if not self.joined:
            # if we are not joined, a JOIN is sent and
            # other messages are appended to a queue which will be
            # released by add_event when it receives a JOIN
            # (or discarded if it receives an error preventing joining)
            if not self.join_sent:
                e = Event(prefix=own_hostmask, command='JOIN', params = self.target
                          , generated=True)

                #ret.append('JOIN %s' % self.target)
                self.handler.send_command('JOIN', self.target)
                self._add(e)
                self.join_sent = True

            #e = Event(prefix=own_hostmask, command=type, params="%s :%s" %
                      #(self.target, message), generated=True)
            self.send_queue.append(message)
            #ret.append('%s %s :%s' % (type, self.target, message))
        else:
            e = Event(prefix=own_hostmask, command=type, params="%s :%s" %
                      (self.target, message), generated=True)
            self._add(e)
            ret.append(e.irc_format())
        return ret


if __name__ == '__main__':
    print extract_modes('#x998 +v test')
    print extract_modes('#x998 +tnl 123')
