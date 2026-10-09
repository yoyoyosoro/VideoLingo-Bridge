"""Installation must provision tokenizer data before the first video task."""
import importlib.util
import io
from pathlib import Path
import zipfile

import nltk
import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nltk_installer', ROOT / 'installer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def isolated_data(monkeypatch, tmp_path):
    monkeypatch.setattr(nltk.data, 'path', [str(tmp_path)])
    monkeypatch.setattr(installer, 'NLTK_DATA_DIR', tmp_path, raising=False)
    return tmp_path


def package_archive(name):
    files = {
        'punkt_tab': {
            'english/abbrev_types.txt': '', 'english/collocations.tab': '',
            'english/ortho_context.tab': '', 'english/sent_starters.txt': '',
        },
        'cmudict': {'cmudict': 'HELLO  HH AH0 L OW1\n'},
        'averaged_perceptron_tagger': {'averaged_perceptron_tagger.pickle': 'fixture'},
        'averaged_perceptron_tagger_eng': {
            'averaged_perceptron_tagger_eng.weights.json': '{}',
        },
    }[name]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for filename, content in files.items():
            archive.writestr(f'{name}/{filename}', content)
    return buffer.getvalue()


def test_fresh_install_can_split_sentences_without_runtime_download(monkeypatch, isolated_data):
    def download(url, **kwargs):
        assert url.startswith('https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/')
        response = requests.Response()
        response.status_code = 200
        response._content = package_archive(Path(url).stem)
        return response
    monkeypatch.setattr(requests, 'get', download)
    installer.install_nltk_data()
    # Use a fresh tokenizer: another test/session may already have cached one.
    from nltk.tokenize.punkt import PunktTokenizer
    assert PunktTokenizer('english').tokenize('Hello world. This is a test.') == [
        'Hello world.', 'This is a test.',
    ]
    assert not installer.missing_nltk_resources()
    nltk.data.find('corpora/cmudict.zip')
    nltk.data.find('taggers/averaged_perceptron_tagger.zip')
    # Rerunning setup with complete data must work offline.
    monkeypatch.setattr(requests, 'get', lambda *a, **k: pytest.fail('Unexpected download'))
    installer.install_nltk_data()


def test_failed_download_is_reported_before_install_succeeds(monkeypatch, isolated_data):
    def offline(*args, **kwargs):
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(requests, 'get', offline)
    with pytest.raises(requests.ConnectionError, match='offline'):
        installer.install_nltk_data()
    assert not list(isolated_data.rglob('*.zip'))


def test_archive_cannot_extract_outside_data_directory(monkeypatch, isolated_data):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('../../escaped.txt', 'bad')
    response = requests.Response()
    response.status_code = 200
    response._content = buffer.getvalue()
    monkeypatch.setattr(requests, 'get', lambda *a, **k: response)
    with pytest.raises(ValueError, match='archive'):
        installer.install_nltk_data()
    assert not (isolated_data.parent / 'escaped.txt').exists()
