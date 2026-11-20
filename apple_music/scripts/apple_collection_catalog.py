"""Read a complete catalog list without requesting playback or downloading audio."""
from urllib.parse import urlsplit

async def collect(api,url):
    parts=urlsplit(url);kind=parts.path.split('/')[2];identifier=parts.path.rstrip('/').split('/')[-1]
    if kind not in ('album','playlist'):raise ValueError('not_collection')
    result=await (api.get_album(identifier) if kind=='album' else api.get_playlist(identifier))
    item=result['data'][0];relation=item['relationships']['tracks'];rows=list(relation.get('data',[]));next_uri=relation.get('next');href=relation.get('href');seen=set()
    while next_uri:
        if next_uri in seen or len(rows)>2000:raise ValueError('catalog_pagination_invalid')
        seen.add(next_uri);page=await api.get_extended_api_data(next_uri,href)
        rows.extend(page['data']);next_uri=page.get('next')
    if len(rows)>2000:raise ValueError('collection_too_large')
    if kind=='album':rows=sorted(rows,key=lambda row:(int(row.get('attributes',{}).get('discNumber') or 1),int(row.get('attributes',{}).get('trackNumber') or 0)))
    tracks=[];ids=set();unsupported=0
    for row in rows:
        track_id=str(row.get('id',''));attrs=row.get('attributes') or {}
        if row.get('type')!='songs' or not track_id.isdigit():unsupported+=1;continue
        if track_id in ids:continue
        ids.add(track_id)
        tracks.append(dict(id=track_id,title=str(attrs.get('name') or 'Track')[:240],url=f'https://music.apple.com/{parts.path.split("/")[1]}/song/{track_id}',duration_ms=attrs.get('durationInMillis'),disc=attrs.get('discNumber'),track=attrs.get('trackNumber')))
    if not tracks:raise ValueError('collection_has_no_tracks')
    return dict(title=str(item.get('attributes',{}).get('name') or kind.title())[:240],kind=kind,tracks=tracks,unsupported=unsupported,total_catalog_rows=len(rows))
