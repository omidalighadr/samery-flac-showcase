"""Bounded catalogue album order and per-job filename numbering."""
from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace
from urllib.parse import urlsplit

_ORDERED=ContextVar('samery_ordered_album',default=False)


def enabled():return _ORDERED.get()


@contextmanager
def naming(active=True):
    token=_ORDERED.set(active)
    try:yield
    finally:_ORDERED.reset(token)


def prefix(data):
    if not enabled():return ''
    from scripts.music_metadata import number
    track=number(data.get('track'));disc=number(data.get('disc')) or 1
    return f'{disc:02d}-{track:02d} ' if track else ''


def sort_tracks(rows,collection_id):
    result={}
    for item in rows:
        if (item.get('wrapperType')=='track' and item.get('kind')=='song'
            and str(item.get('collectionId'))==str(collection_id) and item.get('trackId')):
            result.setdefault(str(item['trackId']),item)
    return sorted(result.values(),key=lambda r:(int(r.get('discNumber') or 1),int(r.get('trackNumber') or 0)))

