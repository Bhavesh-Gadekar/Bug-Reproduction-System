import sys
sys.path.insert(0, '.')
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

res_all = client.get('/api/runs?page=1&page_size=10')
print('ALL:', res_all.status_code, 'total:', res_all.json()['total'])

res_stale = client.get('/api/runs?is_stale=true')
stale_json = res_stale.json()
print('STALE ONLY:', res_stale.status_code, 'total:', stale_json['total'])
for item in stale_json['items'][:3]:
    print('  STALE ITEM:', item['id'], 'raw_status:', item['raw_status'], 'is_stale:', item['is_stale'])

res_error = client.get('/api/runs?raw_status=error')
error_json = res_error.json()
print('ERROR ONLY:', res_error.status_code, 'total:', error_json['total'])
for item in error_json['items'][:3]:
    print('  ERROR ITEM:', item['id'], 'raw_status:', item['raw_status'], 'persist_error:', (item['persist_error'][:30] if item['persist_error'] else None))
