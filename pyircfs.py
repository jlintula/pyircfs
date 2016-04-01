#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Created on 24.2.2009

@author: Jaakko Lintula <jaakko.lintula@iki.fi>
'''

import os, stat, errno, time, sys, re, logging
import fuse
from fuse import Fuse

import lib.handler as handler
import lib.events as events
from lib.handler import ConnectionError

if not hasattr(fuse, '__version__'):
    raise RuntimeError, \
        "your fuse-py doesn't know of fuse.__version__, probably it's too old."

fuse.fuse_python_api = (0, 2)

# pyircfs version
VERSION = (0, 1, 0)

LOG_FILENAME = "pyircfs.log"
#logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG, format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
#                    datefmt='%m-%d %H:%M:%S',)


def basename(path):
    try:
        return path[path.rindex('/')+1:]
    except ValueError:
        return path


class MyStat(fuse.Stat):

    ctime = time.time()

    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = os.getuid()
        self.st_gid = os.getgid()
        self.st_size = 0
        self.st_atime = MyStat.ctime
        self.st_mtime = MyStat.ctime
        self.st_ctime = MyStat.ctime

class PyIrcFS(Fuse):

    def __init__(self, *args, **kwargs):
        Fuse.__init__(self, *args, **kwargs)

        self.commanddir = '/commands'
        self.infodir = '/info'
        self.namesdir = '/names'
        self.privmsgdir = '/'
        self.statuspath = self.infodir + '/status'

    def fsinit(self):
        h = handler.Handler()
        h.reply_stores.append(('*', h._create_new_store(events.EventStore, name="all_recv")))
        if self.altnick:
            nicks = [self.nickname, self.altnick]
        else:
            nicks = [self.nickname]

        h.connect(server=self.server, nicknames=nicks, username=self.username, realname=self.realname)
        self.handler = h

    def _status(self):
        buf = ""
        buf += "Connection status: %d (%s)\n" % self.handler.connection_status
        buf += "(since %s)\n\n" % time.localtime(self.handler.connection_status_timestamp)
        buf += "server: %s:%d\n" % (self.handler.server, self.handler.port)
        buf += "output queue size: %d\n" % (len(self.handler.connection.out_queue))
        buf += "nicklist: %s\n" % self.handler.nicknames
        buf += "nickname: %s\n" % self.handler.nickname
        buf += "username: %s\n" % self.handler.username
        buf += "realname: %s\n" % self.handler.realname
        return buf

    def _nickinfo(self, nick):
        buf = ["%s: %s\n" % (x, nick[x]) for x in nick]
        return ''.join(buf)

    def _channelinfo(self, channel):
        channel = self.handler.list_privmsg_stores()[channel]
        buf = ""
        buf += "topic: %s\n" % channel.topic
        buf += "channel modes: %s\n" % channel.channelmode
        buf += "bans (+b): %s\n" % channel.bans
        buf += "ban exceptions (+e): %s\n" % channel.exceptions
        buf += "invites (+I): %s\n" % channel.invites
        buf += "nicknames: %d\n" % len(channel.nicknames.keys())
        return buf

    def _search(self, path):
        """Returns a filesystem object for the given path, if found"""
        logging.debug("ENTER _search: " + path)
        ret = {}
        st = MyStat()
        if path in ['/', self.privmsgdir, self.commanddir, self.infodir, self.namesdir] :
            logging.debug("search: this is known hardcoded dir")
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 2
            ret['obj'] = None
            ret['objtype'] = 'rootdir'
            ret['attr'] = st
            if path == self.privmsgdir:
                ret['files'] = self.handler.list_privmsg_stores().keys()
                ret['files'].append(self.commanddir[1:])
                ret['files'].append(self.infodir[1:])
                ret['files'].append(self.namesdir[1:])

            elif path == self.commanddir:
                ret['files'] = self.handler.list_command_stores().keys()
            elif path == self.infodir:
                ret['files'] = self.handler.list_info_stores().keys()
                ret['files'].append(basename(self.statuspath))
                ret['files'] += [x for x in self.handler.list_privmsg_stores().keys() \
                                 if x[0] in handler.CHANCHARS]

            elif path == self.namesdir:
                ret['files'] = [x for x in \
                             self.handler.list_privmsg_stores().keys() if \
                             x[0] in handler.CHANCHARS]

            return ret


        if path.startswith(self.namesdir + '/') and \
        basename(path) in self.handler.list_privmsg_stores('channel').keys():
            logging.debug("search: this is a dir under /channels")
            # a channel dir under /channels
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 2
            ret['obj'] = None
            ret['attr'] = st
            ret['files'] = self.handler.list_privmsg_stores()[basename(path)].nicknames.keys()
            ret['objtype'] = 'nickdir'
            return ret

        if re.match("^%s/(\S+)/(\S+)$" % self.namesdir, path):
            channel, nick = re.match("^%s/(\S+)/(\S+)$" %
                                         self.namesdir, path).groups()
            logging.debug("search: resolved channel %s and nick %s" % (channel, nick))
            if channel in self.handler.list_privmsg_stores().keys() and \
            nick in self.handler.list_privmsg_stores()[channel].nicknames.keys():
                logging.debug("search: this is a nick file under channels/#channel")
                # a nick file under /channels/#channel
                ret['obj'] = self._nickinfo(self.handler.list_privmsg_stores()[channel].nicknames[nick])

                ret['objtype'] = 'nick'

                st.st_mode = stat.S_IFREG | 0644
                st.st_nlink = 1
                st.st_size = len(ret['obj'])
                ret['attr'] = st
                #logging.debug("search: returning nickfile: %s" % ret)
                return ret

        if len(path) > 1 and path.count('/') == 1 and \
        basename(path) in self.handler.list_privmsg_stores().keys():
            logging.debug("search: this is a privmsg store")
            ret['obj'] = self.handler.list_privmsg_stores()[basename(path)]
            ret['objtype'] = 'privmsg'
            st.st_mode = stat.S_IFREG | 0644
            st.st_nlink = 1
            st.st_size = ret['obj'].get_size()
            st.st_ctime = ret['obj'].get_ctime()
            try:
                st.st_atime = ret['obj']._eventlist[-1].timestamp
            except IndexError:
                st.st_atime = st.st_ctime
            st.st_mtime = st.st_atime
            ret['attr'] = st
            return ret

        elif path.startswith(self.commanddir + '/') and \
        basename(path) in self.handler.list_command_stores().keys():
            logging.debug("search: this is a command store")
            ret['obj'] = self.handler.list_command_stores()[basename(path)]
            ret['objtype'] = 'command'
            st.st_mode = stat.S_IFREG | 0644
            st.st_nlink = 1
            st.st_size = ret['obj'].get_size()
            st.st_ctime = ret['obj'].get_ctime()
            try:
                st.st_atime = ret['obj']._eventlist[-1].timestamp
            except IndexError:
                st.st_atime = st.st_ctime
            st.st_mtime = st.st_atime
            ret['attr'] = st
            return ret

        elif path.startswith(self.infodir + '/') and \
        basename(path) in self.handler.list_info_stores().keys():
            logging.debug("search: this is an info store")
            ret['obj'] = self.handler.list_info_stores()[basename(path)]
            ret['objtype'] = 'info'
            st.st_mode = stat.S_IFREG | 0444
            st.st_nlink = 1
            st.st_size = ret['obj'].get_size()
            st.st_ctime = ret['obj'].get_ctime()
            try:
                st.st_atime = ret['obj']._eventlist[-1].timestamp
            except IndexError:
                st.st_atime = st.st_ctime
            st.st_mtime = st.st_atime
            ret['attr'] = st
            return ret

        elif path.startswith(self.infodir + '/') and \
        basename(path) in self.handler.list_privmsg_stores().keys():
            ret['obj'] = self._channelinfo(basename(path))
            ret['objtype'] = 'channelinfo'
            st.st_mode = stat.S_IFREG | 0444
            st.st_nlink = 1
            st.st_size = len(ret['obj'])
            st.st_mtime = self.handler.connection_status_timestamp
            st.st_atime = st.st_mtime
            ret['attr'] = st
            return ret

        elif path == self.statuspath:
            ret['obj'] = self._status()
            ret['objtype'] = 'status'
            st.st_mode = stat.S_IFREG | 0444
            st.st_nlink = 1
            st.st_size = len(ret['obj'])
            st.st_mtime = self.handler.connection_status_timestamp
            st.st_atime = st.st_mtime
            ret['attr'] = st
            return ret

    def _read_store_contents(self, store):
        if store['objtype'] in ['nick', 'status', 'channelinfo']:
            # return "special" file object contents
            return str(store['obj']) + '\n'
        else:
            # return IRC message store contents
            return '\n'.join(store['obj'].get_contents()) + '\n'


    def fsdestroy(self):
        if self.handler.connection_status[0] in (1, 10):
            self.handler.send_command("QUIT", "pyircfs %s unmounted" %
                                      '.'.join([str(x) for x in VERSION]))

            time.sleep(1)

            while not self.handler.connection_status[0] == 100:
                time.sleep(0.1)


    def truncate(self, path, size):
        return 0
    def fsync(self, path, isfsyncfile):
        return 0
    def utime(self, path, times):
        return 0
    def mkdir(self, path, mode):
        """mkdir /names/#channel creates a new channel store
           and attempts to JOIN"""
        if self._search(path):
            raise OSError(errno.EEXIST, 'file exists', path)
        if path.startswith(self.namesdir):
            if not basename(path)[0] in handler.CHANCHARS:
                raise OSError(errno.EACCES, 'permission denied', path)
            self.handler.create_privmsg_store(basename(path))
            self.handler.send_command('JOIN', basename(path))

            return 0
        else:
            raise OSError(errno.EACCES, 'permission denied', path)

#    def rmdir(self, path):
#        """rm -rf /channels/#channel is the same as rm /#channel"""
#        store = self._search(path)
#        if not store:
#            raise OSError(errno.ENOENT, 'no such directory', path)
#        if store['objtype'] == 'nickdir':
#            chanobj = self.search('/' + basename(path))['obj']
#            self.handler.remove_store(self.handler.get_store_id(chanobj))
#            return 0
#        else:
#            raise OSError(errno.EACCES, 'permission denied', path)


    def rename(self, source, target):
        """mv privmsg/nickfile commands/command executes
           command with the source file name as a parameter,
           eg. mv nick commands/whois"""

        sstore = self._search(source)
        tstore = self._search(target)
        if not sstore:
            raise OSError(errno.ENOENT, "unknown source", source)
        if not tstore:
            if target.startswith(self.commanddir):
                tstore = {'objtype': 'command'}
            else:
                raise OSError(errno.EACCES, "permission denied", target)
        if 'files' in sstore or 'files' in tstore:
            # moving directories don't make much sense here
            raise OSError(errno.EISDIR, "is a directory", sstore)
        if not tstore['objtype'] == 'command':
            raise OSError(errno.EACCES, "permission denied", tstore)
        if sstore['objtype'] in ['privmsg', 'nick']:
            #self.write(target, basename(source), 0)
            self.handler.send_command(basename(target),
                                      basename(source))
        else:
            raise OSError(errno.EACCES, "permission denied", tstore)


    def getattr(self, path):
        logging.debug("ENTER getattr: " + path)
        s = self._search(path)
        logging.debug("getattr result: " + str(s))
        if s and 'obj' in s:
            return s['attr']
        else:
            raise OSError(errno.ENOENT, "no such file or directory", path)

    def readdir(self, path, offset):
        stores = self._search(path)
        if 'files' in stores:
            stores = stores['files']
        else:
            stores = []

        for i in ['.', '..'] + sorted(stores):
            yield fuse.Direntry(i)

    def open(self, path, flags):
        logging.debug("ENTER open - path %s flags %s" % (path, flags))
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR

        store = self._search(path)
        logging.debug("open: resolved target store as %s " % store)
        if not store:
            raise OSError(errno.ENOENT, "no such file", path)

        if (flags & os.O_RDONLY == os.O_RDONLY):
            return 0   #reading is always supported

        if store['objtype'] == 'info' and (flags & accmode) != os.O_RDONLY:
            raise OSError(errno.EACCES, "permission denied", path)

    def read(self, path, size, offset):

        store = self._search(path)
        if not store:
            raise OSError(errno.ENOENT, 'no such file or directory', path)

        contents = self._read_store_contents(store)

        slen = len(contents)
        if offset < slen:
            if offset + size > slen:
                size = slen - offset
            buf = contents[offset:offset+size]
        else:
            buf = ''
        return buf

    def write(self, path, buf, offset):
        logging.debug("ENTER write: path: %s offset: %s buf: %s" % (path, offset, buf) )
        if path.startswith(self.privmsgdir):
            stype = 'privmsg'
        if path.startswith(self.commanddir):
            stype = 'command'
        elif path.startswith(self.infodir):
            raise OSError(errno.EACCES, "permission denied", path)
        elif path.startswith(self.namesdir):
            stype = 'nick'

        file = path[path.rindex('/')+1:]

        logging.debug("write: resolved stype: %s file: %s" % (stype, file))

        try:
            if stype in ['privmsg', 'nick']:
                method = self.handler.send_message
            elif stype == 'command':
                method = self.handler.send_command

            # Attempt to handle cases where the whole file is rewritten
            # instead of being attempted to -- skip the part from beginning
            # or end that matches the existing contents - necessary for
            # at least osxfuse and text editor use

            send_buf = buf # truncating the buf object used in write() iocall
                           # causes an i/o error to client
            try:
                store = self._search(path)
                if store:
                    storecontents = self._read_store_contents(store)
                    #logging.debug("storecontents: %s " % storecontents)
                    buf_index = buf.find(storecontents)
                    if len(storecontents) > 1 and buf_index == 0:
                        # truncate what will be written to file because it
                        # contains the beginning already
                        logging.debug("write: TRUNCATING buf by %s bytes" % (len(storecontents)))
                        send_buf = buf[len(storecontents):]

                    elif len(storecontents) > 0 and buf_index == -1:
                        # osxfuse (?) special case for "command > buffer"
                        # redirections from cmdline, where buf starts with new
                        # content and rest of it is the old store contents,
                        # attempt to prevent spamming
                        i = 0
                        # walk through lines and look for position where rest
                        # are contained in the store. line by line is enough
                        logging.debug("write: looking for contents in the beginning")
                        while i != -1:
                            i = buf.find('\n', i) + 1 # get next newline in buf
                            if buf[i:] in storecontents:
                                logging.debug("write: TRUNCATING buf from position %s to: %s" % (i, buf[:i]))
                                send_buf = buf[:i]
                                break

            except:
                logging.debug("write: exception?")

            for i in send_buf.split('\n'):
                if i:
                    method(file, i.rstrip('\r\n'))
                    if len(self.handler.connection.out_queue) > 30: # why?
                        time.sleep(2.3) #

        except ConnectionError:
            raise OSError(errno.ENOTCONN, "not connected to server", path)
        else:
            return len(buf)

    def create(self, path, flags, mode):
        if path.startswith(self.privmsgdir):
            stype = 'privmsg'
        if path.startswith(self.commanddir):
            stype = 'command'
        elif path.startswith(self.infodir):
            raise OSError(errno.EACCES, "permission denied", path)
        elif path.startswith(self.namesdir):
            raise OSError(errno.EACCES, "permission denied", path)

        file = basename(path)

        if file.startswith('.'):
            raise OSError(errno.EACCES, "permission denied", path)

        if stype == 'privmsg':
            self.handler.create_privmsg_store(file)
        elif stype == 'command':
            try:
                self.handler.create_command_store(file)
            except ValueError:
                raise OSError(errno.ENOENT, "unknown command", path)
        else:
            raise OSError(errno.EACCES)

    def unlink(self, path):
        store = self._search(path)
        if not store:
            raise OSError(errno.ENOENT, "no such file or directory", path)
        if store['objtype'] == 'info':
            raise OSError(errno.EACCES, "permission denied", path)
        elif store['objtype'] == 'nick':
            return 0

        self.handler.remove_store(self.handler.get_store_id(store['obj']))


def main():
    usage=Fuse.fusage
    server =PyIrcFS(version="%prog " + "%s using python-fuse %s " % (".".join(map(str,(VERSION))), fuse.__version__),
                     usage=usage,
                     dash_s_do='setsingle')
    server.nickname = os.getenv('LOGNAME')
    server.altnick = ''
    server.username = os.getenv('LOGNAME')
    server.realname = os.getenv('LOGNAME')
    server.server = ''
    server.multithreaded = 1
    server.parser.add_option(mountopt="server",
                             help="IRC server address")
    server.parser.add_option(mountopt="nickname",
                             help="nickname (default: %s)" % server.nickname)
    server.parser.add_option(mountopt="altnick",
                             help="alternative nickname (default: none)")
    server.parser.add_option(mountopt="username",
                             help="username (default: %s)" %server.username)
    server.parser.add_option(mountopt="realname",
                             help="username (default: %s)" %server.username)

    server.parse(values=server, errex=1)

    if not server.server:
        if server.parser.fuse_args.modifiers['showversion'] or \
           server.parser.fuse_args.modifiers['showhelp']:
            sys.exit(0)
        print "Please specify mount point and (at least) IRC server!"
        server.parser.print_help()
        sys.exit(-1)

    # start running the server loop
    server.main()

if __name__ == '__main__':
    main()
