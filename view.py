# -*- coding: utf-8 -*-

'''
Created on 24.2.2009

@author: Jaakko Lintula

simple test CLI
'''

import lib.handler as handler
import lib.events as events
from lib.handler import ConnectionError
import time
import sys

SERVER = 'irc.cc.tut.fi'
NICKLIST = ['testi123', 'testi456', 'testi789']
USERNAME = 'test'
REALNAME = 'test'

class Cmdview:

    def __init__(self):
        self.followed_objects = {}
        pass

    def new_store_event(self, obj):
        if isinstance(obj, events.PrivmsgStore) or\
        obj.name == 'all_replies':
            obj.update_callbacks.append(self.store_update_event)
            obj.remove_callbacks.append(self.store_remove_event)

    def store_update_event(self, obj):
        #pass
        if isinstance(obj, events.PrivmsgStore):
            print "%s: %s" % (obj.target, obj.msg_formatter(obj._eventlist[-1]))
        elif obj.name == 'all_replies':
            print "%s" % obj.msg_formatter(obj._eventlist[-1])
            #print "%s: %s" % (obj.target, obj.msg_formatter(len(obj._eventlist)-1))


    def store_remove_event(self, obj):
        print "object removed", obj

    def main(self):

        error = None
        h = handler.Handler()

        h.reply_stores.append(('*', h._create_new_store(events.EventStore, name="all_recv")))
        replystore = h._create_new_store(events.EventStore, name="all_replies")
        [h.reply_stores.append((str(x), replystore)) for x in range(0,400)]

        h.new_store_callbacks.append(self.new_store_event)

        try:
            h.connect(server=SERVER, nicknames=NICKLIST, username=USERNAME, realname=REALNAME)
        except ConnectionError, e:
            print "error! ", e
            sys.exit(-1)

        run = True
        while run:
            l = raw_input('> ')
            cmd = l.split(' ')[0]
            params = ' '.join(l.split(' ')[1:])
            if cmd == 'q':
                h.send_command('QUIT', params)
                time.sleep(2)
                run = False
            if cmd == 'disco':
                h.send_command('QUIT', params)
            elif cmd == "reconn":
                try:
                    h.reconnect()
                except ValueError, e:
                    print e


            elif cmd == 'l':
                print "COMMAND STORES:",
                print h.list_command_stores()
                print "REPLY STORES:",
                print h.list_reply_stores()
                print "PRIVMSG STORES:",
                print h.list_privmsg_stores()
                print "all stores: ", h.all_stores
                print "info stores: ", h.list_info_stores()

            elif cmd == 'p':
                try:
                    print '\n'.join(h.all_stores[int(params)].get_contents())
                    print h.all_stores[int(params)].get_size()
                except KeyError:
                    print "wrong id"
                except ValueError:
                    print "ERROR: that's no number"

            elif cmd == 'pc':
                try:
                    print '\n'.join(h.list_command_stores()[params].get_contents())
                except KeyError:
                    print "ERROR: unknown command store"
            elif cmd == 'pr':
                try:
                    print '\n'.join(h.list_reply_stores()[params].get_contents())
                except KeyError:
                    print "ERROR: unknown reply store"
            elif cmd == 'pp':
                try:
                    print '\n'.join(h.list_privmsg_stores()[params].get_contents())
                except KeyError:
                    print "ERROR: unknown reply store"
            elif cmd == 'sc':
                try:
                    p = params.split()
                    h.send_command(p[0], ' '.join(p[1:]))
                except ValueError, e:
                    print "ERROR: ", e
            elif cmd == 'cc':
                try:
                    p = params.split()
                    h.create_command_store(p[0])
                except ValueError, e:
                    print "ERROR: ", e
            elif cmd == 'm':
                if len(params) == 0: break
                try:
                    t = params.split()[0]
                    m = params[params.index(' ') + 1:]
                    h.send_message(t, m)
                except ValueError:
                    print "failed"

            elif cmd == 'rm':
                try:
                    h.remove_store(int(params))
                except ValueError:
                    print "failed"

            elif cmd == 'ln':
                try:
                    print h.list_privmsg_stores()[params].nicknames
                    print h.list_privmsg_stores()[params].channelmode
                except KeyError:
                    print "ERROR: unknown privmsg store"


        #h.close()

if __name__ == '__main__':
    a = Cmdview()
    a.main()
