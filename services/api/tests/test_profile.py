"""Profile portraits are real private raster images, never public file URLs."""
from io import BytesIO
import json
import zipfile
from PIL import Image, PngImagePlugin
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from test_workflows import client, database, register
from app.main import app
from app.db import DB
from app.profile import ProfileImage


def picture(color='orange', size=(1024, 768), metadata=False):
    result = BytesIO()
    info = PngImagePlugin.PngInfo()
    if metadata:
        info.add_text('private-location', 'GPS-PRIVATE-METADATA-TEST')
    Image.new('RGB', size, color).save(result, format='PNG', pnginfo=info)
    return result.getvalue()


def upload(client, content=None, name='portrait.png'):
    return client.put('/api/v1/profile/photo', files={'file': (name, content if content is not None else picture(), 'image/png')})


def test_photo_is_resized_stripped_persisted_and_replaceable(client):
    register(client)
    assert client.get('/api/v1/profile/photo/info').json()['present'] is False
    first = upload(client, picture(metadata=True))
    assert first.status_code == 200, first.text
    assert first.json()['present'] and first.json()['url'].startswith('/api/v1/profile/photo?v=')
    response = client.get(first.json()['url'])
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/jpeg'
    assert 'no-store' in response.headers['cache-control']
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert b'GPS-PRIVATE-METADATA-TEST' not in response.content
    decoded = Image.open(BytesIO(response.content))
    assert decoded.size == (512, 384) and not decoded.getexif()
    second = upload(client, picture('blue'))
    assert second.status_code == 200 and second.json()['version'] != first.json()['version']
    assert client.get('/api/v1/profile/photo').content != response.content
    with DB() as db:
        assert db.scalar(select(func.count()).select_from(ProfileImage)) == 1
    assert client.delete('/api/v1/profile/photo').json()['present'] is False
    assert client.get('/api/v1/profile/photo').status_code == 404
    assert client.delete('/api/v1/profile/photo').status_code == 200


def test_photo_validation_preserves_existing_image(client):
    register(client)
    original = upload(client).json()
    assert upload(client, b'<svg><script>bad()</script></svg>').status_code == 422
    assert upload(client, b'').status_code == 422
    assert upload(client, b'x' * (2 * 1024 * 1024 + 1)).status_code == 413
    assert upload(client, picture(size=(3000, 3000))).status_code == 422
    animated = BytesIO()
    Image.new('RGB', (8, 8), 'red').save(animated, format='PNG', save_all=True, append_images=[Image.new('RGB', (8, 8), 'blue')], duration=100, loop=0)
    assert upload(client, animated.getvalue()).status_code == 422
    assert client.get('/api/v1/profile/photo/info').json()['version'] == original['version']


def test_photo_requires_session_csrf_and_never_accepts_another_account_id(client):
    alice = register(client)['user']['id']
    uploaded = upload(client).json()
    original = client.get(uploaded['url']).content
    with TestClient(app) as other:
        assert other.get(uploaded['url']).status_code == 401
        assert upload(other).status_code == 401
        register(other, 'bob@example.com')
        assert other.get(uploaded['url']).status_code == 404
        assert other.get('/api/v1/profile/photo?user_id=' + alice).status_code == 404
        assert other.delete('/api/v1/profile/photo?user_id=' + alice).status_code == 200
        assert other.get('/api/v1/profile/photo/info').json()['present'] is False
        assert upload(other, picture('green')).status_code == 200
        assert other.get(uploaded['url']).content != original
        other.headers.pop('X-CSRF-Token')
        assert upload(other).status_code == 403
        assert other.delete('/api/v1/profile/photo').status_code == 403
    assert client.get(uploaded['url']).content == original


def test_photo_export_and_account_erasure(client):
    register(client)
    upload(client)
    photo = client.get('/api/v1/profile/photo').content
    export = client.get('/api/v1/export/archive')
    assert export.status_code == 200, export.text
    with zipfile.ZipFile(BytesIO(export.content)) as bundle:
        assert bundle.read('profile/photo.jpg') == photo
        data = json.loads(bundle.read('memoryvault.json'))
        assert data['profile']['photo']['path'] == 'profile/photo.jpg'
        assert 'profile_images' not in data
    assert client.delete('/api/v1/account').status_code == 200
    with DB() as db:
        assert db.scalar(select(func.count()).select_from(ProfileImage)) == 0
