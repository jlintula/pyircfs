# pyircfs (Python IRC filesystem)

### Introduction

This is a filesystem abstraction layer for IRC (Internet Relay Chat). It
requires Python 2.x and python-fuse 0.2 or newer. I've tested it on
Linux and OS X with osxfuse.

I originally wrote this as an assignment during a network protocols class back
in 2009. Seven years later I decided to dig this thing up, fix some glaring bugs
and release it. It's not complete, pretty, or probably even useful, but it
works!

I had tried to implement any features that make obvious sense as a filesystem
abstraction and some that probably don't: Creating a file with # or & (etc) in
front tries to join a channel with that name, removing such file parts the
channel, etc.

### Features

- See channels and private messages as files and write to them
  - Channels and nicks (that can be written to and read from) are at the root
  of the mount point. Creating a new file attempts to write to a new nick or
  channel with that name.
  - For example, you can use `echo something > (channel|nick)` or `echo
  something >> (channel|nick)` (append), or even
  use a text editor and write to end of an existing file (as long as the
  editor doesn't remove and rewrite the file). Pyircfs tries to
  recognize what was in the file already and not resend that.
- See nicknames in channels as files, cat them to view WHOIS info and write
  to them to send a message
  - Channel nicknames appear as files under names/[channel]/ and when
  written to, a new nick is added to root
- Send any supported IRC command and see its results by accessing
  commands/[command]. Commands "files" appear there once they are used.
- Send any unsupported / unknown IRC command by writing to commands/raw
- See everything received from the server by reading info/all_recv
- See connection status by reading info/status
- Execute an IRC command on a nick by moving the nick file to commands/command
- And much more!

### Usage

```
$ pyircfs.py [mountpoint] [options]

Options:
    --version              show program's version number and exit
    -h, --help             show this help message and exit
    -o opt,[opt...]        mount options
    -o server=FOO          IRC server address
    -o nickname=FOO        nickname (default: username)
    -o altnick=FOO         alternative nickname (default: none)
    -o username=FOO        username (default: username)
    -o realname=FOO        username (default: username)
```

At least mount point and IRC server must be specified. To unmount, run
fusermount -u mountpoint (Linux) or umount mountpoint (OS X).

### Examples

##### Mounting and waiting for connection
```
$ ./pyircfs.py mnt/ -o nickname=test1234 -o server=irc.cc.tut.fi
$ tail -F mnt/info/all_recv
[10:34:47] :irc.cc.tut.fi 020 * :Probing for proxies open to abuse.
[10:35:19] :irc.cc.tut.fi 001 test1234 :Welcome to the Internet Relay Network test1234!-jlintula@85.76.75.177
^C
$ grep status mnt/info/status
Connection status: 10 (connected normally)
```
##### Joining a normal channel / saying something to someone
```
$ cd mnt
$ echo hello >> "#test987"
$ ls -l
total 8
-rw-r--r--  1 jlintula  1807955708  163 Mar 30 09:31 #test987
drwxr-xr-x  2 jlintula  1807955708    0 Mar 30 09:28 commands/
drwxr-xr-x  2 jlintula  1807955708    0 Mar 30 09:28 info/
drwxr-xr-x  2 jlintula  1807955708    0 Mar 30 09:28 names/
$ cat "#test987"
-> JOIN
[09:30:29] test1234 (-jlintula@85.76.75.177) has joined #test987
[09:30:29] <test1234> hello
[09:30:47] <Kusilahna> tervetuloa
[09:31:04] <TAUSKI666> yes
```
##### Listing channel members
```
$ ls -l names/\#test987
total 24
-rw-r--r--  1 jlintula  1807955708  137 Mar 30 09:28 Kusilahna
-rw-r--r--  1 jlintula  1807955708  140 Mar 30 09:28 TAUSKI666
-rw-r--r--  1 jlintula  1807955708  164 Mar 30 09:28 test1234

$ cat names/\#test987/test1234
username: -jlintula
realname: jlintula
hostmask: -jlintula@85.76.75.177
away: False
hostname: 85.76.75.177
server: irc.cc.tut.fi
hopcount: 0
voice: False
op: False
```
##### Sending a private message to someone in channel
```
$ echo hi > names/\#test/TAUSKI666
$ cat TAUSKI666
[09:31:05] <test1234> hi
[09:31:13] <TAUSKI666> terve
```
(`echo hi > nick` at filesystem root would of course work too)
##### Listing information about channel
```
$ cat "info/#test987"
topic: This is a topic
channel modes: [('+s',), ('+t',), ('+n',), ('+l', '616')]
bans (+b): []
ban exceptions (+e): []
invites (+I): []
nicknames: 2
```
##### Joining a channel with a channel key (+k)
```
$ echo "#channelname s3cr3t" > commands/join
```
##### Another way to join a channel
```
$ mkdir "names/#channel"
```
##### Leaving a channel
```
$ echo "#channel goodbye" > commands/part
```
OR
```
$ rm "#channel"
```
##### Being annoying
```
$ cat /proc/cpuinfo > "#channel"
```

### Architecture

- **pyircfs.py** is the main module where FUSE specific magic and filesystem
functions are.
- **lib/connection.py** contains the low level code responsible for
communicating with an IRC server.
- **lib/handler.py** does the work between connection and the classes in *events.py*.
- **lib/events.py** contains classes for "events" (that deal with single IRC commands
and responses) and "event stores" that group events for private
messages, channels, IRC commands and everything else. The event store classes
have attributes that define what incoming and outgoing messages they are
interested in, and  *handler.py* automatically recognizes these classes from here.
- **view.py** is a very basic CLI interface that can be used to test some of the
IRC functionality without using FUSE.

### TODO / Issues

- Add better error handling and test with more advanced IRC servers
- Understand / pretty-print more IRC responses (esp. MODE)
- Add smarter connection handling and flood prevention
- Add support for more IRC features, channel flags, etc
- Add support for multiple IRC servers
- Add support for reconnecting/disconnecting (handler supports it already but
    FUSE part doesn't), auto reconnects, ping timeout detection
- tail -f doesn't work for stores but tail -F (--follow=name) does
- Make commands/raw visible from the beginning, for discoverability,
  maybe others too
- Add a persistent storage backend: Currently everything is stored in memory
- Add cache for eventstore to string (file) conversions?
- And much more!
