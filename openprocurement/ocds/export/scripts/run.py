from gevent import monkey; monkey.patch_all()
import argparse
import os.path
import sys
import yaml
import logging
import functools
import gevent
from openprocurement.ocds.export.storage import TendersStorage, ReleasesStorage
from openprocurement.ocds.export.models import release_tenders, release_tender
from ..contrib.client import APIClient
from logging.config import dictConfig
from ..bridge import APIDataBridge
from ..helpers import (
    exists_or_modified,
    fetch_tenders,
    fetch_tender_versioned,
    save_items,
    save_patched
)


logger = logging.getLogger(__name__)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def batch_releases(prefix, src, dest, tenders_db=None):
    logger.info('Starting generating releases')
    while True:
        for batch in src:
            logger.info('Got {} tenders'.format(len(batch)))
            if tenders_db:
                save_patched(tenders_db, batch)
            releases = release_tenders(iter(batch), prefix)
            dest.put(releases)
            gevent.sleep(0.5)
        gevent.sleep(2)


def create_releases(prefix, src, dest, tenders_db=None):
    logger.info('Starting generating releases')
    while True:
        for batch in src:
            logger.info('Got {} tenders'.format(len(batch)))
            for tender in batch:
                if tenders_db:
                    save_patched(tenders_db, tender)
                try:
                    release = release_tender(tender, prefix)
                    logger.info("generated release for tender "
                                "{}".format(tender['_id']))
                    dest.put(release)
                except Exception as e:
                    logger.fatal('Error {} during'
                                 ' generation release'.format(e))
            gevent.sleep(0.5)
        gevent.sleep(2)


def run():
    parser = argparse.ArgumentParser('API databridge')
    parser.add_argument('-c', '--config', required=True)
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print "Not a valid config"
        sys.exit(1)

    with open(args.config) as cfg:
        config = yaml.load(cfg)
    if 'logging' in config:
        dictConfig(config['logging'])
    else:
        logging.basicConfig(level=logging.DEBUG)
    tenders = TendersStorage(config['tenders_db']['url'], config['tenders_db']['name'])
    storage = ReleasesStorage(config['releases_db']['url'], config['releases_db']['name'])

    client = APIClient(
        config['api']['api_key'],
        config['api']['api_host'],
        config['api']['api_version']
    )

    _filter = functools.partial(exists_or_modified, tenders)
    #_fetch = functools.partial(fetch_tender_versioned, client)
    #_batch = functools.partial(batch_releases, config.get('release').get('prefix'))
    _fetch = functools.partial(fetch_tenders, client)
    _batch = functools.partial(create_releases, config.get('release').get('prefix'), tenders_db=tenders)
    _save = functools.partial(save_items, storage)

    bridge = APIDataBridge(config, filter_feed=_filter)
    bridge.add_gt(_fetch)
    bridge.add_gt(_batch)
    bridge.add_gt(_save, last=True)
    bridge.run()