"""Publishing through the Buffer GraphQL API (https://developers.buffer.com)."""
import os
import requests

ENDPOINT = 'https://api.buffer.com'


def _gql(query, variables=None):
    key = os.environ.get('BUFFER_API_KEY')
    if not key:
        raise SystemExit('BUFFER_API_KEY ortam değişkeni yok (GitHub Secrets).')
    r = requests.post(ENDPOINT, json={'query': query, 'variables': variables or {}},
                      headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}, timeout=60)
    try:
        js = r.json()
    except Exception:
        raise RuntimeError(f'Buffer yanıtı okunamadı: {r.status_code} {r.text[:300]}')
    if js.get('errors'):
        raise RuntimeError(f'Buffer hatası: {js["errors"]}')
    return js['data']


def channels():
    orgs = _gql('query { account { organizations { id name } } }')['account']['organizations']
    out = []
    for o in orgs:
        q = 'query($o: OrganizationId!){ channels(input:{organizationId:$o}){ id name displayName service isQueuePaused } }'
        try:
            chs = _gql(q, {'o': o['id']})['channels']
        except RuntimeError:
            q = 'query($o: String!){ channels(input:{organizationId:$o}){ id name displayName service isQueuePaused } }'
            chs = _gql(q, {'o': o['id']})['channels']
        for c in chs:
            c['organization'] = o['name']
            out.append(c)
    return out


CREATE = '''mutation($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id } }
    ... on MutationError { message }
  }
}'''


def publish(meta, cfg, video_url):
    """Create one post per configured channel. Returns list of (service, result)."""
    wanted = [s.lower() for s in cfg['publish']['services']]
    results = []
    for ch in channels():
        svc = (ch.get('service') or '').lower()
        if svc not in wanted:
            continue
        text = meta['instagram_text'] if svc == 'instagram' else meta['youtube_text']
        inp = {
            'channelId': ch['id'],
            'text': text,
            'schedulingType': 'automatic',
            'mode': cfg['publish'].get('mode', 'shareNow'),
            'assets': [{'video': {'url': video_url, 'metadata': {'thumbnailOffset': 1500}}}],
            'aiAssisted': True,
        }
        if svc == 'instagram':
            inp['metadata'] = {'instagram': {'type': 'reel', 'shouldShareToFeed': True, 'isAiGenerated': True}}
        elif svc == 'youtube':
            inp['metadata'] = {'youtube': {'title': meta['youtube_title'][:95], 'categoryId': str(cfg['publish'].get('youtube_category', '28')),
                                           'privacy': 'public', 'madeForKids': False, 'notifySubscribers': True,
                                           'isAiGenerated': True}}
        res = _gql(CREATE, {'input': inp})['createPost']
        if res.get('__typename') == 'MutationError':
            results.append((svc, 'HATA: ' + res.get('message', '')))
        else:
            results.append((svc, 'OK ' + str((res.get('post') or {}).get('id', ''))))
    if not results:
        raise RuntimeError(f'Buffer\'da {wanted} kanalı bulunamadı. Kanalları Buffer\'a bağladın mı?')
    return results
