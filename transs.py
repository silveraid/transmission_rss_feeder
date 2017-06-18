#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  Copyright (c) 2017 Frank Felhoffer
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#

"""
Python program which is able to automatically feed a transmission service
sourcing from an RSS feed and using regular expressions and age for
filtering the unwanted content
"""

import os, sys
import feedparser
import transmissionrpc
import logging
from logging import handlers
import re
import calendar
import datetime
import argparse
# from pprint import pprint


# The filename of the two database text files
f_added = 'added.txt'

# The filename of the filter file which has
# one regular expression per line
f_filter = 'filter.txt'

def parse_args():
    parser = argparse.ArgumentParser(description='')

    parser.add_argument('-H', '--host', required=False, default='localhost',
        type=str, help='Transmission host (default: %(default)s)')

    parser.add_argument('-P', '--port', required=False, default=9091,
        type=int, help='Transmission port (default: %(default)s)')

    parser.add_argument('-u', '--user', required=False, default='transmission',
        type=str, help='Transmission user (default: %(default)s)')

    parser.add_argument('-p', '--password', required=False, default='transmission',
        type=str, help='Transmission password (default: %(default)s)')

    parser.add_argument('-a', '--age', required=False, default=1800,
        type=int, help='Maximum age of a torrent (default: %(default)s)')

    parser.add_argument('-f', '--feed', required=True, default='transmission',
        type=str, help='RSS Feed URL')

    parser.add_argument('--paused', required=False, action='store_true',
        help='For testing, pauses the transfer')

    parser.add_argument('-v', '--verbose', required=False, action='store_true',
        help='Enables verbose logging')

    args = parser.parse_args()
    return args


# Calculates the time difference between now and a point in time
def sec_diff(time_tuple):
    return (calendar.timegm(datetime.datetime.utcnow().utctimetuple()) -
        calendar.timegm(time_tuple))


# Loads lines from the provided text file and returns with a list
def load_text(fn):
    lines = []

    fp = os.path.join(os.path.abspath(os.path.dirname(
        os.path.abspath(__file__))), fn)

    if os.path.exists(fp):
        with open(fp, 'r') as f:
            for line in f:
                lines.append(line.rstrip('\n'))

    return lines


# Adds a link to the transmission and appends
# the link to the end of the db text file
def add_torrent(tc, item, is_paused):
    # Log
    logging.info("Adding Torrent: " + item.title + " (" + item.link + ")")

    # Adding the torrent file to transmission
    tc.add_torrent(item.link, paused=is_paused)

    # Append the link to the file stores the already added items
    fp = os.path.join(os.path.abspath(os.path.dirname(
        os.path.abspath(__file__))), f_added)

    with open(fp, 'a') as f:
        f.write(item.link + '\n')

# MAIN
def main():

    global verbose

    # Parsing the arguments
    args = parse_args()

    if args.verbose:
        verbose = True
    else:
        verbose = False

    # Print
    print "Transmission RSS feeder v0.01"
    print ""

    # Configure logging
    log = logging.getLogger('')
    log.setLevel(logging.DEBUG)
    format = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(format)
    log.addHandler(ch)

    fh = handlers.RotatingFileHandler('transs.log', maxBytes=(1048576*5), backupCount=7)
    fh.setFormatter(format)
    log.addHandler(fh)

    #
    #
    #

    # Connecting to the transmission service
    try:
        tc = transmissionrpc.Client(args.host, port=args.port,
                user=args.user, password=args.password)
    except transmissionrpc.error.TransmissionError as te:
        logging.error("Error connecting to Transmission: " +
                      str(te).strip())
        exit(0)
    except:
        logging.error("Error connecting to Transmission: " +
                      str(sys.exc_info()[0]).strip())
        exit(0)

    # Log
    logging.info("Transmission connection: OK")

    # Loading the list of the added items
    added_items = load_text(f_added)

    # Loading the list of the filters
    filters = load_text(f_filter)

    # Compiling the filters for faster execution
    compiled_filters = []
    if len(filters):
        if verbose:
            logging.info("processing filters")
        for f in filters:
            if verbose:
                logging.info(" + %s", f)
            compiled_filters.append(re.compile(f))

    # Log
    logging.info("%d filters have been loaded ...", len(filters))

    #
    #
    #

    # Downloading the rss file
    feed = feedparser.parse(args.feed)
    if feed.bozo and feed.bozo_exception:
        logging.error("Error reading feed \'{0}\': ".format(args.feed) +
                      str(feed.bozo_exception).strip())
        return

    # Log
    logging.info("Received %d items from the RSS feed.", len(feed.entries))

    #
    #
    #

    # Statistical values
    aged = old = new = filtered = 0

    # Looping through the items from the rss feed
    for item in feed.entries:

        # Make sure that the entry is fresh, not older than 30 minutes
        torrent_age = sec_diff(item.published_parsed)
        if torrent_age > args.age:
            if verbose:
                logging.info("Ignoring Torrent: " + item.title + ", too old!")
            aged += 1
            continue

        # Check if it is already added
        if item.link in added_items:
            if verbose:
                logging.info("Ignoring Torrent: " + item.title + ", already added!")
            old += 1
            continue

        # Looping through all of the filter items
        okay = False
        if len(compiled_filters):
            for regex in compiled_filters:
                # Checking each of the titles against the filter list
                if regex.match(item.title):
                    add_torrent(tc, item, args.paused)
                    new += 1
                    okay = True
                    break

        if not okay:
            if verbose:
                logging.info("Ignoring torrent: " + item.title + ", filtered out!")
            filtered += 1

        # In case there is no filter adding all files
        else:
            add_torrent(tc, item, args.paused)
            new += 1

    logging.info("SUMMARY")
    logging.info("NEW: %d, OLD: %d, AGED: %d, FILTERED: %d", new, old, aged, filtered)


# Starting the program
if __name__ == "__main__":
    main()