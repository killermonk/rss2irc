#!/usr/bin/env python


import feedparser
import time
import irc
import storage
import threading
import Queue
import logging
from pprint import pprint

REFRESH_TIME = 120

logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s %(levelname)s] (%(threadName)-10s) %(message)s',
)


def grabber(feeds, feed_queue):
    logging.debug('Entering into grabber()')
    while True:
        for feed_name, feed_url in feeds:
            logging.debug('Reading feed {0}'.format(feed_name))
            raw_feed = feedparser.parse(feed_url)
            for entry in raw_feed['entries']:
                entry['title'] = entry['title'].encode('utf-8', 'ignore')
                entry['link'] = entry['link'].encode('utf-8')
                logging.debug("Putting entry '{0}' into feed queue".format(entry['title']))
                feed_queue.put((feed_name, entry))
        time.sleep(REFRESH_TIME)


def publisher(feed_queue, store, irc_queue):
    logging.debug('Entering into publisher()')
    feedback_queue = Queue.Queue()
    while True:
        feed_name, entry = feed_queue.get()
        if not feed_name:
            logging.debug("No items in feed_queue.")
            time.sleep(1)
            continue
        else:
            feed_queue.task_done()

        store.queue.put((feedback_queue, 'publish', feed_name, entry))
        result, feed_name, entry = feedback_queue.get()
        if not feed_name:
            logging.debug("No items in feedback_queue (nothing stored).")
            time.sleep(1)
            continue
        else:
            feedback_queue.task_done()

        if result:
            logging.debug("Entry '{0}' is new, saving.".format(entry['title']))
            irc_queue.put(
                    (
                        irc_thread.botname,
                        ' | '.join([
                                    feed_name,
                                    entry['title'],
                                    entry['link']
                        ])
                    )
            )
            time.sleep(1)
        else:
            logging.debug("Entry '{0}' already saved.".format(entry['title']))


def main():
    host = 'irc.freenode.net'
    port = 6667
    channel = '#999net'
    channels = [channel]
    feeds = [
        ('HN', 'https://news.ycombinator.com/rss'),
        ('TorrentFreak', 'http://feeds.feedburner.com/Torrentfreak')
    ]
    feed_queue = Queue.Queue()

    # Satisfying IRCConnector interface
    main_thread = threading.current_thread()
    main_thread.kill_received = threading.Event()

    grabber_thread = threading.Thread(target=grabber, args=(feeds, feed_queue), name='Grabber')
    grabber_thread.daemon = True
    grabber_thread.start()

    irc_thread = irc.IRCConnector(main_thread, host, port, channels)
    irc_thread.daemon = True
    irc_thread.start()

    irc_queue = None
    while True:
        try:
            irc_queue = irc_thread.channel_queues[channel]
        except KeyError:
            logging.warning("No channel_queues['{0}'] instantiated. Get some sleep.".format(channel))
            time.sleep(5)
        else:
            logging.info("channel_queues['{0}'] instantiated. Go ahead.".format(channel))
            break

    store = storage.Storage()
    publisher_thread = threading.Thread(target=publisher, args=(feed_queue, store, irc_queue), name='Publisher')
    publisher_thread.start()

    threads = []
    threads.append(grabber_thread)
    threads.append(irc_thread)
    threads.append(store)
    threads.append(publisher_thread)
    while not main_thread.kill_received.is_set():
        continue
    store.kill_received.set()


if __name__ == '__main__':
    main()
