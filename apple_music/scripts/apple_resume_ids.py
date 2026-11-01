"""Non-secret completed-ID snapshot consumed before each audio download."""
import json
from pathlib import Path
import re


def load_completed(output,value=None):
    if not value:return set()
    raw=Path(value)
    path=raw.resolve()
    if raw.is_symlink() or not path.is_relative_to(Path(output).resolve()) or path.stat().st_size>2_000_000:
        raise ValueError('Invalid resume snapshot')
    values=json.loads(path.read_text())
    if not isinstance(values,list):raise ValueError('Invalid resume snapshot')
    return {s for s in values if isinstance(s,str) and re.fullmatch(r'\d{1,24}',s)}


def track_id(item):
    tags=getattr(item.media,'tags',None)
    return str(getattr(tags,'title_id',None) or getattr(item.media,'media_id',''))
