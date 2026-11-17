"""TDW patch: API key authentication for ML backends."""
import json

import pytest
from ml.api_connector import MLApi
from ml.models import MLBackend

from label_studio.tests.utils import make_project, register_ml_backend_mock

PROJECT_CONFIG = """<View><Image name="image" value="$image_url"/><Choices name="label"
          toName="image"><Choice value="pos"/><Choice value="neg"/></Choices></View>"""
URL = 'https://ml_backend_api_key'


@pytest.fixture
def ml_mock(ml_backend):
    register_ml_backend_mock(ml_backend, url=URL, setup_model_version='1.0.0')
    yield ml_backend


def test_connector_authorization_header_is_bearer():
    api = MLApi(url=URL, auth_method='API_KEY', api_key='k-123')
    assert api.http.headers['Authorization'] == 'Bearer k-123'


def test_connector_custom_header_is_raw_key():
    api = MLApi(url=URL, auth_method='API_KEY', api_key='k-123', api_key_header='X-API-Key')
    assert api.http.headers['X-API-Key'] == 'k-123'
    assert 'Authorization' not in api.http.headers


def test_connector_ignores_key_for_other_methods():
    api = MLApi(url=URL, auth_method='NONE', api_key='k-123')
    assert 'Authorization' not in api.http.headers


def test_connector_result_never_contains_the_key(ml_mock):
    api = MLApi(url=URL, auth_method='API_KEY', api_key='k-123')
    res = api.health()
    assert 'k-123' not in json.dumps(res.headers)


@pytest.mark.django_db
def test_api_key_flow(business_client, ml_mock, mock_gethostbyname):
    project = make_project(
        config=dict(is_published=True, label_config=PROJECT_CONFIG, title='api_key'), user=business_client.user
    )
    base = {'project': project.id, 'title': 'yolo', 'url': URL, 'auth_method': 'API_KEY'}

    # key is required
    r = business_client.post('/api/ml/', data=base)
    assert r.status_code == 400
    assert 'API key is required' in r.json()['validation_errors']['non_field_errors'][0]

    # invalid header name is rejected (no header injection)
    r = business_client.post('/api/ml/', data={**base, 'api_key': 'k', 'api_key_header': 'X Bad\r\nHeader'})
    assert r.status_code == 400

    # create with the default header
    r = business_client.post('/api/ml/', data={**base, 'api_key': 'secret-1'})
    assert r.status_code == 201
    body = r.json()
    assert 'api_key' not in body and body['api_key_is_set'] is True
    assert body['api_key_header'] == 'Authorization'
    sent = [h for h in ml_mock.request_history if h.url.startswith(URL)]
    assert sent and all(h.headers.get('Authorization') == 'Bearer secret-1' for h in sent)
    assert 'secret-1' not in json.dumps(business_client.get(f"/api/ml/{body['id']}").json())

    # patch without the key keeps the stored key; header switches to X-API-Key
    ml_mock.reset_mock() if hasattr(ml_mock, 'reset_mock') else None
    r = business_client.patch(
        f"/api/ml/{body['id']}",
        data=json.dumps({**base, 'api_key_header': 'X-API-Key'}),
        content_type='application/json',
    )
    assert r.status_code == 200
    assert MLBackend.objects.get(id=body['id']).api_key == 'secret-1'
    last = ml_mock.request_history[-1]
    assert last.headers.get('X-API-Key') == 'secret-1'
